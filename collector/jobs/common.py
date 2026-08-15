"""任务公共逻辑：快照构建、幂等写入、manifest/status 更新。"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from collector.calendar import is_trading_day, previous_trading_day
from collector.config import (
    DAILY_DIR,
    daily_path,
    ensure_dirs,
    load_yaml,
    tmp_path,
)
from collector.schema import (
    TZ_SHANGHAI,
    canonical_json,
    finalize_snapshot,
    new_snapshot,
    now_iso,
)
from collector.status import ModuleStatus

VOLATILE_FIELDS = {
    "generatedAt",
    "updatedAt",
    "revision",
    "generationReason",
}

def resolve_target_date(raw: str) -> str:
    """解析目标日期，所有“今天”语义统一使用 Asia/Shanghai。"""
    if raw and raw != "auto":
        return date.fromisoformat(raw).isoformat()

    today = datetime.now(TZ_SHANGHAI).date()

    if is_trading_day(today, fallback_weekday=True):
        return today.isoformat()

    return previous_trading_day(
        today,
        fallback_weekday=True,
    ).isoformat()

def build_snapshot(
    trade_date: str,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    """按设计文档组装 9 大模块快照。"""
    from collector.calculators.summary import generate_summary
    from collector.modules.fund_flow import collect_fund_flow
    from collector.modules.margin import collect_margin
    from collector.modules.market_index import collect_market_index
    from collector.modules.northbound import collect_northbound
    from collector.modules.sectors import collect_sectors
    from collector.modules.sentiment import collect_sentiment
    from collector.modules.turnover import collect_turnover

    snapshot = new_snapshot(
        trade_date,
        legacy=legacy,
    )

    modules = snapshot["modules"]

    market_rules = load_yaml("market-rules.yaml")

    modules["marketIndex"] = collect_market_index(trade_date)
    modules["turnover"] = collect_turnover(
        trade_date,
        market_rules=market_rules,
    )
    modules["sentiment"] = collect_sentiment(trade_date)
    modules["sectorPerformance"] = collect_sectors(trade_date)
    modules["fundFlow"] = collect_fund_flow(trade_date)
    modules["northbound"] = collect_northbound(trade_date)
    modules["margin"] = collect_margin(trade_date)
    modules["tracks"] = _collect_tracks(trade_date, modules)
    modules["summary"] = generate_summary(snapshot)

    return finalize_snapshot(snapshot)

def _collect_tracks(
    trade_date: str,
    modules: dict[str, Any],
) -> dict[str, Any]:
    """Fail-closed 占位。

    当前送审代码尚未实现真实赛道指标采集，绝不能用 0/False 伪造评分。
    """
    cfg = load_yaml("tracks.yaml")
    tracks_cfg = cfg.get("tracks", [])

    items: list[dict[str, Any]] = []

    for tc in tracks_cfg:
        if not tc.get("enabled", True):
            continue

        items.append(
            {
                "trackId": tc["id"],
                "trackName": tc["name"],
                "positioning": tc.get("positioning", ""),
                "turnoverRank": None,
                "turnoverUniverseSize": None,
                "turnoverPercentile": None,
                "mainNetInflow": None,
                "mainNetInflowPercentile": None,
                "continuousInflowDays": None,
                "maAlignment": None,
                "rps60": None,
                "excessReturn20d": None,
                "limitUpCount": None,
                "limitUpRate": None,
                "ladderCompleteness": None,
                "redStockRatio": None,
                "coreCatalyst": {
                    "state": "UNKNOWN",
                    "text": "",
                },
                "earningsRealization": {
                    "state": "UNKNOWN",
                    "text": "",
                },
                "score": None,
                "coveragePct": 0.0,
                "decision": "INSUFFICIENT",
            }
        )

    from collector.calculators.tracks import score_tracks

    return {
        "status": ModuleStatus.UNAVAILABLE.value,
        "dataDate": trade_date,
        "configVersion": "1.0",
        "reason": "TRACK_METRICS_COLLECTOR_NOT_IMPLEMENTED",
        "items": score_tracks(items),
    }

def _semantic_payload(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """移除不应影响幂等比较的运行元数据。"""
    payload = deepcopy(snapshot)

    for field in VOLATILE_FIELDS:
        payload.pop(field, None)

    return payload

def _read_json(path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None

def write_if_changed(
    snapshot: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """语义幂等写入。

    - 时间戳/revision/generationReason 不参与 NO_CHANGE 判断；
    - 只有业务语义变化才 revision + 1；
    - force 只表示重新采集，不允许制造无意义 revision。
    """
    del force

    from collector.validators.schema import validate_snapshot

    ensure_dirs()

    path = daily_path(snapshot["tradeDate"])
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tmp_path(snapshot["tradeDate"])
    tmp.parent.mkdir(parents=True, exist_ok=True)

    finalize_snapshot(snapshot)

    validate_snapshot(snapshot)

    existing = _read_json(path)

    if existing is not None:
        old_semantic = canonical_json(
            _semantic_payload(existing)
        )
        new_semantic = canonical_json(
            _semantic_payload(snapshot)
        )

        if old_semantic == new_semantic:
            return False, "NO_CHANGE"

        snapshot["generatedAt"] = (
            existing.get("generatedAt")
            or snapshot.get("generatedAt")
            or now_iso()
        )

        snapshot["revision"] = (
            int(existing.get("revision", 1)) + 1
        )
    else:
        snapshot["revision"] = max(
            1,
            int(snapshot.get("revision", 1)),
        )

    snapshot["updatedAt"] = now_iso()

    validate_snapshot(snapshot)

    text = json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

    return True, "CHANGED"

def _write_json_atomic(
    path,
    obj: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(temp, path)

def update_manifest_and_latest(
    trade_date: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """重算 manifest，旧日期修订不得让 latestDate 回退。"""
    ensure_dirs()

    data_root = DAILY_DIR.parent
    manifest_path = data_root / "manifest.json"
    latest_path = data_root / "latest.json"
    status_path = data_root / "status.json"

    available_dates = _list_available_dates()

    if not available_dates:
        raise RuntimeError("no daily snapshot found")

    latest_date = available_dates[-1]

    latest_final_date: str | None = None

    for value in reversed(available_dates):
        item = _read_json(daily_path(value))

        if (
            item is not None
            and item.get("overallStatus")
            == ModuleStatus.FINAL.value
        ):
            latest_final_date = value
            break

    latest_snapshot = _read_json(
        daily_path(latest_date)
    )

    if latest_snapshot is None:
        raise RuntimeError(
            f"cannot read latest snapshot: {latest_date}"
        )

    manifest = {
        "schemaVersion": "1.1",
        "latestDate": latest_date,
        "latestFinalDate": latest_final_date,
        "updatedAt": now_iso(),
        "availableDates": available_dates,
    }

    _write_json_atomic(
        manifest_path,
        manifest,
    )

    _write_json_atomic(
        latest_path,
        latest_snapshot,
    )

    errors = _collect_errors(snapshot)

    stale_modules = [
        name
        for name, module
        in snapshot.get("modules", {}).items()
        if module.get("status")
        == ModuleStatus.STALE.value
    ]

    status = {
        "lastWorkflow": os.environ.get(
            "SMI_WORKFLOW",
            "manual",
        ),
        "lastRunAt": now_iso(),
        "lastSuccessfulTradeDate": (
            trade_date
            if not errors
            else latest_final_date
        ),
        "latestDate": latest_date,
        "health": (
            "DEGRADED"
            if errors or stale_modules
            else "OK"
        ),
        "errors": errors,
        "staleModules": stale_modules,
    }

    _write_json_atomic(
        status_path,
        status,
    )

    return manifest

def _list_available_dates() -> list[str]:
    dates: list[str] = []

    if not DAILY_DIR.exists():
        return dates

    for year_dir in DAILY_DIR.iterdir():
        if not year_dir.is_dir():
            continue

        for path in year_dir.glob("*.json"):
            try:
                date.fromisoformat(path.stem)
            except ValueError:
                continue

            dates.append(path.stem)

    return sorted(set(dates))

def _collect_errors(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """收集所有模块的真实错误；PARTIAL 中的子源失败也要进入健康信息（R6-P2-03）。"""
    output: list[dict[str, Any]] = []

    for name, module in snapshot.get(
        "modules",
        {},
    ).items():
        module_errors = module.get(
            "errors",
            [],
        )

        if not module_errors:
            continue

        output.append(
            {
                "module": name,
                "status": module.get("status"),
                "errors": module_errors,
            }
        )

    return output

def snapshot_hash(
    snapshot: dict[str, Any],
) -> str:
    """返回业务语义 Hash，不受运行时间戳影响。"""
    text = canonical_json(
        _semantic_payload(snapshot)
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
