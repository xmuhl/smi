"""手工补跑任务：指定交易日安全重建快照。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from collector.calendar import is_trading_day
from collector.config import daily_path
from collector.jobs.common import (
    build_snapshot,
    update_manifest_and_latest,
    write_if_changed,
)
from collector.schema import finalize_snapshot
from collector.status import ModuleStatus

def _load_existing(target: str) -> dict | None:
    path = daily_path(target)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

def _merge_preserving_valid_history(
    existing: dict,
    rebuilt: dict,
) -> dict:
    """新采集无法历史重建时，不允许空值/ERROR 覆盖已有 FINAL。"""
    existing_modules = existing.get("modules", {})
    rebuilt_modules = rebuilt.get("modules", {})

    for name, old_module in existing_modules.items():
        new_module = rebuilt_modules.get(name)

        if not isinstance(new_module, dict):
            rebuilt_modules[name] = old_module
            continue

        old_status = old_module.get("status")
        new_status = new_module.get("status")

        if (
            old_status == ModuleStatus.FINAL.value
            and new_status
            in {
                ModuleStatus.PENDING.value,
                ModuleStatus.STALE.value,
                ModuleStatus.UNAVAILABLE.value,
                ModuleStatus.ERROR.value,
            }
        ):
            rebuilt_modules[name] = old_module

    return rebuilt

def main() -> int:
    parser = argparse.ArgumentParser(description="SMI manual backfill")
    parser.add_argument(
        "--date",
        required=True,
        help="目标交易日 YYYY-MM-DD",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新调用可用历史接口",
    )
    parser.add_argument(
        "--replace-legacy",
        action="store_true",
        help="显式允许替换 Legacy 基线；默认禁止",
    )
    args = parser.parse_args()

    target = date.fromisoformat(args.date).isoformat()

    if not is_trading_day(
        date.fromisoformat(target),
        fallback_weekday=True,
    ):
        print(f"NOT_TRADING_DAY {target}")
        return 2

    existing = _load_existing(target)

    if (
        existing
        and existing.get("meta", {}).get("legacy") is True
        and not args.replace_legacy
    ):
        print(f"LEGACY_PROTECTED {target}")
        return 0

    rebuilt = build_snapshot(
        target,
        legacy=False,
    )

    if (
        existing is None
        and rebuilt["modules"]["marketIndex"].get("status")
        != ModuleStatus.FINAL.value
    ):
        print(f"HISTORICAL_MARKET_DATA_UNAVAILABLE {target}")
        return 2

    if existing is not None:
        rebuilt = _merge_preserving_valid_history(
            existing,
            rebuilt,
        )

        from collector.calculators.summary import generate_summary

        rebuilt["modules"]["summary"] = generate_summary(rebuilt)

    rebuilt["generationReason"] = "MANUAL_BACKFILL"
    finalize_snapshot(rebuilt, revision_bump=True)

    changed, _ = write_if_changed(
        rebuilt,
        force=args.force,
    )

    if changed:
        update_manifest_and_latest(target, rebuilt)
        print(
            f"WRITTEN {target} "
            f"revision={rebuilt['revision']}"
        )
    else:
        print(f"NO_CHANGE {target}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
