"""模块 8：主赛道监测真实采集器（消费 daily raw archive，R7 第八优先级）。

设计要点：
- 只读 ✱ daily raw archive（collector.archive.read_records），绝不联网、不伪造；
- 每个 track 先算出"结构化原始指标"，再交给 calculators.tracks.score_tracks
  产出 score/coveragePct/decision，最后映射为 16 列 typed 输出项；
- 诚实缺口 fail-closed：沪深300 无 archive 源（RPS/超额基准）、红盘占比无当日
  行情源时置 None 并计入 coverage 缺口，在 errors 说明中注明
  HS300_SEED_UNAVAILABLE / RED_RATIO_SOURCE_UNAVAILABLE，绝不填 0 冒充。
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from collector import archive as _archive
from collector.config import load_yaml
from collector.status import ModuleStatus

CONFIG_VERSION = "3.4"
EFFECTIVE_FROM = "2026-07-20"
EFFECTIVE_TO = "2026-12-31"
SOURCE_SYSTEM = "SELF"

# coverage 口径：11 个可计数指标槽位（对应 16 列中可"实现/未实现"二分的列）。
# 这些键与 collect_tracks 中结构化原始指标 raw 的 snake_case 键一一对应。
_INDICATOR_FIELDS = (
    "turnover_rank",
    "main_net_inflow",
    "continuous_inflow_days",
    "ma_data",
    "rps60",
    "excess_return_20d_pct",
    "limit_up_count",
    "ladder_completeness",
    "red_stock_ratio",
    "core_catalyst",
    "earnings_realization",
)

# 模块错误/说明码
ERR_HS300_SEED_UNAVAILABLE = "HS300_SEED_UNAVAILABLE"
ERR_RED_RATIO_SOURCE_UNAVAILABLE = "RED_RATIO_SOURCE_UNAVAILABLE"


def _finite(value: Any) -> bool:
    """有限数值（排除 bool/None/字符串/NaN/Inf）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _is_missing(value: Any) -> bool:
    """指标是否"实现"：None 或空串视为未实现（数据不足/诚实缺口）。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _sorted_by_date(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 tradeDate 升序排（跨年份/跨月按 ISO 字符串排序即正确）。"""
    return sorted(
        records,
        key=lambda r: str(r.get("tradeDate", "")),
    )


