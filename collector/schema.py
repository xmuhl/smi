"""每日快照 Schema 的数据类与构建工具。"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from collector.status import ModuleStatus

TZ_SHANGHAI = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(TZ_SHANGHAI).isoformat(timespec="seconds")


def new_snapshot(trade_date: str, *, legacy: bool = False, revision: int = 1) -> dict[str, Any]:
    """创建空快照骨架（结构固定，值留待填充）。"""
    snapshot: dict[str, Any] = {
        "schemaVersion": "1.1",
        "tradeDate": trade_date,
        "generatedAt": now_iso(),
        "updatedAt": None,
        "revision": revision,
        "overallStatus": ModuleStatus.PENDING.value,
        "generationReason": None,
        "market": "CN_A",
        "timezone": "Asia/Shanghai",
        "meta": {
            "sourceSystem": "TONGDAXIN_LEGACY" if legacy else "SMI_V1",
            "legacy": legacy,
            "importedFromExcel": legacy,
            "officialDisclosureCompatibility": not legacy,
        },
        "modules": {
            "marketIndex": _module("marketIndex"),
            "turnover": _module("turnover"),
            "sentiment": _module("sentiment"),
            "sectorPerformance": _module("sectorPerformance"),
            "fundFlow": _module("fundFlow"),
            "northbound": _module("northbound"),
            "margin": _module("margin"),
            "tracks": _module("tracks"),
            "summary": _module("summary"),
        },
        "validation": {
            "calendarExpectedTradingDay": False,
            "marketDateVerified": False,
            "requiredIndicesPresent": False,
            "stockUniverseCheckPassed": False,
            "criticalErrors": [],
            "warnings": [],
        },
    }
    return snapshot


def _module(name: str) -> dict[str, Any]:
    return {
        "status": ModuleStatus.PENDING.value,
        "dataDate": None,
        "source": [],
        "name": name,
    }


def finalize_snapshot(snapshot: dict[str, Any], *, revision_bump: bool = False) -> dict[str, Any]:
    """设置 updatedAt 并计算 overallStatus。"""
    now = now_iso()
    if snapshot.get("updatedAt") is None or revision_bump:
        snapshot["updatedAt"] = now
    statuses = [m.get("status", "PENDING") for m in snapshot["modules"].values()]
    if any(s == ModuleStatus.ERROR.value for s in statuses):
        snapshot["overallStatus"] = "PARTIAL_ERROR"
    elif any(s == ModuleStatus.PENDING.value for s in statuses):
        snapshot["overallStatus"] = "PARTIAL_PENDING"
    elif all(s == ModuleStatus.FINAL.value for s in statuses):
        snapshot["overallStatus"] = ModuleStatus.FINAL.value
    else:
        snapshot["overallStatus"] = "PARTIAL"
    return snapshot


def canonical_json(
    obj: Any,
) -> str:
    """严格规范 JSON；NaN/Infinity 直接失败。"""
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )

