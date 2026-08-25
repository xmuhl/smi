"""数据健康检查 + 飞书告警（P0-b：消灭"绿皮红心"）。

背景（2026-08-25 事故）：t1-reconcile 无论补数成败一律退出 0，margin
连续 ERROR 两天完全静默；GitHub 只对红色运行发邮件，绿运行里的数据
缺口无人可见。本脚本作为各数据 workflow 的收尾步骤（if: always()），
把数据级缺口显性化为 annotation / 非零退出 / 飞书 webhook。

用法：
  python tools/alert/data_health.py --mode close-snapshot [--date auto|YYYY-MM-DD]
  python tools/alert/data_health.py --mode t1-reconcile
  python tools/alert/data_health.py --mode generic

退出码：
  0 = 健康（含非交易日、无告警事实）
  1 = 数据缺口（当日快照未发布 / margin ERROR）——工作流红 + 通知

通知口径：
  - findings 非空，或 JOB_STATUS=failure（部署/提交步骤失败）→ 推飞书；
  - FEISHU_WEBHOOK_URL 未配置时打印提示并跳过（不阻塞、不报错）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from collector.calendar import is_trading_day  # noqa: E402
from collector.config import daily_path  # noqa: E402
from collector.schema import TZ_SHANGHAI  # noqa: E402

# margin ERROR 是硬缺口（源失败，等价于数据错误）；
# STALE/PENDING 是交易所披露延迟（T+1/顺延），只提示不红灯。
MARGIN_HARD_FAIL_STATUSES = {"ERROR"}

# 非 margin 模块的 ERROR/UNAVAILABLE 仅 annotation 提示：
# fundFlow 等模块存在产品裁决的已知边界，红灯会造成长期噪音。


def _today_cst() -> str:
    return datetime.now(TZ_SHANGHAI).date().isoformat()


def _resolve_close_date(raw: str) -> str:
    if raw and raw != "auto":
        return raw
    return _today_cst()


def _load_daily(date_str: str) -> dict | None:
    path = daily_path(date_str)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _available_snapshot_dates_before_today() -> list[str]:
    from collector.jobs.t1_reconcile import (
        _available_snapshot_dates_before_today as scan,
    )

    return scan()


def _run_url() -> str:
    base = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if base and repo and run_id:
        return f"{base}/{repo}/actions/runs/{run_id}"
    return "local-run"


def _notify(title: str, findings: list[str]) -> None:
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    job_status = os.environ.get("JOB_STATUS", "")

    if not findings and job_status in ("", "success"):
        return

    lines = [f"[SMI] {title}"]
    if job_status and job_status != "success":
        lines.append(f"job status: {job_status}")
    lines.extend(findings)
    lines.append(f"run: {_run_url()}")
    text = "\n".join(lines)

    if not webhook:
        print("FEISHU_WEBHOOK_URL not configured; notification skipped")
        print(text)
        return

    payload = json.dumps(
        {"msg_type": "text", "content": {"text": text}},
    ).encode("utf-8")

    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            if body.get("code") not in (0, None):
                print(f"FEISHU_NOTIFY_REJECTED {body}")
            else:
                print("FEISHU_NOTIFIED")
    except Exception as exc:  # noqa: BLE001
        # 告警通道故障不得影响健康判定本身
        print(f"FEISHU_NOTIFY_FAILED {type(exc).__name__}: {exc}")


def check_close_snapshot(target: str) -> int:
    from datetime import date as date_type

    if not is_trading_day(
        date_type.fromisoformat(target),
        fallback_weekday=True,
    ):
        print(f"NON_TRADING_DAY {target}")
        return 0

    snapshot = _load_daily(target)

    if snapshot is None:
        finding = f"当日快照未发布：{target} 无 daily 文件（采集失败或被门禁拦截）"
        print(f"::error::{finding}")
        _notify("close-snapshot 数据缺口", [finding])
        return 1

    findings = _scan_modules(snapshot)
    hard = _margin_hard_findings(snapshot, target)

    if hard:
        for line in hard:
            print(f"::error::{line}")
        _notify("close-snapshot 数据缺口", hard + findings)
        return 1

    for line in findings:
        print(f"::warning::{line}")

    _notify("close-snapshot", [])
    print(f"HEALTH_OK {target} overall={snapshot.get('overallStatus')}")
    return 0


def check_t1_reconcile() -> int:
    dates = _available_snapshot_dates_before_today()

    if not dates:
        print("NO_SNAPSHOT")
        return 0

    errors: list[str] = []
    warnings: list[str] = []

    for target in dates:
        snapshot = _load_daily(target)
        if snapshot is None:
            continue

        margin = snapshot.get("modules", {}).get("margin", {})
        status = margin.get("status")

        if status in MARGIN_HARD_FAIL_STATUSES:
            first_error = (margin.get("errors") or [""])[0]
            errors.append(
                f"margin {target}={status}：{first_error[:80]}"
            )
        elif status not in ("FINAL", None):
            warnings.append(f"margin {target}={status}（披露延迟，等下窗口重试）")

    for line in errors:
        print(f"::error::{line}")
    for line in warnings:
        print(f"::warning::{line}")

    if errors:
        _notify("t1-reconcile 两融缺口", errors + warnings)
        return 1

    _notify("t1-reconcile", [])
    print("HEALTH_OK margin all FINAL (or pending disclosure)")
    return 0


def _scan_modules(snapshot: dict) -> list[str]:
    findings: list[str] = []

    for name, module in (snapshot.get("modules") or {}).items():
        if not isinstance(module, dict):
            continue
        if module.get("status") in ("ERROR", "UNAVAILABLE"):
            first_error = (module.get("errors") or [""])[0]
            findings.append(
                f"module {name}={module.get('status')}：{str(first_error)[:80]}"
            )

    return findings


def _margin_hard_findings(
    snapshot: dict,
    target: str,
) -> list[str]:
    margin = (snapshot.get("modules") or {}).get("margin", {})

    if not isinstance(margin, dict):
        return []

    if margin.get("status") in MARGIN_HARD_FAIL_STATUSES:
        first_error = (margin.get("errors") or [""])[0]
        return [
            f"margin {target}={margin.get('status')}：{str(first_error)[:80]}"
        ]

    return []


def check_generic() -> int:
    _notify("workflow failed", [])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SMI data health & alert")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("close-snapshot", "t1-reconcile", "generic"),
    )
    parser.add_argument("--date", default="auto")
    args = parser.parse_args()

    if args.mode == "close-snapshot":
        return check_close_snapshot(_resolve_close_date(args.date))
    if args.mode == "t1-reconcile":
        return check_t1_reconcile()
    return check_generic()


if __name__ == "__main__":
    sys.exit(main())
