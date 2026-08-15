"""历史回补后重算成交额跨日派生链（R9-P2-01-B / R9.2 GLM 复核修订）。

不重新抓网络。对每个交易日，用 previous_trading_day 显式定位
"真实上一交易日"并读取该日快照；仅当前后 method 均可证明为
SH_SZ_A_NO_B_NO_BJ_V1 且前值有效时重算
turnoverPrevious / turnoverDelta / turnoverChangePct / volumeState，
随后重算 summary 并持久化；最后重算 manifest/latest。

事务性约束（R9.2）：
- 预期上一交易日的 JSON 缺失或损坏 -> 该日按 PREVIOUS_UNAVAILABLE
  处理，绝不向前跨越到更早的存在文件（N1）；
- 全部派生字段、method 回填与 summary 均与磁盘一致时不 finalize、
  不 bump revision，保证重复执行幂等、NO_CHANGE 可达（N2）；
- 比较逻辑唯一来自 turnover._turnover_comparison，无第二套阈值。
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from typing import Any

from collector.calculators.summary import generate_summary
from collector.config import DAILY_DIR, daily_path, load_yaml
from collector.jobs.common import (
    update_manifest_and_latest,
    write_if_changed,
)
from collector.modules.turnover import (
    _infer_turnover_method,
    _turnover_comparison,
)
from collector.schema import finalize_snapshot
from collector.status import ModuleStatus

DERIVED_KEYS = (
    "turnoverPrevious",
    "turnoverDelta",
    "turnoverChangePct",
    "volumeState",
    "previousMethod",
    "comparisonStatus",
)


def _read_snapshot(path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _previous_info_from_snapshot(
    previous_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """从真实上一交易日快照提取可比前值；不可证明则返回 None。"""
    if not isinstance(previous_snapshot, dict):
        return None

    module = (
        previous_snapshot.get("modules", {}).get("turnover", {})
    )

    if not isinstance(module, dict):
        return None

    if module.get("status") != ModuleStatus.FINAL.value:
        return None

    value = module.get("turnoverToday")

    if value is None:
        return None

    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value_f):
        return None

    return {
        "value": value_f,
        "method": _infer_turnover_method(module),
        "source": list(module.get("source", []) or []),
    }


def _reconcile_day(
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    market_rules: dict[str, Any],
) -> bool:
    """按真实上一交易日重算 turnover 派生字段；仅语义变化时落盘。"""
    module = snapshot.get("modules", {}).get("turnover", {})

    if not isinstance(module, dict):
        return False

    if module.get("status") != ModuleStatus.FINAL.value:
        return False

    today_value = module.get("turnoverToday")

    if today_value is None:
        return False

    try:
        today_value_yi = round(float(today_value), 2)
    except (TypeError, ValueError):
        # 脏数据：不修改该文件，也不作为后续 previous
        return False

    comparison = _turnover_comparison(
        today_value_yi,
        _previous_info_from_snapshot(previous_snapshot),
        market_rules,
    )

    changed = False

    method = _infer_turnover_method(module)

    if method is not None and module.get("method") != method:
        module["method"] = method
        changed = True

    for key in DERIVED_KEYS:
        value = comparison[key]

        if module.get(key) != value:
            module[key] = value
            changed = True

    new_summary = generate_summary(snapshot)

    if snapshot.get("modules", {}).get("summary") != new_summary:
        snapshot["modules"]["summary"] = new_summary
        changed = True

    if not changed:
        return False

    snapshot["generationReason"] = "TURNOVER_CHAIN_RECONCILE"
    finalize_snapshot(snapshot, revision_bump=True)
    return True


def main() -> int:
    from collector.calendar import previous_trading_day

    paths = sorted(
        path
        for year_dir in DAILY_DIR.iterdir()
        if year_dir.is_dir()
        for path in year_dir.glob("*.json")
        if path.stem[:4].isdigit()
    )

    snapshots: dict[str, dict[str, Any]] = {}

    for path in paths:
        snapshot = _read_snapshot(path)

        if snapshot is not None:
            snapshots[path.stem] = snapshot

    market_rules = load_yaml("market-rules.yaml")

    reconciled: list[str] = []

    for path in paths:
        trade_date = path.stem
        snapshot = snapshots.get(trade_date)

        if snapshot is None:
            # 文件损坏：跳过；previous 按日期显式查找，
            # 不会把更早日期误当它的"前一交易日"
            continue

        try:
            previous_date = (
                previous_trading_day(
                    date.fromisoformat(trade_date),
                    fallback_weekday=True,
                ).isoformat()
            )
        except ValueError:
            previous_date = None

        # 真实上一交易日文件缺失（不在 snapshots）或损坏
        # -> previous_snapshot=None -> PREVIOUS_UNAVAILABLE
        previous_snapshot = (
            snapshots.get(previous_date)
            if previous_date
            else None
        )

        changed = _reconcile_day(
            snapshot,
            previous_snapshot,
            market_rules,
        )

        if not changed:
            continue

        written, _ = write_if_changed(snapshot)

        if written:
            reconciled.append(trade_date)

    if not reconciled:
        print("NO_CHANGE")
        return 0

    latest_date = paths[-1].stem
    latest_snapshot = _read_snapshot(daily_path(latest_date))

    if latest_snapshot is not None:
        update_manifest_and_latest(latest_date, latest_snapshot)

    print("RECONCILED " + ",".join(reconciled))
    return 0


if __name__ == "__main__":
    sys.exit(main())