def _group_close_by_board(
    close_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """按 (trackId,boardCode) 分组 close 序列（每日行情记录），升序。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for rec in close_records:
        track_id = str(rec.get("trackId") or "")
        board_code = str(rec.get("boardCode") or "")
        key = f"{track_id}::{board_code}"
        grouped.setdefault(key, []).append(rec)
    for key in grouped:
        grouped[key] = _sorted_by_date(grouped[key])
    return grouped


def _board_close_series(
    per_board: dict[str, list[dict[str, Any]]],
    track_id: str,
    board_code: str,
) -> list[dict[str, Any]]:
    return per_board.get(f"{track_id}::{board_code}", [])


def _track_board_descs(tc: dict[str, Any]) -> list[dict[str, Any]]:
    """返回某赛道主板块描述列表：非 composite 返回单板 weight=1；composite 返回两个子板。"""
    if tc.get("composite"):
        return [
            {
                "boardCode": str(sub.get("code") or ""),
                "indexNameThs": sub.get("index_name_ths", ""),
                "expectedName": sub.get("name", ""),
                "weight": float(sub.get("weight", 0.5)),
            }
            for sub in tc["composite"]
        ]
    return [
        {
            "boardCode": str(tc.get("board_code") or ""),
            "indexNameThs": tc.get("index_name_ths", ""),
            "expectedName": tc.get("expected_name", ""),
            "weight": 1.0,
        }
    ]


def _track_match_names(tc: dict[str, Any]) -> list[str]:
    """该赛道用于涨停池匹配的板块名集合（index_name_ths、expected_name、复合子板名）。"""
    names: list[str] = []
    for d in _track_board_descs(tc):
        if d["indexNameThs"]:
            names.append(d["indexNameThs"].strip())
        if d["expectedName"]:
            names.append(d["expectedName"].strip())
    main_ths = (tc.get("index_name_ths") or "").strip()
    main_exp = (tc.get("expected_name") or "").strip()
    if main_ths:
        names.append(main_ths)
    if main_exp:
        names.append(main_exp)
    # 去重保序
    seen: set[str] = set()
    dedup: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            dedup.append(n)
    return dedup


def _combine_close_series(
    per_board: dict[str, list[dict[str, Any]]],
    track_id: str,
    descs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把 (可能多个) 子板块 close 序列合成为一条每日序列（按日升序）。

    - 单板：直接用该板序列等价副本；
    - composite：每天取各子板 close 按 weight 加权均值（缺任一天则该天剔除）。
    """
    if len(descs) == 1:
        series = _board_close_series(per_board, track_id, descs[0]["boardCode"])
        return [dict(r) for r in series]

    by_date: dict[str, dict[str, Any]] = {}
    for d in descs:
        sub = _board_close_series(per_board, track_id, d["boardCode"])
        for rec in sub:
            dt = str(rec.get("tradeDate") or "")
            if not dt:
                continue
            by_date.setdefault(dt, {})[d["boardCode"]] = rec

    combined: list[dict[str, Any]] = []
    for dt in sorted(by_date.keys()):
        row: dict[str, Any] = {"tradeDate": dt}
        partial = False
        for d in descs:
            rec = by_date.get(dt, {}).get(d["boardCode"])
            if rec is None:
                partial = True
                break
        if partial:
            continue
        for field in ("open", "high", "low", "close", "volume", "amount"):
            vals = []
            for d in descs:
                rec = by_date[dt][d["boardCode"]]
                v = rec.get(field)
                fv = _to_float(v)
                vals.append(d["weight"] * fv if fv is not None else fv)
            vals = [x for x in vals if x is not None]
            if vals and all(x is not None for x in vals):
                row[field] = sum(vals)
            else:
                row[field] = None
        combined.append(row)
    return combined


def _compute_ma(
    series: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """最近 20 根 close → (close, ma5, ma10, ma20)；不足 20 根返回 None。"""
    closes = [_to_float(r.get("close")) for r in series]
    closes = [c for c in closes if c is not None]
    if len(closes) < 20:
        return None
    tail = closes[-20:]
    ma5 = sum(tail[-5:]) / 5.0
    ma10 = sum(tail[-10:]) / 10.0
    ma20 = sum(tail) / 20.0
    return {
        "close": tail[-1],
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
    }


def _ma_alignment_label(ma: dict[str, Any] | None) -> str | None:
    """多头排列判定：ma5>ma10>ma20 且 close>ma5 → '是'，否则 '否'；无数据 → None。"""
    if ma is None:
        return None
    close = ma["close"]
    if close > ma["ma5"] and ma["ma5"] > ma["ma10"] and ma["ma10"] > ma["ma20"]:
        return "是"
    return "否"


def _sixty_day_return(
    series: list[dict[str, Any]],
) -> float | None:
    """最近 60 日收益 = close(D)/close(D-60)-1；不足 61 根 → None。"""
    closes = [_to_float(r.get("close")) for r in series]
    closes = [c for c in closes if c is not None]
    if len(closes) < 61:
        return None
    return closes[-1] / closes[-61] - 1.0


def _rps_percentile(returns: dict[str, float], key: str) -> float | None:
    """给定全 universe 的 60 日收益映射，返回该 board 的收益百分位（0~100）。

    百分位 = 收益 <= 本board 的 board 数 / 总数 * 100；最强 ≈ 100。
    universe<2 → None。
    """
    if len(returns) < 2 or key not in returns:
        return None
    value = returns[key]
    count = len(returns)
    low_count = sum(1 for v in returns.values() if v <= value)
    return round(low_count / count * 100, 1)


def _five_day_amount(
    series: list[dict[str, Any]],
) -> float | None:
    """近 5 日 amount 合计；不足 5 根有效 amount → None。"""
    amounts = [_to_float(r.get("amount")) for r in series]
    amounts = [a for a in amounts if a is not None]
    if len(amounts) < 5:
        return None
    return sum(amounts[-5:])


def _turnover_rank(amounts: dict[str, float], key: str) -> int | None:
    """近 5 日 amount 合计在 universe 中的降序名次（1=最大）；数据不足 → None。"""
    if len(amounts) < 2 or key not in amounts:
        return None
    rank = 1
    for other, val in amounts.items():
        if other != key and val > amounts[key]:
            rank += 1
    return rank


def _main_net_inflow(
    flow_records: list[dict[str, Any]],
    track_id: str,
    board_code: str,
    trade_date: str,
) -> float | None:
    """track-board-flow tradeDate==D 的 mainNetInflow（亿元）。"""
    for rec in flow_records:
        if (
            str(rec.get("tradeDate") or "") == trade_date
            and str(rec.get("trackId") or "") == track_id
            and str(rec.get("boardCode") or "") == board_code
        ):
            return _to_float(rec.get("mainNetInflow"))
    return None


def _continuous_inflow_days(
    flow_records: list[dict[str, Any]],
    track_id: str,
    board_code: str,
    trade_date: str,
) -> int:
    """flow 序列（<=D 降序）连续 >0 天数；D 行必须存在且 >0，否则 0。

    合并在 collect 层完成（composite 用两个子板当日传入日流量加权合成后判断）。
    """
    # 取该板全部 flow 行（<=D 由调用方已过滤 trade_date）。
    rows = [
        rec
        for rec in flow_records
        if str(rec.get("trackId") or "") == track_id
        and str(rec.get("boardCode") or "") == board_code
    ]
    rows = _sorted_by_date(rows)  # 升序
    rows = [
        {
            "tradeDate": str(r.get("tradeDate") or ""),
            "value": _to_float(r.get("mainNetInflow")),
        }
        for r in rows
        if _to_float(r.get("mainNetInflow")) is not None
    ]
    # 连续计数：从最新日往回数，只计入 <= trade_date
    days = 0
    for rec in reversed(rows):
        if rec["tradeDate"] > trade_date:
            continue
        # 遇到严格早于 D 的断档行之前计数；D 必须 >0
        if rec["tradeDate"] == trade_date and rec["value"] <= 0:
            return 0
        if rec["value"] <= 0:
            break
        days += 1
    # 若 D 行缺失/<=0，直接 0（由上面 D 判断兜底；若 D 根本不存在 rows 则不是连续）
    if not any(rec["tradeDate"] == trade_date and rec["value"] > 0 for rec in rows):
        return 0
    return days


def _limit_up_daily(
    pool_records: list[dict[str, Any]],
    trade_date: str,
) -> list[dict[str, Any]] | None:
    """返回 tradeDate==D 的涨停池 items；D 无 pool 记录 → None（数据缺口）。"""
    for rec in pool_records:
        if str(rec.get("tradeDate") or "") != trade_date:
            continue
        items = rec.get("items")
        if isinstance(items, list):
            return items
    return None


def _limit_up_match(
    item: dict[str, Any],
    match_names: list[str],
) -> bool:
    """判断涨停项是否属于某赛道：按其 所属行业/行业 字段或名称命中任一板块名。"""
    industry_candidates: list[str] = []
    industry_candidates.append(str(item.get("所属行业") or ""))
    industry_candidates.append(str(item.get("行业") or ""))
    industry_candidates.append(str(item.get("industry") or ""))
    name = str(item.get("name") or "")

    for cand in industry_candidates:
        if not cand:
            continue
        for mn in match_names:
            if mn and (mn in cand or cand in mn):
                return True
    for mn in match_names:
        if mn and (mn in name or name in mn):
            return True
    return False


def _limit_up_stats(
    pool_items: list[dict[str, Any]] | None,
    match_names: list[str],
) -> tuple[int | None, dict[str, int] | None, str | None]:
    """返回 (limitUpCount, ladderCounts, ladderCompleteness)。

    - pool 无 data（None）→ (None, None, None) 诚缺口；
    - pool 有 data → 命中数；ladderCounts 按连板数分桶；ladderCompleteness=N连板/无连板。
    """
    if pool_items is None:
        return None, None, None
    matched = [item for item in pool_items if _limit_up_match(item, match_names)]
    limit_up_count = len(matched)
    if not matched:
        return 0, {"firstBoardCount": 0, "twoBoardCount": 0, "threePlusCount": 0}, "无连板"
    first = sum(1 for it in matched if int(it.get("streak") or 1) == 1)
    two = sum(1 for it in matched if int(it.get("streak") or 1) == 2)
    three_plus = sum(1 for it in matched if int(it.get("streak") or 1) >= 3)
    max_streak = max(int(it.get("streak") or 1) for it in matched)
    ladder_counts = {
        "firstBoardCount": first,
        "twoBoardCount": two,
        "threePlusCount": three_plus,
    }
    return (
        limit_up_count,
        ladder_counts,
        f"{max_streak}连板",
    )


def _decision_chinese(scorer_decision: str) -> str:
    """把四级判定 + 兼容枚举映射为验收枚举中文文案（R12-PLAN-4）。"""
    return {
        # 范本四级判定
        "CORE_MAIN": "核心主赛道",
        "SECONDARY_MAIN": "次主线/轮动主线",
        "SHORT_LINE": "短线支线",
        "PULSE_AVOID": "一日游脉冲/回避",
        "INSUFFICIENT": "数据不足",
        # 兼容历史快照中的旧枚举
        "PASS": "达标",
        "WATCH": "观察",
        "AVOID": "规避",
    }.get(scorer_decision, "数据不足")


# ---------------------------------------------------------------------------
# R12-PLAN-1：动态候选池（消费 industry-universe-snapshot 归档）
# ---------------------------------------------------------------------------

def _universe_board_rows() -> dict[str, list[dict[str, Any]]]:
    """industry-universe-snapshot → {boardName: 按日升序的指标行}。"""
    records = _archive.read_records("industry-universe-snapshot")
    per_board: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        items = rec.get("items")
        if not isinstance(items, list):
            continue
        trade_date = str(rec.get("tradeDate") or "")
        if not trade_date:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("boardName") or "").strip()
            if not name:
                continue
            per_board.setdefault(name, []).append(
                {
                    "date": trade_date,
                    "boardCodeEm": item.get("boardCodeEm"),
                    "chgPct": _to_float(item.get("chgPct")),
                    "amount": _to_float(item.get("amount")),
                    "netInflow": _to_float(item.get("netInflow")),
                    "riseCount": item.get("riseCount"),
                    "fallCount": item.get("fallCount"),
                }
            )
    for name in per_board:
        per_board[name] = sorted(per_board[name], key=lambda r: r["date"])
    return per_board


def _concept_qualification_injection(
    per_board: dict[str, list[dict[str, Any]]],
    tracks_cfg: list[dict[str, Any]],
    close_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """R23-P2-03：概念资格腿注入 universe 联合排名口径（跨 taxonomy 可比资格）。

    board_type=concept 的赛道以 THS 概念指数（与行业汇总同源同单位）的
    逐日成交额插入行业 universe，参与近5日成交额联合排名——概念板块
    由此获得与行业口径可比的市场排名，不再因 taxonomy 差异被永久剔除。
    注入行不带 netInflow/riseCount/fallCount（THS 概念指数无此口径，
    评分层诚实缺口；资金流本就不参与资格判定）。
    单位换算：close 归档为元，universe 行为亿 → /1e8。
    日期域收缩：概念腿 close 历史远长于 universe 归档——若把 close 全历史
    并入日历，close-only 历史日会成为（低完整性行的）"证据日"，行业成员
    在这些日子"缺行"会累计出池 streak（玩具门限下复现：行业种子被误逐）。
    故注入行只保留**行业 universe 已有日期**（证据日上参与排名）。
    仅支持单板概念腿；复合赛道资格须走行业主腿（qualifyLeg，配置文档化）。
    """
    industry_dates = {
        r["date"]
        for rows in per_board.values()
        for r in rows
        if r.get("date")
    }
    injected: dict[str, list[dict[str, Any]]] = {}
    for tc in tracks_cfg:
        if str(tc.get("board_type") or "") != "concept":
            continue
        if not tc.get("enabled", True):
            continue
        descs = _track_board_descs(tc)
        if len(descs) != 1:
            continue
        code = descs[0]["boardCode"]
        series: dict[str, float] = {}
        for rec in close_records:
            if str(rec.get("trackId") or "") != str(tc["id"]):
                continue
            if code and str(rec.get("boardCode") or "") != code:
                continue
            dt = str(rec.get("tradeDate") or "")
            amt = _to_float(rec.get("amount"))
            if dt and amt is not None:
                series[dt] = amt / 1e8
        rows = [
            {
                "date": dt,
                "boardCodeEm": code,
                "chgPct": None,
                "amount": amt,
                "netInflow": None,
                "riseCount": None,
                "fallCount": None,
            }
            for dt, amt in sorted(series.items())
            if dt in industry_dates
        ]
        if rows:
            # 注入键用 expected_name（如"中特估"）：与 _find_universe_row /
            # 承继映射共用的名称域一致（track name 不在指标匹配名集合内）
            key = str(descs[0]["expectedName"] or tc.get("name") or tc["id"])
            injected[key] = rows
    return injected


def _universe_known_dates(
    per_board: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """universe 归档覆盖的全部交易日（升序）——板块缺行即视为断档。"""
    dates: set[str] = set()
    for rows in per_board.values():
        for row in rows:
            if row.get("date"):
                dates.add(row["date"])
    return sorted(dates)


def _universe_metrics(
    rows: list[dict[str, Any]],
    trade_date: str,
    window_days: int,
    known_dates: list[str] | None = None,
) -> dict[str, Any]:
    """单板块 universe 指标：近 N 日成交额、当日净流入、连续净流入天数、红盘占比。

    R12 复核修订 P2-8：窗口与连续计数按归档覆盖日（known_dates）逐日截断，
    板块缺行/数值缺失即断档——旧数据不计入"近 5 日"，避免跨缺口聚合失真。
    红盘口径 = 上涨/(上涨+下跌)（THS 源无平盘列；口径在 yaml 注释明示）。
    """
    row_by_date = {r["date"]: r for r in rows if r.get("date")}
    upto_dates = [
        d for d in (known_dates or sorted(row_by_date)) if d <= trade_date
    ]
    today = row_by_date.get(trade_date)

    window_amounts: list[float] = []
    for d in reversed(upto_dates):
        row = row_by_date.get(d)
        if row is None or row.get("amount") is None:
            break  # 断档：窗口到此为止
        window_amounts.append(row["amount"])
        if len(window_amounts) >= window_days:
            break
    five_day_amount = sum(window_amounts) if window_amounts else None

    days = 0
    if today is not None and (today.get("netInflow") or 0) > 0:
        for d in reversed(upto_dates):
            row = row_by_date.get(d)
            if row is None:
                break  # 断档：连续性终止
            value = row.get("netInflow")
            if value is None or value <= 0:
                break
            days += 1

    red_ratio: float | None = None
    if today is not None:
        rise = today.get("riseCount")
        fall = today.get("fallCount")
        if isinstance(rise, (int, float)) and isinstance(fall, (int, float)):
            total = rise + fall
            if total > 0:
                red_ratio = round(rise / total * 100.0, 1)

    return {
        "fiveDayAmount": five_day_amount,
        "amountWindowDays": len(window_amounts),
        "netInflow": today.get("netInflow") if today else None,
        "continuousInflowDays": days,
        "redStockRatio": red_ratio,
        "riseCount": today.get("riseCount") if today else None,
        "fallCount": today.get("fallCount") if today else None,
        "boardCodeEm": today.get("boardCodeEm") if today else None,
    }


def _universe_ranking(
    per_board: dict[str, list[dict[str, Any]]],
    trade_date: str,
    window_days: int,
) -> list[dict[str, Any]]:
    """全市场行业板块近 N 日成交额降序排名（不筛净流入——排名与资金
    维度的净流入判定是两个独立指标，范本口径）。"""
    known_dates = _universe_known_dates(per_board)
    scored: list[dict[str, Any]] = []
    for name, rows in per_board.items():
        metrics = _universe_metrics(
            rows, trade_date, window_days, known_dates=known_dates
        )
        if metrics["fiveDayAmount"] is None:
            continue
        scored.append({"boardName": name, **metrics})
    scored.sort(key=lambda item: item["fiveDayAmount"], reverse=True)
    for rank, item in enumerate(scored, start=1):
        item["turnoverRank"] = rank
        item["universeSize"] = len(scored)
    return scored


def select_candidate_boards(
    trade_date: str,
    per_board: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """从 universe 归档选出当日动态候选（tracks 模块与 archive_raw 回补共用）。

    口径（范本第 8 表资金维度，R23-P2-02 修订）：近 N 日成交额全市场
    排名前 entryRankMax 的行业板块（仅排名，不筛净流入）；按排名升序返回。
    无当日 universe 记录 → []（fail-closed，调用方退化为纯种子）。
    """
    cfg = load_yaml("tracks.yaml")
    selection = cfg.get("selection", {}) or {}
    pool_size = int(selection.get("entryRankMax", 5))
    window_days = int(selection.get("amountWindowDays", 5))

    if per_board is None:
        per_board = _universe_board_rows()

    today_exists = any(
        any(r["date"] == trade_date for r in rows) for rows in per_board.values()
    )
    if not today_exists:
        return []

    ranked = _universe_ranking(per_board, trade_date, window_days)
    return [item for item in ranked if item["turnoverRank"] <= pool_size][
        :pool_size
    ]


def _entry_ok(item: dict[str, Any], entry_rank_max: int) -> bool:
    """单日准入条件（R23-P2-02）：仅成交额排名 <= entryRankMax。

    净流入不再作为准入硬门——与出池同口径：排名决定监测资格，资金流
    决定评分/评级（R22 范本证据：07-17 医药 -386.52 亿/半导体 -730.77 亿
    均在监测表；R22-P2-02 裁定入池净流出硬门会系统性漏选负流入高活跃
    新赛道，与本原则冲突）。
    """
    rank = item.get("turnoverRank")
    if rank is None or rank > entry_rank_max:
        return False
    return True


def _exit_hit(item: dict[str, Any] | None, exit_rank_max: int) -> bool:
    """单日触及出池条件：当日缺行 / 排名跌出 exitRankMax。

    R22（人工验收 R22-DEF-01）：仅排名口径——净流入是评分定级维度，
    不是出局条件。范本 2026-07-17 自证：医药生物净流入 -386.52 亿、
    半导体 -730.77 亿仍留在监测表（定位"退潮主线/主跌浪"，策略回避），
    即"成交额排名决定谁被监测，资金流决定评级好坏"。
    """
    if item is None:
        return True
    rank = item.get("turnoverRank")
    if rank is None or rank > exit_rank_max:
        return True
    return False


def select_scoring_pool(
    trade_date: str,
    per_board: dict[str, list[dict[str, Any]]] | None = None,
    grandfather: list[str] | None = None,
) -> list[dict[str, Any]]:
    """正式评分池（R13-P2-01 迟滞版动态选池；R22 增设种子初始在池）。

    与 select_candidate_boards（单日发现口径）的差异：
    - 入池需连续确认：近 entryWindowDays 个归档日内 >= entryMinDays 日满足
      准入条件（归档历史不足时按实际天数收敛，冷启动退化为单日规则）；
      R23-P2-02：准入仅按成交额排名（<= entryRankMax=5，范本严格口径），
      净流入不再作为准入硬门（排名决定监测资格，资金流决定评级）；
    - 出池需连续确认：连续 exitConfirmDays 日触及出池条件才退出（排名
      连续 exitConfirmDays 日 > exitRankMax）；
    - R23-P2-01 两层资格：QUALIFIED_TODAY（rank<=5 当日范本资格）/
      RETAINED_OBSERVATION（迟滞观察保留）独立分层输出；
    - 池成员资格从 universe 归档全历史逐日递推，无需额外状态文件。
    无当日 universe 记录 → []（fail-closed；R22 起调用方亦不再回退种子，
    无数据日诚实输出空池）。
    grandfather：R22-DEF-01——种子板块映射到的 universe 板块名，作为
    状态机首个证据日的初始在池成员（承继资格），此后与动态成员同规则
    出池（仅排名口径），不再永久豁免。
    """
    cfg = load_yaml("tracks.yaml")
    selection = cfg.get("selection", {}) or {}
    # R23-P2-01：入池阈值改为范本严格口径"前5"（原 poolSize=8 防抖口径
    # 取消——防抖由 RETAINED_OBSERVATION 观察层承担，不再放宽入池资格）
    entry_rank_max = int(selection.get("entryRankMax", 5))
    window_days = int(selection.get("amountWindowDays", 5))
    entry_window = int(selection.get("entryWindowDays", 3))
    entry_min = int(selection.get("entryMinDays", 2))
    exit_rank_max = int(selection.get("exitRankMax", 12))
    exit_confirm = int(selection.get("exitConfirmDays", 2))

    if per_board is None:
        per_board = _universe_board_rows()

    known_dates = [
        d for d in _universe_known_dates(per_board) if d <= trade_date
    ]
    if trade_date not in known_dates:
        return []

    rank_by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for d in known_dates:
        rank_by_date[d] = {
            item["boardName"]: item
            for item in _universe_ranking(per_board, d, window_days)
        }

    # 逐日 universe 完整性（R15 评审因果化修订）：证据日判定只依赖
    # **严格早于当日**的可信历史（前向峰值），未来的更高峰值不得回溯
    # 改写历史日的证据资格（R15 复现：D1/D2=2 板块入池后，D3 恢复 6 板块
    # 会使全局峰值抬到 6 → D1/D2 被回溯判为不完整 → 池无解释清空）。
    # - 绝对下限 minUniverseBoards 来自已验证完整快照（2026-08-20 实测
    #   90 板块，取其半），防冷启动期部分响应被"相对自身峰值"漏放；
    # - 前向峰值只由**已通过门禁的完整日**抬高（可信基线），未过门禁的
    #   部分响应日不污染基线。
    board_count_by_date: dict[str, int] = {d: 0 for d in known_dates}
    for rows in per_board.values():
        dates_present = {r["date"] for r in rows}
        for d in known_dates:
            if d in dates_present:
                board_count_by_date[d] += 1
    min_ratio = float(selection.get("minUniverseBoardRatio", 0.5))
    min_abs = int(selection.get("minUniverseBoards", 0))
    complete_dates: set[str] = set()
    trusted_peak = 0
    for d in known_dates:  # 升序遍历 → 严格因果
        threshold = max(min_abs, trusted_peak * min_ratio)
        if board_count_by_date[d] >= threshold:
            complete_dates.add(d)
            trusted_peak = max(trusted_peak, board_count_by_date[d])

    pool: list[str] = list(grandfather or [])
    exit_streak: dict[str, int] = {}
    for d in known_dates:
        today_rows = rank_by_date[d]
        window = known_dates[
            max(0, known_dates.index(d) - entry_window + 1) : known_dates.index(d) + 1
        ]
        # 冷启动收敛：归档历史不足 entryMinDays 时按实际窗口天数要求
        eff_min = min(entry_min, len(window))

        # universe 最低完整性门禁（R14 §5.4）：当日板块行数显著低于
        # 历史峰值（部分响应）时，该日不作为出池/入池证据日——否则上游
        # 数据缺失会被误解释为市场资格失败（缺行=exit hit 的前置条件是
        # 当日 universe 已通过完整性校验）。
        if d not in complete_dates:
            continue

        # 1) 存量成员出池确认（R14 §5.2：健康日必须清零 streak，
        #    "连续 N 日"不得退化为"累计 N 次"）
        kept: list[str] = []
        for name in pool:
            item = today_rows.get(name)
            if _exit_hit(item, exit_rank_max):
                streak = exit_streak.get(name, 0) + 1
            else:
                streak = 0
            if streak >= exit_confirm:
                exit_streak.pop(name, None)
                continue
            exit_streak[name] = streak
            kept.append(name)

        # 2) 新成员入池确认（只在完整性达标的证据日上累计命中）
        for name, item in today_rows.items():
            if name in kept:
                continue
            hits = 0
            for wd in window:
                if wd not in complete_dates:
                    continue
                wi = rank_by_date.get(wd, {}).get(name)
                if wi is not None and _entry_ok(wi, entry_rank_max):
                    hits += 1
            if hits >= eff_min:
                kept.append(name)
                exit_streak[name] = 0

        pool = kept

    # R22：当日快照本身不过完整性门禁 → 不输出任何池成员（fail-closed）。
    # 无可信证据日的板块集不可辩护（含承继成员）——08-18/19 部分快照日
    # 诚实输出空池，与人工验收"无数据日清空"决议一致。
    if trade_date not in complete_dates:
        return []

    # 输出当日有 universe 行的池成员（缺行成员保留池籍但当日不可评分）。
    # R23-P2-01 两层资格：当日范本资格（rank <= entryRankMax）与迟滞观察
    # 保留（曾入选、现 rank ∈ (entryRankMax, exitRankMax]、未满出池确认）
    # 是两个独立资格层，输出显式分层标记，调用方/前端不得等价呈现。
    items = [
        {
            **rank_by_date[trade_date][name],
            "poolQualification": (
                "QUALIFIED_TODAY"
                if rank_by_date[trade_date][name]["turnoverRank"] <= entry_rank_max
                else "RETAINED_OBSERVATION"
            ),
        }
        for name in pool
        if name in rank_by_date[trade_date]
    ]
    items.sort(key=lambda item: item["turnoverRank"])
    return items


def select_discovery_pool(
    trade_date: str,
    per_board: dict[str, list[dict[str, Any]]] | None = None,
    rank_max: int | None = None,
) -> list[dict[str, Any]]:
    """预热池（R13-P2-01）：成交额排名前 prewarmRankMax 的板块。

    不筛当日净流入——预热目的是让 archive-raw 对"接近入池"的板块持续
    回补 close 历史，消除首次入选后的冷启动；预热数据不直接参与评分。
    """
    cfg = load_yaml("tracks.yaml")
    selection = cfg.get("selection", {}) or {}
    window_days = int(selection.get("amountWindowDays", 5))
    if rank_max is None:
        rank_max = int(selection.get("prewarmRankMax", 16))

    if per_board is None:
        per_board = _universe_board_rows()

    if trade_date not in _universe_known_dates(per_board):
        return []

    ranked = _universe_ranking(per_board, trade_date, window_days)
    return [item for item in ranked if item["turnoverRank"] <= rank_max]


def dynamic_track_identity(cand: dict[str, Any]) -> dict[str, Any]:
    """动态候选 → 归档/输出统一身份（tracks 模块与 archive_raw 回补共用，
    保证 close 历史 trackId::boardCode 键一致）。"""
    board_code = str(cand.get("boardCodeEm") or "").strip() or (
        "THS-" + str(cand["boardName"])
    )
    return {
        "trackId": "dyn_" + board_code,
        "boardCode": board_code,
        "boardName": str(cand["boardName"]),
        "boardType": "industry",
    }


def _canonical_board_name(name: str) -> str:
    """板块名规范化：去首尾空白与常见后缀（"行业"），用于精确等价匹配。

    R12 复核修订 P2-6/P2-7：弃用双向子串包含（"电力"会误吞"电力设备"、
    "医药生物"误配"医药商业"），只保留 精确相等 / 别名表命中 / 规范化相等。
    """
    text = str(name or "").strip()
    if text.endswith("行业") and len(text) > 2:
        text = text[: -len("行业")]
    return text


def _match_board_metadata(
    board_name: str,
    board_metadata: dict[str, Any],
) -> dict[str, Any] | None:
    """板块名 → boardMetadata 条目（精确名/别名表/规范化相等，禁子串）。"""
    if not board_metadata:
        return None
    name = board_name.strip()
    canon = _canonical_board_name(name)
    for key, meta in board_metadata.items():
        if key == name or _canonical_board_name(key) == canon:
            return meta
    for key, meta in board_metadata.items():
        for alias in [key] + list((meta or {}).get("aliases", []) or []):
            if alias and (
                str(alias).strip() == name
                or _canonical_board_name(str(alias)) == canon
            ):
                return meta
    return None


def _seed_match_names(seeds: list[dict[str, Any]]) -> set[str]:
    """种子赛道全部候选名集合（用于动态候选去重）。"""
    names: set[str] = set()
    for tc in seeds:
        for key in ("name", "expected_name", "index_name_ths"):
            value = str(tc.get(key) or "").strip()
            if value:
                names.add(value)
        for sub in tc.get("composite", []) or []:
            for key in ("name", "index_name_ths"):
                value = str(sub.get(key) or "").strip()
                if value:
                    names.add(value)
    return names


def _names_overlap(name: str, known: set[str]) -> bool:
    """名称重合判定：精确相等或规范化相等（"电力"=="电力行业"）。"""
    canon = _canonical_board_name(name)
    return any(
        k == name or _canonical_board_name(k) == canon for k in known if k
    )


def _find_universe_row(
    names: list[str],
    rank_by_name: dict[str, Any],
) -> dict[str, Any] | None:
    """按精确/规范化名称在 universe 排名表中找板块行（P2-6 对称修复）。"""
    for name in names:
        if name and name in rank_by_name:
            return rank_by_name[name]
    canon_by_key = {
        _canonical_board_name(key): row for key, row in rank_by_name.items()
    }
    for name in names:
        if not name:
            continue
        row = canon_by_key.get(_canonical_board_name(name))
        if row is not None:
            return row
    return None


def _make_track_item(
    *,
    track_id: str,
    track_name: str,
    positioning: str,
    raw: dict[str, Any],
    scorer_out: dict[str, Any],
    min_history_days: int = 20,
) -> dict[str, Any]:
    """把结构化原始指标 + 评分结果映射为 16 列 typed 输出项。"""
    ma_label = _ma_alignment_label(raw.get("ma_data"))
    excess_label = raw.get("excess_label")
    red_ratio = raw.get("red_stock_ratio")
    # R13-P2-01/P2-02：数据就绪状态。动态候选 close 历史不足
    # min_history_days → WARMING_UP（冷启动，与 FETCH_FAILED 语义分离）；
    # 否则沿用评分器的 READY/DEGRADED/INSUFFICIENT。
    readiness = str(scorer_out.get("dataReadiness") or "INSUFFICIENT")
    history_days = raw.get("history_days")
    # WARMING_UP（R14 §5.3）：动态候选 close 历史不足 = 冷启动预热态，
    # 不是正式评分池成员——不输出成熟 score/decision（固定"数据不足"），
    # 不参与模块 coverage 与 D0 完整度（collect_tracks 分开计数）。
    warming = (
        raw.get("track_kind") == "dynamic"
        and isinstance(history_days, int)
        and history_days < min_history_days
    )
    if warming:
        readiness = "WARMING_UP"
    score = None if warming else scorer_out.get("score")
    coverage_pct = None if warming else scorer_out.get("coveragePct")
    decision_code = (
        "INSUFFICIENT" if warming
        else str(scorer_out.get("decision") or "INSUFFICIENT")
    )
    dimension_pass = None if warming else scorer_out.get("dimensionPass")
    return {
        "date": raw["date"],
        "trackId": track_id,
        "trackName": track_name,
        "positioning": positioning,
        "selectionReason": raw.get("selection_reason", ""),
        "turnoverRank": raw.get("turnover_rank"),
        "mainNetInflow": raw.get("main_net_inflow"),
        "continuousInflowDays": raw.get("continuous_inflow_days"),
        "maAlignment": ma_label,
        "rps60": raw.get("rps60"),
        "excessReturn20d": excess_label,
        "limitUpCount": raw.get("limit_up_count"),
        "ladderCompleteness": raw.get("ladder_completeness"),
        "redStockRatio": (
            f"{red_ratio:.0f}%" if isinstance(red_ratio, (int, float)) and math.isfinite(float(red_ratio)) else None
        ),
        "coreCatalyst": raw.get("core_catalyst") or "",
        "earningsRealization": raw.get("earnings_realization") or "",
        "score": score,
        "coveragePct": coverage_pct,
        "decision": _decision_chinese(decision_code),
        "decisionCode": decision_code,
        "dimensionPass": dimension_pass,
        "poolQualification": raw.get("pool_qualification"),
        "dataReadiness": readiness,
        "historyDays": history_days,
    }


def collect_tracks(
    trade_date: str,
) -> dict[str, Any]:
    """消费 daily raw archive 采集主赛道指标（状态机统一选池）。

    R12-PLAN-1：动态候选从 industry-universe-snapshot 全市场口径选出；
    资金/红盘指标优先 universe 口径，close 序列指标（MA/RPS）沿用
    track-board-close（候选首次入选时由 archive_raw 回补历史）。
    R22-DEF-01（人工验收）：配置种子（范本 2026-07-17 四板块）不再是
    无条件在场成员——映射 universe 板块名后并入同一套入池/出池状态机
    （承继初始资格，仅按排名口径出池）；无 universe 数据日输出空池
    （fail-closed），不再显示静态占位板块。
    """
    cfg = load_yaml("tracks.yaml")
    tracks_cfg = cfg.get("tracks", [])
    seeds = [tc for tc in tracks_cfg if tc.get("enabled", True)]
    selection_cfg = cfg.get("selection", {}) or {}
    board_metadata = cfg.get("boardMetadata", {}) or {}
    window_days = int(selection_cfg.get("amountWindowDays", 5))

    close_records = _archive.read_records("track-board-close")
    flow_records = _archive.read_records("track-board-flow")
    pool_records = _archive.read_records("limit-up-pool")

    per_board = _universe_board_rows()
    # R23-P2-03：概念资格腿（THS 概念指数口径）注入行业 universe 联合排名
    per_board.update(
        _concept_qualification_injection(per_board, tracks_cfg, close_records)
    )
    universe_today = any(
        any(r["date"] == trade_date for r in rows)
        for rows in per_board.values()
    )
    ranked = (
        _universe_ranking(per_board, trade_date, window_days)
        if universe_today
        else []
    )
    rank_by_name = {item["boardName"]: item for item in ranked}
    # ---- 0) 输出赛道列表：状态机在池种子 + 动态候选（名称重合去重） ----
    # R22-DEF-01（人工验收）：种子不再无条件在场——映射到 universe 板块名
    # 后作为状态机初始在池成员（承继资格），与动态成员同规则出池；
    # 无 universe 数据日不回退种子（fail-closed 空池）。
    seed_names = _seed_match_names(seeds)
    seed_uni_name: dict[str, str] = {}
    for tc in seeds:
        match_names = set(_track_match_names(tc)) | {str(tc.get("name") or "")}
        for board_key in per_board:
            if _names_overlap(str(board_key), match_names):
                seed_uni_name[tc["id"]] = str(board_key)
                break

    candidates = (
        select_scoring_pool(
            trade_date,
            per_board=per_board,
            grandfather=sorted(set(seed_uni_name.values())),
        )
        if universe_today
        else []
    )
    pool_names_today = {str(c["boardName"]) for c in candidates}
    pool_qual_by_name = {
        str(c["boardName"]): c.get("poolQualification")
        for c in candidates
    }

    # 未映射种子披露（R22-DEF-01）：配置种子在行业 universe 中不存在
    # 对应板块（如"高股息中特估"为概念板块，不在行业快照口径）时，
    # 不得静默消失——记入 module errors 供前端/验收明示。此为信息性
    # 披露，不影响选池语义（无市场排名即无从入选，fail-closed）。
    unmapped_seeds = [
        f"seed_unmapped_in_industry_universe:{tc['id']}"
        f"({tc.get('name', tc['id'])})"
        for tc in seeds
        if tc["id"] not in seed_uni_name
    ]

    out_tracks: list[dict[str, Any]] = []
    for tc in seeds:
        mapped = seed_uni_name.get(tc["id"])
        if mapped is None or mapped not in pool_names_today:
            # 从未出现在 universe，或已按排名规则连续 exitConfirmDays 日
            # 跌出 exitRankMax → 不在监测表（范本语义：每日按条件筛选）
            continue
        out_tracks.append(
            {
                "trackId": tc["id"],
                "trackName": tc.get("name", tc["id"]),
                "positioning": tc.get("positioning", ""),
                "descs": _track_board_descs(tc),
                "matchNames": _track_match_names(tc),
                "coreCatalyst": str(tc.get("coreCatalyst") or ""),
                "earningsRealization": str(tc.get("earningsRealization") or ""),
                "kind": "seed",
                "universe": None,
                "selectionReason": "seed",
            }
        )

    for cand in candidates:
        if _names_overlap(str(cand["boardName"]), seed_names):
            continue
        meta = _match_board_metadata(str(cand["boardName"]), board_metadata) or {}
        identity = dynamic_track_identity(cand)
        out_tracks.append(
            {
                "trackId": identity["trackId"],
                "trackName": identity["boardName"],
                "positioning": str(meta.get("positioning") or ""),
                "descs": [
                    {
                        "boardCode": identity["boardCode"],
                        "indexNameThs": identity["boardName"],
                        "expectedName": identity["boardName"],
                        "weight": 1.0,
                    }
                ],
                "matchNames": [identity["boardName"]],
                "coreCatalyst": str(meta.get("coreCatalyst") or ""),
                "earningsRealization": str(meta.get("earningsRealization") or ""),
                "kind": "dynamic",
                "universe": cand,
                "selectionReason": (
                    f"dynamic:rank={cand['turnoverRank']}/{cand['universeSize']}"
                    f",inflow={cand['netInflow']}"
                ),
            }
        )

    close_grouped = _group_close_by_board(close_records)

    # ---- 1) universe 级派生：60 日收益（RPS 百分位底座）与近 5 日 amount ----
    returns: dict[str, float] = {}
    amounts: dict[str, float] = {}
    for ot in out_tracks:
        track_id = ot["trackId"]
        descs = ot["descs"]
        comb = _combine_close_series(close_grouped, track_id, descs)
        key = (
            f"{track_id}::{descs[0]['boardCode']}"
            if len(descs) == 1
            else f"{track_id}::composite"
        )
        ret = _sixty_day_return(comb)
        amt = _five_day_amount(comb)
        if ret is not None:
            returns[key] = ret
        if amt is not None:
            amounts[key] = amt

    # ---- 2) 每赛道指标 ----
    raw_tracks: list[dict[str, Any]] = []
    module_errors: list[str] = [ERR_HS300_SEED_UNAVAILABLE]
    if not universe_today:
        module_errors.append(ERR_RED_RATIO_SOURCE_UNAVAILABLE)
    module_errors.extend(unmapped_seeds)

    for ot in out_tracks:
        track_id = ot["trackId"]
        track_name = ot["trackName"]
        descs = ot["descs"]
        comb = _combine_close_series(close_grouped, track_id, descs)

        ma = _compute_ma(comb)
        universe_key = (
            f"{track_id}::{descs[0]['boardCode']}"
            if len(descs) == 1
            else f"{track_id}::composite"
        )
        rps60 = _rps_percentile(returns, universe_key)

        # universe 匹配（动态候选即自身；种子按精确/规范化名称找行业行）
        uni = ot.get("universe")
        if uni is None:
            uni = _find_universe_row(ot["matchNames"], rank_by_name)

        # 成交额排名：优先 universe 全市场口径，回退归档板块互排
        if uni is not None:
            turnover_rank = uni["turnoverRank"]
            turnover_universe = uni["universeSize"]
        else:
            turnover_rank = _turnover_rank(amounts, universe_key)
            turnover_universe = len(amounts)

        # 资金流：优先 universe 当日净流入/连续天数，回退 flow 归档
        legacy_inflow: float | None
        if len(descs) == 1:
            legacy_inflow = _main_net_inflow(
                flow_records, track_id, descs[0]["boardCode"], trade_date
            )
            legacy_days = _continuous_inflow_days(
                flow_records, track_id, descs[0]["boardCode"], trade_date
            )
        else:
            vals = []
            for d in descs:
                v = _main_net_inflow(
                    flow_records, track_id, d["boardCode"], trade_date
                )
                if v is not None:
                    vals.append(d["weight"] * v)
            legacy_inflow = sum(vals) if vals else None
            legacy_days = _composite_continuous_inflow_days(
                flow_records, track_id, descs, trade_date
            )

        if uni is not None and uni.get("netInflow") is not None:
            inflow = uni["netInflow"]
            days = int(uni["continuousInflowDays"])
        else:
            inflow = legacy_inflow
            days = legacy_days

        # 红盘占比：universe 当日涨跌家数（修复 RED_RATIO_SOURCE_UNAVAILABLE）
        red_stock_ratio = (
            uni.get("redStockRatio") if uni is not None else None
        )

        # 涨停池
        pool_items = _limit_up_daily(pool_records, trade_date)
        limit_up_count, ladder_counts, ladder_label = _limit_up_stats(
            pool_items, ot["matchNames"]
        )

        # 涨停率 = 涨停数 / 板块公司数（universe 上涨+下跌家数近似成分数；
        # R12 复核修订：补齐评分器 limitUpRate 输入，否则情绪维权重被剔除）
        limit_up_rate: float | None = None
        if limit_up_count is not None and uni is not None:
            rise = uni.get("riseCount")
            fall = uni.get("fallCount")
            if isinstance(rise, (int, float)) and isinstance(fall, (int, float)):
                total = rise + fall
                if total > 0:
                    limit_up_rate = round(limit_up_count / total * 100.0, 2)

        raw = {
            "date": trade_date,
            "ma_data": ma,
            "rps60": rps60,
            "turnover_rank": turnover_rank,
            "turnover_universe_size": turnover_universe,
            "main_net_inflow": inflow,
            "continuous_inflow_days": (
                int(days) if days is not None else None
            ),
            "excess_return_20d_pct": None,  # HS300 无 archive 源，诚实缺口
            "excess_label": None,
            "limit_up_count": limit_up_count,
            "ladder_counts": ladder_counts,
            "ladder_completeness": ladder_label,
            "red_stock_ratio": red_stock_ratio,
            "core_catalyst": ot["coreCatalyst"],
            "earnings_realization": ot["earningsRealization"],
            "selection_reason": ot["selectionReason"],
            # R23-P2-01 两层资格：当日范本资格 / 迟滞观察保留
            "pool_qualification": (
                (ot.get("universe") or {}).get("poolQualification")
                if ot.get("universe") is not None
                else pool_qual_by_name.get(seed_uni_name.get(track_id, ""))
            ),
            # R13-P2-01：close 历史深度（交易日数），供 WARMING_UP 判定
            "history_days": len(comb),
            "track_kind": ot["kind"],
        }

        tracks_input = {
            "trackId": track_id,
            "trackName": track_name,
            "positioning": ot["positioning"],
            "turnoverRank": raw["turnover_rank"],
            "turnoverUniverseSize": raw["turnover_universe_size"],
            "mainNetInflow": raw["main_net_inflow"],
            "continuousInflowDays": raw["continuous_inflow_days"],
            "maAlignment": raw["ma_data"],
            "rps60": raw["rps60"],
            "excessReturn20d": raw["excess_return_20d_pct"],
            "limitUpCount": raw["limit_up_count"],
            "limitUpRate": limit_up_rate,
            "ladderCompleteness": raw["ladder_counts"],
            "ladderLabel": raw["ladder_completeness"],
            "redStockRatio": raw["red_stock_ratio"],
            "coreCatalyst": ot["coreCatalyst"],
            "earningsRealization": ot["earningsRealization"],
        }
        raw_tracks.append({"raw": raw, "input": tracks_input})

    # ---- 3) 评分（含四级判定） ----
    from collector.calculators.tracks import score_tracks

    scored = score_tracks([rt["input"] for rt in raw_tracks])

    scored_by_idx: dict[str, dict[str, Any]] = {}
    for rt, sc in zip(raw_tracks, scored):
        scored_by_idx[rt["input"]["trackId"]] = sc

    # ---- 4) 输出项与 coverage ----
    items: list[dict[str, Any]] = []
    coverages: list[float] = []

    for rt in raw_tracks:
        sc = scored_by_idx[rt["input"]["trackId"]]

        item = _make_track_item(
            track_id=rt["input"]["trackId"],
            track_name=rt["input"]["trackName"],
            positioning=rt["input"]["positioning"],
            raw=rt["raw"],
            scorer_out=sc,
            min_history_days=int(selection_cfg.get("minHistoryDays", 20)),
        )
        items.append(item)

        # WARMING_UP 预热候选与正式 READY 评分分开计数（R14 §5.3）：
        # 不进 coverage 分母、不影响评分完整性判定与 D0。
        if item.get("dataReadiness") == "WARMING_UP":
            continue

        implemented = 0
        for field in _INDICATOR_FIELDS:
            val = rt["raw"].get(field)
            if not _is_missing(val):
                implemented += 1
        coverages.append(implemented / len(_INDICATOR_FIELDS) * 100.0)

    module_coverage = (
        sum(coverages) / len(coverages)
        if coverages
        else 0.0
    )
    module_coverage = round(module_coverage, 1)

    data_date_ok = all(item["date"] == trade_date for item in items)

    # R13-P2-02：三态 coverage 门禁（配置驱动，替代单一硬门槛 80）。
    # - 关键输入缺失（无输出项/日期身份错误/全部评分缺失）→ 直接
    #   UNAVAILABLE（critical，不允许 coverage 绕过）；
    # - coverage >= target → PARTIAL/TRACKS_SUFFICIENT/READY；
    # - floor <= coverage < target → PARTIAL/TRACKS_DEGRADED/DEGRADED
    #   （保留可用评分，降置信，不再一刀切 UNAVAILABLE）；
    # - coverage < floor → UNAVAILABLE/TRACKS_INSUFFICIENT/FAILED。
    scoring_decision_cfg = (
        load_yaml("track-scoring.yaml").get("decision", {}) or {}
    )
    coverage_target = float(
        scoring_decision_cfg.get("coverage_target_pct", 80.0)
    )
    coverage_floor = float(
        scoring_decision_cfg.get("coverage_hard_floor_pct", 65.0)
    )
    any_score = any(
        scored_by_idx[rt["input"]["trackId"]].get("score") is not None
        for rt, it in zip(raw_tracks, items)
        if it.get("dataReadiness") != "WARMING_UP"
    )
    critical_failed = (not items) or (not data_date_ok) or (not any_score)
    warming_boards = [
        item["trackName"]
        for item in items
        if item.get("dataReadiness") == "WARMING_UP"
    ]

    base: dict[str, Any] = {
        "dataDate": trade_date,
        "configVersion": CONFIG_VERSION,
        "effectiveFrom": EFFECTIVE_FROM,
        "effectiveTo": EFFECTIVE_TO,
        "sourceSystem": SOURCE_SYSTEM,
        "coveragePct": module_coverage,
        "coverageTargetPct": coverage_target,
        "coverageHardFloorPct": coverage_floor,
        "errors": module_errors,
        "items": items,
        # R13-P2-01：冷启动板块清单（信息性，不计失败）
        "warmingUpBoards": warming_boards,
    }

    if critical_failed or module_coverage < coverage_floor:
        if not critical_failed:
            fail_reason = "TRACK_METRICS_INSUFFICIENT_COVERAGE"
        elif items and not any_score and len(warming_boards) == len(items):
            # 全部候选处于预热态：无成熟评分可输出，诚实 fail-closed
            fail_reason = "TRACKS_ALL_WARMING_UP"
        else:
            fail_reason = "TRACK_CRITICAL_INPUT_MISSING"
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            **base,
            "decision": "TRACKS_INSUFFICIENT",
            "dataReadiness": "FAILED",
            "reason": fail_reason,
        }

    if module_coverage >= coverage_target:
        return {
            "status": ModuleStatus.PARTIAL.value,
            **base,
            "decision": "TRACKS_SUFFICIENT",
            "dataReadiness": "READY",
            "reason": (
                "PARTIAL_TRACKS_SUFFICIENT; "
                "excessReturn20d 为诚实缺口（见 errors）；"
                f"候选池={len(candidates)}（universe {'OK' if universe_today else 'UNAVAILABLE'}）"
            ),
        }

    return {
        "status": ModuleStatus.PARTIAL.value,
        **base,
        "decision": "TRACKS_DEGRADED",
        "dataReadiness": "DEGRADED",
        "reason": (
            "PARTIAL_TRACKS_DEGRADED; "
            f"coverage {module_coverage} 处于 [{coverage_floor}, "
            f"{coverage_target}) 区间，保留可用评分并降置信；"
            "excessReturn20d 为诚实缺口（见 errors）；"
            f"候选池={len(candidates)}（universe {'OK' if universe_today else 'UNAVAILABLE'}）"
        ),
    }


def _composite_continuous_inflow_days(
    flow_records: list[dict[str, Any]],
    track_id: str,
    descs: list[dict[str, Any]],
    trade_date: str,
) -> int:
    """composite：按日合成两子板 0.5 加权当日净流入，再统计连续 >0 天数。

    D 行必须存在且合成值 >0，否则 0。
    """
    # 收集每个子板按日流量
    by_board: dict[str, dict[str, float]] = {}
    for d in descs:
        code = d["boardCode"]
        board_series: dict[str, float] = {}
        for rec in flow_records:
            if (
                str(rec.get("trackId") or "") == track_id
                and str(rec.get("boardCode") or "") == code
            ):
                v = _to_float(rec.get("mainNetInflow"))
                dt = str(rec.get("tradeDate") or "")
                if v is not None and dt:
                    board_series[dt] = v
        by_board[code] = board_series

    dates = sorted(
        {
            dt
            for d in descs
            for dt in by_board.get(d["boardCode"], {})
            if d["weight"] > 0
        }
    )

    combined_series: list[tuple[str, float]] = []
    for dt in dates:
        val = 0.0
        ok = True
        for d in descs:
            v = by_board.get(d["boardCode"], {}).get(dt)
            if v is None:
                ok = False
                break
            val += d["weight"] * v
        if not ok:
            continue
        combined_series.append((dt, val))

    days = 0
    for dt, val in reversed(combined_series):
        if dt > trade_date:
            continue
        if dt == trade_date and val <= 0:
            return 0
        if val <= 0:
            break
        days += 1
    if not any(dt == trade_date and val > 0 for dt, val in combined_series):
        return 0
    return days
