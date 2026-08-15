"""历史回补后重算成交额跨日派生链（R9-P2-01-B）。

不重新抓网络：按日期顺序读取每日 daily JSON，仅在前后 method 一致时重算
turnoverPrevious / turnoverDelta / turnoverChangePct / volumeState，
并重算 summary 后持久化；最后重算 manifest/latest/status。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from collector.calculators.summary import generate_summary
from collector.config import DAILY_DIR, daily_path
from collector.jobs.common import (
    update_manifest_and_latest,
    write_if_changed,
)
from collector.modules.turnover import (
    TURNOVER_METHOD,
    _infer_turnover_method,
)
from collector.schema import finalize_snapshot


def _read_snapshot(path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _reconcile_day(
    snapshot: dict[str, Any],
    previous_method: str | None,
    previous_value: float | None,
) -> bool:
    """重算单个日的跨日派生字段；返回是否发生语义变化。"""
    module = snapshot.get("modules", {}).get(
        "turnover",
        {},
    )

    if not isinstance(module, dict):
        return False

    today_value = module.get("turnoverToday")

    if today_value is None:
        return False

    method = _infer_turnover_method(module)

    # 回填 method 字段（历史重生成早于 method 引入的版本缺少该字段）
    if method is not None and module.get("method") != method:
        module["method"] = method

    comparable = (
        previous_value is not None
        and method == TURNOVER_METHOD
        and previous_method == TURNOVER_METHOD
    )

    if comparable:
        module["turnoverPrevious"] = round(
            previous_value,
            2,
        )
        delta = round(
            float(today_value) - previous_value,
            2,
        )
        module["turnoverDelta"] = delta

        if previous_value > 0:
            module["turnoverChangePct"] = round(
                delta / previous_value * 100,
                2,
            )
        else:
            module["turnoverChangePct"] = None

        pct = module["turnoverChangePct"]
        rules = {
            "EXPANSION": 5.0,
            "CONTRACTION": -5.0,
        }
        if pct is not None:
            if pct >= rules["EXPANSION"]:
                module["volumeState"] = "EXPANSION"
            elif pct <= rules["CONTRACTION"]:
                module["volumeState"] = "CONTRACTION"
            else:
                module["volumeState"] = "FLAT"
    else:
        module["turnoverPrevious"] = None
        module["turnoverDelta"] = None
        module["turnoverChangePct"] = None
        module["volumeState"] = "UNKNOWN"

    module["previousMethod"] = previous_method
    module["comparisonStatus"] = (
        "COMPARABLE"
        if comparable
        else (
            "PREVIOUS_METHOD_MISMATCH"
            if previous_value is not None
            else "PREVIOUS_UNAVAILABLE"
        )
    )

    snapshot["modules"]["summary"] = (
        generate_summary(snapshot)
    )
    snapshot["generationReason"] = (
        "TURNOVER_CHAIN_RECONCILE"
    )
    finalize_snapshot(
        snapshot,
        revision_bump=True,
    )

    return True


def main() -> int:
    paths = sorted(
        path
        for year_dir in DAILY_DIR.iterdir()
        if year_dir.is_dir()
        for path in year_dir.glob("*.json")
        if path.stem[:4].isdigit()
    )

    previous_method: str | None = None
    previous_value: float | None = None
    reconciled: list[str] = []

    for path in paths:
        snapshot = _read_snapshot(path)

        if snapshot is None:
            continue

        module = (
            snapshot.get("modules", {})
            .get("turnover", {})
        )
        current_value = module.get(
            "turnoverToday"
        )

        if current_value is None:
            previous_method = None
            previous_value = None
            continue

        changed = _reconcile_day(
            snapshot,
            previous_method,
            previous_value,
        )

        if changed:
            written, _ = write_if_changed(
                snapshot
            )

            if written:
                reconciled.append(path.stem)

        previous_method = _infer_turnover_method(
            module
        )
        previous_value = float(current_value)

    if not reconciled:
        print("NO_CHANGE")
        return 0

    latest_date = paths[-1].stem
    latest_snapshot = _read_snapshot(
        daily_path(latest_date)
    )

    if latest_snapshot is not None:
        update_manifest_and_latest(
            latest_date,
            latest_snapshot,
        )

    print("RECONCILED " + ",".join(reconciled))
    return 0


if __name__ == "__main__":
    sys.exit(main())
