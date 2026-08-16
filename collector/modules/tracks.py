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

CONFIG_VERSION = "2.0"
EFFECTIVE_FROM = "2026-07-01"
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


def _red_stock_ratio(
    member_records: list[dict[str, Any]],
    trade_date: str,
    track_id: str,
) -> float | None:
    """本轮诚实缺口：无当日成交行情源 → None（不伪造）。"""
    # 仅探测是否存在当日成分快照（用于 errors 说明），RPS/红盘本身置 None。
    return None


def _decision_chinese(scorer_decision: str) -> str:
    """把 score_tracks 的 PASS/WATCH/AVOID/INSUFFICIENT 映射为验收枚举中文文案。"""
    return {
        "PASS": "达标",
        "WATCH": "观察",
        "AVOID": "规避",
        "INSUFFICIENT": "数据不足",
    }.get(scorer_decision, "数据不足")


def _make_track_item(
    *,
    track_id: str,
    track_name: str,
    positioning: str,
    raw: dict[str, Any],
    scorer_out: dict[str, Any],
) -> dict[str, Any]:
    """把结构化原始指标 + 评分结果映射为 16 列 typed 输出项。"""
    ma_label = _ma_alignment_label(raw.get("ma_data"))
    excess_label = raw.get("excess_label")
    red_ratio = raw.get("red_stock_ratio")
    return {
        "date": raw["date"],
        "trackId": track_id,
        "trackName": track_name,
        "positioning": positioning,
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
        "score": scorer_out.get("score"),
        "coveragePct": scorer_out.get("coveragePct"),
        "decision": _decision_chinese(str(scorer_out.get("decision") or "INSUFFICIENT")),
    }


