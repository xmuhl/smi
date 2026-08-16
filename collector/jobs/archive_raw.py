"""⑧ raw archive 任务：每日归档 tracks 数据底座（R7 第四优先级）。

用法：
    python -m collector.jobs.archive_raw --date auto       # 最近交易日
    python -m collector.jobs.archive_raw --date 2026-08-14 # 指定日（历史回补）

退出码：
    0  全部成功、部分成功（可解释 SKIP），或幂等重跑（ALREADY_EXISTS）；
       workflow 允许 stage/commit/deploy。
    1  交易日但零新增且零已存在（全源失败，CI 告警）；
       workflow fail-closed，禁止 stage/commit/deploy。
    2  未分类异常（配置/日历损坏、归档写入、parent fsync、
       strict readback、payload conflict 等）；
       workflow fail-closed，禁止 stage/commit/deploy。
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date

from collector.archive import append_record, count_records
from collector.calendar import is_trading_day
from collector.jobs.common import resolve_target_date
from collector.modules.raw_archive import (
    _expanded_tracks,
    collect_board_close,
    collect_board_flow,
    collect_limit_up_pool,
    collect_membership,
)

KINDS = (
    "track-board-close",
    "track-board-flow",
    "limit-up-pool",
    "track-membership-snapshot",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="SMI raw archive")
    parser.add_argument(
        "--date",
        default="auto",
        help="目标交易日 YYYY-MM-DD 或 auto",
    )
    args = parser.parse_args()

    # 阶段 0：解析目标日（配置/日历损坏属未分类异常 → 2）
    try:
        target = resolve_target_date(args.date)

        if not is_trading_day(
            date.fromisoformat(target),
            fallback_weekday=True,
        ):
            print(f"NOT_TRADING_DAY {target}")
            return 0

        tracks = _expanded_tracks()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 2

    written = 0  # 新增行
    skipped = 0  # 可解释跳过（INVALID / 历史不支持 / 名称缺失 / 概念短路 …）
    already = 0  # 幂等命中（ALREADY_EXISTS，视为成功重跑）
    failed = 0   # 上游抓取异常（FETCH_FAILED，CI 告警候选）

    def _collect_one(label: str, kind: str, result: dict) -> None:
        nonlocal written, skipped, already, failed

        if not result.get("ok"):
            reason = str(result.get("reason", "?"))
            print(f"SKIP {label} {target} reason={reason}")
            skipped += 1
            if reason.startswith("FETCH_FAILED"):
                failed += 1
            return

        ok, reason = append_record(kind, result["record"])

        if ok:
            written += 1
        elif reason == "ALREADY_EXISTS":
            already += 1
        else:
            print(f"SKIP {label} {target} reason={reason}")
            skipped += 1

    # 阶段 1-4：单源失败仅 SKIP（collect 层已把异常包装为 FETCH_FAILED）
    try:
        for track in tracks:
            _collect_one(
                f"board-close {track['trackId']}/{track.get('boardCode')}",
                "track-board-close",
                collect_board_close(target, track),
            )

        for track in tracks:
            _collect_one(
                f"board-flow {track['trackId']}/{track.get('boardCode')}",
                "track-board-flow",
                collect_board_flow(target, track),
            )

        _collect_one(
            "limit-up-pool",
            "limit-up-pool",
            collect_limit_up_pool(target),
        )

        for track in tracks:
            _collect_one(
                f"membership {track['trackId']}/{track.get('boardCode')}",
                "track-membership-snapshot",
                collect_membership(target, track),
            )
    except Exception:  # noqa: BLE001
        # append_record 的持久化/严格回读/payload conflict 等未分类异常：
        # fail-closed → 2。workflow 对非零 rc 禁止 stage/commit/deploy，
        # 避免把 post-replace 未确认工作树发布到 Git 或 Cloudflare。
        traceback.print_exc()
        print("UNCLASSIFIED_FAILURE")
        status = 2
    else:
        status = 0

    print(
        f"ARCHIVE_DONE {target} written={written} skipped={skipped} "
        f"already={already} failures={failed} status={status}"
    )

    for kind in KINDS:
        print(f"  {kind}: {count_records(kind)} records")

    if status == 0 and written == 0 and already == 0 and (skipped + failed) > 0:
        return 1  # 交易日全源失败零写入：CI 告警

    return status


if __name__ == "__main__":
    sys.exit(main())
