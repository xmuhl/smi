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
from datetime import date, datetime, time

from collector.archive import append_record, count_records
from collector.calendar import is_trading_day
from collector.jobs.common import resolve_target_date
from collector.schema import TZ_SHANGHAI
from collector.modules.raw_archive import (
    _expanded_tracks,
    collect_board_close,
    collect_board_close_history,
    collect_board_flow,
    collect_industry_universe,
    collect_limit_up_pool,
    collect_membership,
)

KINDS = (
    "track-board-close",
    "track-board-flow",
    "limit-up-pool",
    "track-membership-snapshot",
    "industry-universe-snapshot",
)

# 历史回补判定：板块 close 归档中早于 (D - 该天数) 的记录不存在 → 需要回补
_BACKFALL_LOOKBACK_DAYS = 10


def _boards_needing_history(
    target: str,
    expanded_tracks: list[dict],
) -> list[dict]:
    """种子（已展开为单板行）+ 动态候选中 close 历史不足的板块（R12-PLAN-3）。

    入参为 _expanded_tracks() 的 camelCase 输出（composite 已拆成子板行）；
    返回 collect_board_close_history 可用的板块描述列表；
    候选读取失败时退化为仅种子（fail-closed，不阻断主流程）。
    """
    from datetime import date, timedelta

    from collector import archive as _archive
    from collector.modules.tracks import (
        dynamic_track_identity,
        select_candidate_boards,
    select_discovery_pool,
    select_scoring_pool,
    )

    threshold = (
        date.fromisoformat(target) - timedelta(days=_BACKFALL_LOOKBACK_DAYS)
    ).isoformat()

    existing_keys: set[tuple[str, str]] = set()
    for rec in _archive.read_records("track-board-close"):
        if str(rec.get("tradeDate") or "") <= threshold:
            existing_keys.add(
                (
                    str(rec.get("trackId") or ""),
                    str(rec.get("boardCode") or ""),
                )
            )

    boards: list[dict] = []

    for track in expanded_tracks:
        index_name_ths = str(track.get("indexNameThs") or "").strip()
        board_code = str(track.get("boardCode") or "").strip()
        if not index_name_ths or not board_code:
            continue
        if (str(track.get("trackId") or ""), board_code) in existing_keys:
            continue
        boards.append(
            {
                "trackId": str(track.get("trackId") or ""),
                "trackName": str(track.get("trackName") or ""),
                "boardType": str(track.get("boardType") or ""),
                "boardCode": board_code,
                "boardName": str(track.get("boardName") or ""),
                "indexNameThs": index_name_ths,
            }
        )

    # R13-P2-01 预热池：正式评分池（迟滞选池）∪ 发现池（成交额前
    # prewarmRankMax，不筛净流入）一并回补 close 历史，消除首次入选后
    # 才开始累积历史的冷启动；预热数据不直接参与评分。
    try:
        seen: set[tuple[str, str]] = set()
        for cand in (
            select_scoring_pool(target) + select_discovery_pool(target)
        ):
            identity = dynamic_track_identity(cand)
            key = (identity["trackId"], identity["boardCode"])
            if key in existing_keys or key in seen:
                continue
            seen.add(key)
            boards.append(
                {
                    "trackId": identity["trackId"],
                    "trackName": identity["boardName"],
                    "boardType": identity["boardType"],
                    "boardCode": identity["boardCode"],
                    "boardName": identity["boardName"],
                    "indexNameThs": identity["boardName"],
                }
            )
    except Exception:  # noqa: BLE001 候选读取失败不阻断种子回补
        pass

    return boards


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

        # 2026-08-28：盘前守卫——GitHub 调度劣化时 cron 补发可延迟数小时
        # （08-27 事故实测 7~10h），凌晨执行时 auto 解析到未收盘日；THS
        # 「即时」资金流/涨停池盘前返回的是昨日收盘值，照常归档会把旧值
        # 打成今日标签（450fd9a 脏数据根因，7 行 03:14 capturedAt 的
        # 08-28 记录，次日 post-close 重采触发 payload conflict 炸 rc=2）。
        # 与 close_snapshot 的 BEFORE_CLOSE 同阈：16:00 CST 后才允许采当日。
        now = datetime.now(TZ_SHANGHAI)

        if target == now.date().isoformat() and now.time() < time(16, 0):
            print(f"BEFORE_CLOSE {target}")
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

        # 阶段 5：行业板块全景当日快照（动态选池监测口径底座，R12-PLAN-3）
        # N-1（复核修订）：close-snapshot 侧已预写当日 universe（P1-3），
        # 这里重拉若数值微差会触发 append_record 的 payload conflict
        # RuntimeError → rc=2 当日全丢。已存在即跳过（保留先写版本）；
        # 残余冲突也降级 SKIP 而非炸整个 job。
        from collector import archive as _archive_mod

        if _archive_mod.read_records(
            "industry-universe-snapshot", trade_date=target
        ):
            print(f"SKIP industry-universe {target} reason=ALREADY_ARCHIVED")
            already += 1
        else:
            try:
                _collect_one(
                    "industry-universe",
                    "industry-universe-snapshot",
                    collect_industry_universe(target),
                )
            except RuntimeError as exc:
                print(
                    f"SKIP industry-universe {target} "
                    f"reason=CONFLICT_DEGRADED:{str(exc)[:120]}"
                )
                skipped += 1

        # 阶段 6：候选/种子板块 THS 历史回补（幂等；仅历史不足的板块）
        # 注意 select_candidate_boards 消费的是刚写入的 universe 归档。
        for board in _boards_needing_history(target, tracks):
            result = collect_board_close_history(target, board)
            if not result.get("ok"):
                print(
                    f"SKIP history {board['trackId']}/{board.get('boardCode')} "
                    f"{target} reason={result.get('reason')}"
                )
                skipped += 1
                if str(result.get("reason", "")).startswith("FETCH_FAILED"):
                    failed += 1
                continue
            for record in result.get("records", []):
                ok, reason = append_record("track-board-close", record)
                if ok:
                    written += 1
                elif reason == "ALREADY_EXISTS":
                    already += 1
                else:
                    print(
                        f"SKIP history {board['trackId']}/{board.get('boardCode')} "
                        f"{target} reason={reason}"
                    )
                    skipped += 1
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
