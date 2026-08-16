"""单进程回补循环：逐交易日调用 manual_backfill 核心流程。

背景：原有 tmp/run_backfill.py 用 subprocess 逐日调用 manual_backfill，每日子
进程冷启动，无法共享 sectors 的 _THS_HIST_CACHE（THS 板块历史指数缓存），且
THS 并发 10 触发限流后单日 30+ 分钟。本循环改为在同一个进程内连续回补多个
历史交易日，并在循环开始时启用板块历史缓存，使每只板块的 THS 历史指数只拉
取一次（跨日复用），把 19 日 × 465 次 THS 请求压缩为约 465 次。

为让每只板块的"首次大窗口拉取"覆盖其后的全部回补日（起点锚定 2026-06-15、
终点=当日），本循环按交易日**降序**（--end → --start）处理：首个（最新）日的
一次全窗口拉取即可覆盖所有更早的历史回补日，之后的日子全部命中缓存。

失败日记录并继续下一天，最后汇总打印 FAILED 清单。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from collector.calendar import is_trading_day
from collector.jobs import manual_backfill
from collector.jobs.common import (
    build_snapshot,
    ensure_derived_state_consistent,
    write_if_changed,
)
from collector.modules.sectors import (
    _ths_hist_cache_clear,
    _ths_hist_cache_enable,
)
from collector.schema import finalize_snapshot
from collector.status import ModuleStatus


def _backfill_one(
    target: str,
    *,
    force: bool = False,
    replace_legacy: bool = False,
) -> int:
    """等价于 manual_backfill.main() 对单个目标日的核心流程。

    逻辑移植自 collector/jobs/manual_backfill.py 的 main()（解析日期→载入
    existing→build_snapshot→merge→generate_summary→finalize→write_if_changed
    →ensure_derived_state_consistent），并保持与 manual_backfill 一致的输出文案
    （WRITTEN/NO_CHANGE/LEGACY_PROTECTED 等）与退出语义（0 成功，2 拒绝）。
    复用 manual_backfill 的 _load_existing/_merge_preserving_valid_history，
    避免复制业务语义；manual_backfill.py 本身不作任何修改。
    """
    from datetime import datetime

    from collector.schema import TZ_SHANGHAI

    today = datetime.now(TZ_SHANGHAI).date().isoformat()

    if target >= today:
        print(f"BACKFILL_REQUIRES_PAST_DATE {target}")
        return 2

    if not is_trading_day(
        date.fromisoformat(target),
        fallback_weekday=True,
    ):
        print(f"NOT_TRADING_DAY {target}")
        return 2

    existing = manual_backfill._load_existing(target)

    if (
        existing
        and existing.get("meta", {}).get("legacy") is True
        and not replace_legacy
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
        rebuilt = manual_backfill._merge_preserving_valid_history(
            existing,
            rebuilt,
        )

        from collector.calculators.summary import generate_summary

        rebuilt["modules"]["summary"] = generate_summary(rebuilt)

    rebuilt["generationReason"] = "MANUAL_BACKFILL"
    finalize_snapshot(rebuilt, revision_bump=True)

    changed, _ = write_if_changed(
        rebuilt,
        force=force,
    )

    ensure_derived_state_consistent(target, rebuilt)

    if changed:
        print(
            f"WRITTEN {target} "
            f"revision={rebuilt['revision']}"
        )
    else:
        print(f"NO_CHANGE {target}")

    return 0


def _trading_days(start: str, end: str) -> list[str]:
    """[start, end] 区间（含边界）内全部交易日，降序排列。

    降序使首个（最新）日触发每只板块的首次大窗口拉取，其返回窗口覆盖其后
    全部更早的历史回补日，后续交易日全部命中 sectors 跨日缓存。
    """
    days: list[str] = []
    day = date.fromisoformat(end)
    stop = date.fromisoformat(start)

    while day >= stop:
        if is_trading_day(day):
            days.append(day.isoformat())
        day = date.fromordinal(day.toordinal() - 1)

    return days


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SMI single-process backfill loop"
    )
    parser.add_argument(
        "--start",
        default="2026-07-18",
        help="回补起始交易日 YYYY-MM-DD（含）",
    )
    parser.add_argument(
        "--end",
        default="2026-08-13",
        help="回补终止交易日 YYYY-MM-DD（含）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新调用可用历史接口（透传 _backfill_one）",
    )
    parser.add_argument(
        "--replace-legacy",
        action="store_true",
        help="显式允许替换 Legacy 基线（透传 _backfill_one）",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start).isoformat()
    end = date.fromisoformat(args.end).isoformat()

    if end < start:
        print(f"INVALID_RANGE {start}..{end}")
        return 2

    days = _trading_days(start, end)

    print(f"TARGET_DAYS {len(days)} {start}..{end}", flush=True)

    # 启用跨日板块历史缓存，使每只板块的 THS 指数只拉取一次；
    # 结束后幂等停用并清空，避免污染后续非循环调用/单测。
    _ths_hist_cache_enable(True)
    _ths_hist_cache_clear()

    failed: list[tuple[str, int, str]] = []

    try:
        for day in days:
            print(f"=== {day} ===", flush=True)
            code = _backfill_one(
                day,
                force=args.force,
                replace_legacy=args.replace_legacy,
            )
            if code != 0:
                failed.append((day, code, "see day output"))
    finally:
        _ths_hist_cache_enable(False)
        _ths_hist_cache_clear()

    if failed:
        print(f"FAILED {failed}", flush=True)
    else:
        print("FAILED []", flush=True)

    print("DONE", flush=True)

    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
