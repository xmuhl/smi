"""T+1 校正任务：补上最近一个已有历史快照的两融数据。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

from collector.config import DAILY_DIR, daily_path
from collector.jobs.common import (
    update_manifest_and_latest,
    write_if_changed,
)
from collector.schema import TZ_SHANGHAI, finalize_snapshot
from collector.status import ModuleStatus

def _available_snapshot_dates_before_today() -> list[str]:
    today = datetime.now(TZ_SHANGHAI).date().isoformat()
    dates: list[str] = []

    if not DAILY_DIR.exists():
        return dates

    for year_dir in DAILY_DIR.iterdir():
        if not year_dir.is_dir():
            continue

        for path in year_dir.glob("*.json"):
            value = path.stem

            try:
                date.fromisoformat(value)
            except ValueError:
                continue

            if value < today:
                dates.append(value)

    return sorted(set(dates), reverse=True)

def _resolve_reconcile_target(raw: str) -> str | None:
    """auto 直接从已有快照寻找最近一个 T-1 快照，不再次调用日历回退。"""
    if raw and raw != "auto":
        return date.fromisoformat(raw).isoformat()

    candidates = _available_snapshot_dates_before_today()

    if not candidates:
        return None

    for candidate in candidates:
        path = daily_path(candidate)

        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except (OSError, ValueError):
            continue

        margin = snapshot.get("modules", {}).get("margin", {})

        if margin.get("status") != ModuleStatus.FINAL.value:
            return candidate

    return candidates[0]

def main() -> int:
    parser = argparse.ArgumentParser(description="SMI t1 reconcile")
    parser.add_argument(
        "--date",
        default="auto",
        help="目标交易日 YYYY-MM-DD 或 auto",
    )
    args = parser.parse_args()

    target = _resolve_reconcile_target(args.date)

    if target is None:
        print("NO_SNAPSHOT")
        return 0

    path = daily_path(target)

    if not path.exists():
        print(f"NO_SNAPSHOT {target}")
        return 0

    with open(path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    previous_margin = snapshot["modules"].get("margin", {})

    if previous_margin.get("status") == ModuleStatus.FINAL.value:
        from collector.jobs.common import ensure_derived_state_consistent

        ensure_derived_state_consistent(target, snapshot)
        print(f"ALREADY_FINAL {target}")
        return 0

    from collector.modules.margin import collect_margin

    updated_margin = collect_margin(
        target,
        is_t1=True,
    )

    snapshot["modules"]["margin"] = updated_margin

    from collector.calculators.summary import generate_summary

    snapshot["modules"]["summary"] = generate_summary(snapshot)
    snapshot["generationReason"] = "T1_RECONCILE"

    finalize_snapshot(
        snapshot,
        revision_bump=True,
    )

    changed, _ = write_if_changed(snapshot)

    from collector.jobs.common import ensure_derived_state_consistent

    ensure_derived_state_consistent(target, snapshot)

    if changed:
        print(
            f"UPDATED {target} "
            f"margin={updated_margin.get('status')} "
            f"revision={snapshot['revision']}"
        )
    else:
        print(f"NO_CHANGE {target}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
