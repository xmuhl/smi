"""发布新鲜度看门狗 + 自动恢复（2026-08-27 cron 整体丢弃事故的兜底）。

事故背景：2026-08-27 close-snapshot 三个 cron 窗口（16:23/18:23/19:23
CST）与 archive-raw 全部未被 GitHub 调度创建（workflow 均 active、
cron 配置未变，属 GitHub 侧调度丢弃）。"未触发"不产生失败运行——
GitHub 默认通知完全静默，数据停更至当晚 20:19 手动 dispatch 才恢复。

本脚本作为 freshness-watchdog workflow 的执行体，对线上站点巡检：
  --mode today    盘后巡检：交易日当日 latest.json 未发布 → 自动
                  dispatch close-snapshot（45 分钟内已有运行则不重复
                  派发）+ 告警，红灯可见；
  --mode catchup  次晨巡检：上一交易日 daily 文件在线上缺失（整晚
                  全部窗口丢失）→ 自动 dispatch manual-backfill 该日
                  （90 分钟内已有运行则不重复派发）+ 告警。

退出码：
  0 = 新鲜 / 非交易日 / 无缺口
  1 = 存在缺口（已尝试自动恢复并推通知）——工作流红 + GitHub 邮件
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ALERT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(TOOLS_ALERT_DIR))

from collector.calendar import is_trading_day, previous_trading_day  # noqa: E402
from collector.schema import TZ_SHANGHAI  # noqa: E402

import data_health  # noqa: E402  # tools/alert/data_health.py（复用 _notify）

SITE_LATEST = "https://smi-6s2.pages.dev/data/latest.json"
SITE_DAILY = "https://smi-6s2.pages.dev/data/daily/{year}/{date}.json"

# 同一恢复动作在冷却窗口内不重复派发（巡检是小时级，一次采集
# 15~40 分钟；冷却期内交由在途/刚完成的运行自行收敛）。
DISPATCH_COOLDOWN_MINUTES = {
    "close-snapshot.yml": 45,
    "manual-backfill.yml": 90,
}


def _today_cst() -> date:
    return datetime.now(TZ_SHANGHAI).date()


def _fetch_json(url: str, attempts: int = 3) -> dict | None:
    """拉取站点 JSON；网络抖动重试。返回 None = 不可达/非法。"""
    for attempt in range(1, attempts + 1):
        try:
            # Cloudflare 拦截 Python-urllib 默认 UA（本机实测 403），
            # 常规浏览器 UA 直连通畅。
            request = urllib.request.Request(
                url,
                headers={
                    "Cache-Control": "no-cache",
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    ),
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )
        except Exception as exc:  # noqa: BLE001 — 巡检须吞掉网络层异常
            print(
                f"fetch attempt={attempt}/{attempts} "
                f"failed: {exc}"
            )
    return None


def _github_api(path: str, method: str = "GET") -> tuple[int, dict | list]:
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _recent_run_created_within(
    workflow_filename: str,
    cooldown_minutes: int,
) -> bool:
    """冷却窗口内该 workflow 是否已有运行（含排队/进行中/刚完成）。"""
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository:
        return False

    status, payload = _github_api(
        f"/repos/{repository}/actions/workflows/"
        f"{workflow_filename}/runs?per_page=5"
    )
    if status != 200:
        # API 不可达时不派发（宁可漏恢复，不可叠加派发），
        # 告警仍会通过退出码 1 送达。
        print(f"runs api status={status}; treat as recent-run-exists")
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=cooldown_minutes
    )
    for run in payload.get("workflow_runs", []):
        created = run.get("created_at")
        if not created:
            continue
        try:
            created_at = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if created_at >= cutoff:
            print(
                f"recent run exists: {workflow_filename} "
                f"created={created} status={run.get('status')}"
            )
            return True

    return False


def _post_dispatch_payload(
    workflow_filename: str, inputs: dict[str, str]
) -> bool:
    """带 body 的 POST（_github_api 不携带 body，单列实现）。"""
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository:
        print("GITHUB_REPOSITORY missing; cannot dispatch")
        return False

    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    body = json.dumps({"ref": "main", "inputs": inputs}).encode(
        "utf-8"
    )
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/"
        f"workflows/{workflow_filename}/dispatches",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(
                f"dispatch {workflow_filename} "
                f"inputs={inputs} api_status={response.status}"
            )
            return response.status == 204
    except urllib.error.HTTPError as exc:
        print(f"dispatch failed api_status={exc.code}")
        return False


def _run_today_mode() -> int:
    today = _today_cst()

    if not is_trading_day(today):
        print(f"NON_TRADING_DAY {today.isoformat()}")
        return 0

    latest = _fetch_json(SITE_LATEST)
    if latest is None:
        data_health._notify(
            "freshness-watchdog(today)",
            [
                f"SITE_LATEST_UNREACHABLE：{SITE_LATEST} 重试 "
                "3 次失败——站点/Pages 不可达，需人工查看部署链路",
            ],
        )
        return 1

    site_date = str(latest.get("tradeDate", ""))
    print(
        f"site tradeDate={site_date} expected>={today.isoformat()}"
    )

    if site_date >= today.isoformat():
        print("FRESH")
        return 0

    findings = [
        f"SITE_LATEST_STALE：线上停更于 {site_date or 'UNKNOWN'}，"
        f"交易日 {today.isoformat()} 当日快照未发布"
        "（close-snapshot 调度窗口疑似被 GitHub 丢弃）",
    ]

    if _recent_run_created_within(
        "close-snapshot.yml",
        DISPATCH_COOLDOWN_MINUTES["close-snapshot.yml"],
    ):
        findings.append(
            "RECOVERY_DEFERRED：45 分钟冷却期内已有 close-snapshot "
            "运行，不重复派发"
        )
    else:
        dispatched = _post_dispatch_payload(
            "close-snapshot.yml",
            {"date": "auto", "deploy": "false"},
        )
        findings.append(
            "RECOVERY_DISPATCHED：已自动派发 close-snapshot"
            if dispatched
            else "RECOVERY_DISPATCH_FAILED：派发失败，需人工 "
            "Actions → close-snapshot → Run workflow"
        )

    data_health._notify("freshness-watchdog(today)", findings)
    return 1


def _run_catchup_mode() -> int:
    today = _today_cst()

    if not is_trading_day(today):
        print(f"NON_TRADING_DAY {today.isoformat()}")
        return 0

    expected = previous_trading_day(today)
    url = SITE_DAILY.format(
        year=expected.year, date=expected.isoformat()
    )
    payload = _fetch_json(url)

    if payload is not None:
        print(f"CATCHUP_OK {expected.isoformat()} present")
        return 0

    findings = [
        f"PREVIOUS_DAY_MISSING：上一交易日 {expected.isoformat()} "
        "快照未发布（整晚调度/采集全部丢失），将回补该日",
    ]

    if _recent_run_created_within(
        "manual-backfill.yml",
        DISPATCH_COOLDOWN_MINUTES["manual-backfill.yml"],
    ):
        findings.append(
            "RECOVERY_DEFERRED：90 分钟冷却期内已有 manual-backfill "
            "运行，不重复派发"
        )
    else:
        dispatched = _post_dispatch_payload(
            "manual-backfill.yml",
            {"date": expected.isoformat(), "deploy": "false"},
        )
        findings.append(
            f"RECOVERY_DISPATCHED：已自动派发 manual-backfill "
            f"date={expected.isoformat()}"
            if dispatched
            else "RECOVERY_DISPATCH_FAILED：派发失败，需人工 "
            "Actions → manual-backfill → Run workflow"
        )

    data_health._notify("freshness-watchdog(catchup)", findings)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SMI freshness watchdog"
    )
    parser.add_argument(
        "--mode",
        choices=("today", "catchup"),
        default="today",
        help="today=盘后当日巡检；catchup=次晨缺口巡检",
    )
    args = parser.parse_args()

    if args.mode == "catchup":
        return _run_catchup_mode()
    return _run_today_mode()


if __name__ == "__main__":
    sys.exit(main())
