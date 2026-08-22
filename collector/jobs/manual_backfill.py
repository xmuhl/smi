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

def _merge_partial_sentiment(
    old_module: dict,
    new_module: dict,
) -> dict:
    """合并历史情绪 PARTIAL：已取得的字段只增不减（R8-P1-01）。"""
    merged = dict(new_module)

    for field in (
        "nonStLimitUpCount",
        "stLimitUpCount",
        "nonStLimitDownCount",
        "stLimitDownCount",
        "brokenLimitCount",
    ):
        if (
            merged.get(field) is None
            and old_module.get(field) is not None
        ):
            merged[field] = old_module[field]

    merged["status"] = ModuleStatus.PARTIAL.value
    return merged


def _merge_preserving_valid_history(
    existing: dict,
    rebuilt: dict,
    replace_modules: frozenset[str] = frozenset(),
) -> dict:
    """历史回补合并：禁止已持久化的高质量事实被较低状态降级覆盖。

    R8-P1-01：保护集必须覆盖 PARTIAL——已有 FINAL 只能被新的 FINAL 修订；
    已有 PARTIAL 是已取得的历史事实，非 FINAL 的重建不得把非空字段抹掉。
    R22-DEF-01：replace_modules 为显式豁免清单（如 tracks 语义修订）——
    列名模块放弃保护，允许重建结果整体替换（含 PARTIAL→PARTIAL 降换）；
    这是人工显式声明的"该模块旧内容即缺陷"路径，不改变默认保护。
    """
    existing_modules = existing.get("modules", {})
    rebuilt_modules = rebuilt.get("modules", {})

    for name, old_module in existing_modules.items():
        new_module = rebuilt_modules.get(name)

        if name in replace_modules:
            continue

        if not isinstance(new_module, dict):
            rebuilt_modules[name] = old_module
            continue

        old_status = old_module.get("status")
        new_status = new_module.get("status")

        # 已有 FINAL 只能被新的 FINAL 修订；任何非 FINAL 都不得降级覆盖。
        if (
            old_status == ModuleStatus.FINAL.value
            and new_status != ModuleStatus.FINAL.value
        ):
            rebuilt_modules[name] = old_module
            continue

        # 已有 PARTIAL 是已取得的历史事实：
        # 1) 新 FINAL 可以升级；
        # 2) 新 PARTIAL 只允许补充，不允许把已有非空字段抹成 None；
        # 3) PENDING/STALE/UNAVAILABLE/ERROR 不得降级覆盖。
        if old_status == ModuleStatus.PARTIAL.value:
            if new_status == ModuleStatus.FINAL.value:
                continue

            if (
                new_status == ModuleStatus.PARTIAL.value
                and name == "sentiment"
            ):
                rebuilt_modules[name] = _merge_partial_sentiment(
                    old_module,
                    new_module,
                )
                continue

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
    parser.add_argument(
        "--replace-modules",
        default="",
        help="显式放弃合并保护的模块名（逗号分隔，如 tracks）；"
        "用于语义修订时整体替换已持久化的缺陷内容（R22-DEF-01）",
    )
    args = parser.parse_args()

    target = date.fromisoformat(args.date).isoformat()

    # R9-P2-04：manual_backfill 定位为"仅历史日工具"；
    # 当前交易日的人工重跑统一走 close_snapshot --date TODAY --force，
    # 以受 16:00 收盘安全门禁保护。
    from datetime import datetime

    from collector.schema import TZ_SHANGHAI

    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if target >= today:
        print(
            f"BACKFILL_REQUIRES_PAST_DATE {target}"
        )
        return 2

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
            replace_modules=frozenset(
                m.strip()
                for m in args.replace_modules.split(",")
                if m.strip()
            ),
        )

        from collector.calculators.summary import generate_summary

        rebuilt["modules"]["summary"] = generate_summary(rebuilt)

    rebuilt["generationReason"] = "MANUAL_BACKFILL"
    finalize_snapshot(rebuilt, revision_bump=True)

    changed, _ = write_if_changed(
        rebuilt,
        force=args.force,
    )

    from collector.jobs.common import ensure_derived_state_consistent

    ensure_derived_state_consistent(target, rebuilt)

    if changed:
        print(
            f"WRITTEN {target} "
            f"revision={rebuilt['revision']}"
        )
    else:
        print(f"NO_CHANGE {target}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
