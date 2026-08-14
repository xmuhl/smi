"""收盘快照任务：每个交易日收盘后生成当日全景。"""

from __future__ import annotations

import argparse
import sys
import time as _time
from datetime import date, datetime, time

from collector.calendar import is_trading_day
from collector.config import load_yaml
from collector.jobs.common import (
    build_snapshot,
    resolve_target_date,
    update_manifest_and_latest,
    write_if_changed,
)
from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus

# R5-P2-01：任务级有限重试（可重试错误 → 退避重试，最多 4 次）
RETRYABLE_VALIDATION_ERRORS = {
    "REQUIRED_INDEX_MISSING",
    "MARKET_DATE_NOT_VERIFIED",
    "STOCK_UNIVERSE_TOO_SMALL",
}

# 第 2~4 次尝试前的等待秒数（+2min → +5min → +10min）
RETRY_DELAYS_SECONDS = [120, 300, 600]


def _is_retryable(errors: list[str]) -> bool:
    """仅对披露延迟/网络类错误重试；日历、schema 等错误立即 fail-closed。"""
    if not errors:
        return False

    return all(
        error.split(":", 1)[0] in RETRYABLE_VALIDATION_ERRORS
        for error in errors
    )

def _validate_close_snapshot(
    snapshot: dict,
    target: str,
) -> list[str]:
    """执行交易日历之后的第二层市场事实校验。"""
    rules = load_yaml("market-rules.yaml")
    validation_rules = rules.get("validation", {})

    required_indices = {
        str(v)
        for v in validation_rules.get(
            "required_indices",
            ["000001", "399001", "399006"],
        )
    }

    min_stock_count = int(
        validation_rules.get("min_valid_stock_count", 4000)
    )

    validation = snapshot.setdefault("validation", {})
    errors: list[str] = []

    validation["calendarExpectedTradingDay"] = is_trading_day(
        date.fromisoformat(target),
        fallback_weekday=True,
    )

    index_module = snapshot["modules"].get("marketIndex", {})
    index_items = index_module.get("items", [])

    valid_index_codes = {
        str(item.get("code"))
        for item in index_items
        if item.get("close") is not None
    }

    required_present = required_indices.issubset(valid_index_codes)

    validation["requiredIndicesPresent"] = required_present

    turnover = snapshot["modules"].get("turnover", {})

    market_date_verified = (
        index_module.get("status") == ModuleStatus.FINAL.value
        and index_module.get("dataDate") == target
        and turnover.get("status") == ModuleStatus.FINAL.value
        and turnover.get("dataDate") == target
    )

    validation["marketDateVerified"] = market_date_verified

    sentiment = snapshot["modules"].get("sentiment", {})

    counts = [
        sentiment.get("riseCount"),
        sentiment.get("fallCount"),
        sentiment.get("flatCount"),
    ]

    valid_count = sum(
        int(v)
        for v in counts
        if isinstance(v, (int, float))
    )

    universe_ok = valid_count >= min_stock_count
    validation["stockUniverseCheckPassed"] = universe_ok

    if not validation["calendarExpectedTradingDay"]:
        errors.append("CALENDAR_NOT_TRADING_DAY")

    if not required_present:
        errors.append("REQUIRED_INDEX_MISSING")

    if not market_date_verified:
        errors.append("MARKET_DATE_NOT_VERIFIED")

    if not universe_ok:
        errors.append(
            f"STOCK_UNIVERSE_TOO_SMALL:{valid_count}<{min_stock_count}"
        )

    validation["criticalErrors"] = errors

    return errors

def main() -> int:
    parser = argparse.ArgumentParser(description="SMI close snapshot")
    parser.add_argument(
        "--date",
        default="auto",
        help="目标交易日 YYYY-MM-DD 或 auto",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="重新执行采集；不会绕过收盘安全校验",
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="禁用任务级重试（测试用）",
    )
    args = parser.parse_args()

    target = resolve_target_date(args.date)
    target_date = date.fromisoformat(target)

    if not is_trading_day(target_date, fallback_weekday=True):
        print(f"NOT_TRADING_DAY {target}")
        return 0

    now = datetime.now(TZ_SHANGHAI)

    if (
        target == now.date().isoformat()
        and now.time() < time(16, 0)
    ):
        print(f"BEFORE_CLOSE {target}")
        return 2

    attempt = 0
    retry_delays = [] if args.no_retry else RETRY_DELAYS_SECONDS

    while True:
        attempt += 1
        snapshot = build_snapshot(target, legacy=False)
        snapshot["generationReason"] = "CLOSE_SNAPSHOT"

        validation_errors = _validate_close_snapshot(snapshot, target)

        if not validation_errors:
            break

        if attempt > len(retry_delays) or not _is_retryable(validation_errors):
            # 调试用：失败时打印每个模块的状态与错误，便于 GitHub Actions 日志定位
            print(f"VALIDATION_FAILED {target} " + ",".join(validation_errors))
            for name, mod in snapshot["modules"].items():
                print(
                    f"  module={name} status={mod.get('status')} "
                    f"dataDate={mod.get('dataDate')} reason={mod.get('reason','')[:60]} "
                    f"errors={str(mod.get('errors',''))[:200]}"
                )
            return 2

        delay = retry_delays[attempt - 1]
        print(
            f"RETRY_SCHEDULED {target} attempt={attempt + 1} "
            f"delay={delay}s errors={",".join(validation_errors)}"
        )
        _time.sleep(delay)

    changed, _ = write_if_changed(
        snapshot,
        force=args.force,
    )

    if changed:
        update_manifest_and_latest(target, snapshot)
        print(
            f"WRITTEN {target} "
            f"revision={snapshot['revision']}"
        )
    else:
        print(f"NO_CHANGE {target}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