def collect_tracks(
    trade_date: str,
) -> dict[str, Any]:
    """消费 daily raw archive 采集 4 赛道指标，返回 tracks 模块（PARTIAL/UNAVAILABLE）。"""
    cfg = load_yaml("tracks.yaml")
    tracks_cfg = cfg.get("tracks", [])
    enabled = [tc for tc in tracks_cfg if tc.get("enabled", True)]

    close_records = _archive.read_records("track-board-close")
    flow_records = _archive.read_records("track-board-flow")
    pool_records = _archive.read_records("limit-up-pool")
    member_records = _archive.read_records("track-membership-snapshot")

    per_board = _group_close_by_board(close_records)

    # ---- 1) universe 级派生：60 日收益与近 5 日 amount（全部 track 的板） ----
    returns: dict[str, float] = {}
    amounts: dict[str, float] = {}
    for tc in enabled:
        track_id = tc["id"]
        descs = _track_board_descs(tc)
        comb = _combine_close_series(per_board, track_id, descs)
        # composite：直接以合成 close 序列参与 universe（一个 entry）；单板以 boardCode。
        if len(descs) == 1:
            key = f"{track_id}::{descs[0]['boardCode']}"
            ret = _sixty_day_return(comb)
            amt = _five_day_amount(comb)
            if ret is not None:
                returns[key] = ret
            if amt is not None:
                amounts[key] = amt
        else:
            # composite 用一个合成键
            key = f"{track_id}::composite"
            ret = _sixty_day_return(comb)
            amt = _five_day_amount(comb)
            if ret is not None:
                returns[key] = ret
            if amt is not None:
                amounts[key] = amt

    # ---- 2) 每赛道指标 ----
    raw_tracks: list[dict[str, Any]] = []
    module_errors: list[str] = [ERR_HS300_SEED_UNAVAILABLE, ERR_RED_RATIO_SOURCE_UNAVAILABLE]

    for tc in enabled:
        track_id = tc["id"]
        track_name = tc.get("name", track_id)
        positioning = tc.get("positioning", "")
        descs = _track_board_descs(tc)
        comb = _combine_close_series(per_board, track_id, descs)

        # 均线：用合成序列
        ma = _compute_ma(comb)
        ret = _sixty_day_return(comb)
        amt = _five_day_amount(comb)

        # universe key（与上面一致）
        universe_key = (
            f"{track_id}::{descs[0]['boardCode']}"
            if len(descs) == 1
            else f"{track_id}::composite"
        )

        rps60 = _rps_percentile(returns, universe_key)
        turnover_rank = _turnover_rank(amounts, universe_key)
        turnover_universe = len(amounts)

        # 资金流：单板直接取；composite 用当日两个子板 0.5 加权合成
        inflow: float | None
        if len(descs) == 1:
            inflow = _main_net_inflow(flow_records, track_id, descs[0]["boardCode"], trade_date)
        else:
            vals = []
            for d in descs:
                v = _main_net_inflow(flow_records, track_id, d["boardCode"], trade_date)
                if v is not None:
                    vals.append(d["weight"] * v)
            inflow = sum(vals) if vals else None

        # 连续净流入天数：单板直接用；composite 合成当日流量后重新判断
        if len(descs) == 1:
            days = _continuous_inflow_days(flow_records, track_id, descs[0]["boardCode"], trade_date)
        else:
            days = _composite_continuous_inflow_days(flow_records, track_id, descs, trade_date)

        # 涨停池
        pool_items = _limit_up_daily(pool_records, trade_date)
        match_names = _track_match_names(tc)
        limit_up_count, ladder_counts, ladder_label = _limit_up_stats(pool_items, match_names)

        # 定性配置（从 tracks.yaml）
        core_catalyst = str(tc.get("coreCatalyst") or "")
        earnings = str(tc.get("earningsRealization") or "")

        # 红盘占比：诚实缺口
        red_stock_ratio = _red_stock_ratio(member_records, trade_date, track_id)

        # 结构化原始指标（供 score_tracks）
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
            "core_catalyst": core_catalyst,
            "earnings_realization": earnings,
        }

        tracks_input = {
            "trackId": track_id,
            "trackName": track_name,
            "positioning": positioning,
            "turnoverRank": raw["turnover_rank"],
            "turnoverUniverseSize": raw["turnover_universe_size"],
            "mainNetInflow": raw["main_net_inflow"],
            "continuousInflowDays": raw["continuous_inflow_days"],
            "maAlignment": raw["ma_data"],
            "rps60": raw["rps60"],
            "excessReturn20d": raw["excess_return_20d_pct"],
            "ladderCompleteness": raw["ladder_counts"],
            "redStockRatio": raw["red_stock_ratio"],
            "coreCatalyst": core_catalyst,
            "earningsRealization": earnings,
        }
        raw_tracks.append({"raw": raw, "input": tracks_input})

    # ---- 3) 评分 ----
    from collector.calculators.tracks import score_tracks

    scored = score_tracks([rt["input"] for rt in raw_tracks])

    scored_by_idx: dict[str, dict[str, Any]] = {}
    for rt, sc in zip(raw_tracks, scored):
        scored_by_idx[rt["input"]["trackId"]] = sc

    # ---- 4) 输出项与 coverage ----
    items: list[dict[str, Any]] = []
    coverages: list[float] = []
    all_scores_present = True

    for rt in raw_tracks:
        sc = scored_by_idx[rt["input"]["trackId"]]
        if sc.get("score") is None:
            all_scores_present = False

        item = _make_track_item(
            track_id=rt["input"]["trackId"],
            track_name=rt["input"]["trackName"],
            positioning=rt["input"]["positioning"],
            raw=rt["raw"],
            scorer_out=sc,
        )
        items.append(item)

        # coverage：已实现指标 / 槽位
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

    if (
        module_coverage >= 80.0
        and all_scores_present
        and data_date_ok
        and items
    ):
        return {
            "status": ModuleStatus.PARTIAL.value,
            "dataDate": trade_date,
            "configVersion": CONFIG_VERSION,
            "effectiveFrom": EFFECTIVE_FROM,
            "effectiveTo": EFFECTIVE_TO,
            "sourceSystem": SOURCE_SYSTEM,
            "coveragePct": module_coverage,
            "decision": "TRACKS_SUFFICIENT",
            "reason": (
                "PARTIAL_TRACKS_SUFFICIENT; "
                "excessReturn20d/redStockRatio 为诚实缺口（见 errors）"
            ),
            "errors": module_errors,
            "items": items,
        }

    return {
        "status": ModuleStatus.UNAVAILABLE.value,
        "dataDate": trade_date,
        "configVersion": CONFIG_VERSION,
        "effectiveFrom": EFFECTIVE_FROM,
        "effectiveTo": EFFECTIVE_TO,
        "sourceSystem": SOURCE_SYSTEM,
        "coveragePct": module_coverage,
        "decision": "TRACKS_INSUFFICIENT",
        "reason": "TRACK_METRICS_INSUFFICIENT_COVERAGE",
        "errors": module_errors,
        "items": items,
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
