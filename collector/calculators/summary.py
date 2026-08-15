"""模块 9：确定性综合总结规则引擎。"""

from __future__ import annotations

from typing import Any

from collector.status import ModuleStatus

def generate_summary(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    modules = snapshot["modules"]

    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": snapshot["tradeDate"],
        "generator": "RULE_ENGINE_V1",
        "indexAndTurnover": _rule_index(
            modules.get("marketIndex")
        ),
        "sentiment": _rule_sentiment(
            modules.get("sentiment")
        ),
        "fundFlow": _rule_fund_flow(
            modules.get("fundFlow")
        ),
        "margin": _rule_margin(
            modules.get("margin")
        ),
        "trackConclusion": _rule_tracks(
            modules.get("tracks")
        ),
        "marketEnvironment": _rule_turnover(
            modules.get("turnover")
        ),
        "northbound": _rule_northbound(
            modules.get("northbound")
        ),
        "riskWarning": _rule_risk(modules),
    }

def _rule_index(
    markets: dict[str, Any] | None,
) -> str:
    if (
        not markets
        or markets.get("status")
        != ModuleStatus.FINAL.value
    ):
        return "指数模块暂未取得完整有效数据，本项不作判断。"

    by_name = {
        item.get("name"): item
        for item in markets.get("items", [])
    }

    sh = by_name.get(
        "上证指数",
        {},
    )
    cyb = by_name.get(
        "创业板指",
        {},
    )
    hs300 = by_name.get(
        "沪深300",
        {},
    )

    pct_sh = sh.get("changePct")
    pct_cyb = cyb.get("changePct")
    pct_hs300 = hs300.get("changePct")

    if (
        pct_sh is None
        or pct_cyb is None
        or pct_hs300 is None
    ):
        return "指数数据不完整，本项不作判断。"

    if pct_sh > 0:
        first = (
            f"上证指数收涨 {pct_sh:+.2f}%"
        )
    elif pct_sh < 0:
        first = (
            f"上证指数收跌 {pct_sh:+.2f}%"
        )
    else:
        first = "上证指数平收"

    if pct_cyb > pct_hs300:
        relative = (
            "创业板表现强于沪深300"
        )
    elif pct_cyb < pct_hs300:
        relative = (
            "沪深300表现强于创业板"
        )
    else:
        relative = (
            "创业板与沪深300表现接近"
        )

    return f"{first}；{relative}。"

def _rule_turnover(
    turnover: dict[str, Any] | None,
) -> str:
    if (
        not turnover
        or turnover.get("status")
        != ModuleStatus.FINAL.value
    ):
        return "两市成交额模块暂未取得有效数据，本项不作判断。"

    today = turnover.get(
        "turnoverToday"
    )
    change = turnover.get(
        "turnoverChangePct"
    )
    state = turnover.get(
        "volumeState"
    )

    if today is None:
        return "两市成交额数据不完整，本项不作判断。"

    if change is None:
        return (
            f"沪深两市成交额 {today:.2f} 亿元；"
            "暂无可比较的前一交易日快照。"
        )

    mapping = {
        "EXPANSION": "放量",
        "CONTRACTION": "缩量",
        "FLAT": "量能基本平稳",
    }

    description = mapping.get(
        state,
        "量能状态待确认",
    )

    return (
        f"沪深两市成交额 {today:.2f} 亿元，"
        f"较前一交易日 {change:+.2f}%，"
        f"{description}。"
    )

def _rule_sentiment(
    sentiment: dict[str, Any] | None,
) -> str:
    if not sentiment:
        return "市场情绪模块暂未取得完整有效数据，本项不作判断。"

    if (
        sentiment.get("status")
        == ModuleStatus.PARTIAL.value
    ):
        return _partial_sentiment_text(sentiment)

    if (
        sentiment.get("status")
        != ModuleStatus.FINAL.value
    ):
        return "市场情绪模块暂未取得完整有效数据，本项不作判断。"

    rise = sentiment.get("riseCount")
    fall = sentiment.get("fallCount")
    limit_up = sentiment.get(
        "nonStLimitUpCount"
    )

    if rise is None or fall is None:
        return "市场情绪数据不完整，本项不作判断。"

    limit_text = (
        f"，非ST涨停 {limit_up} 家"
        if limit_up is not None
        else ""
    )

    if rise > fall:
        return (
            f"上涨 {rise} 家、下跌 {fall} 家"
            f"{limit_text}，上涨家数占优。"
        )

    if rise < fall:
        return (
            f"上涨 {rise} 家、下跌 {fall} 家"
            f"{limit_text}，下跌家数占优。"
        )

    return (
        f"上涨 {rise} 家、下跌 {fall} 家，"
        "涨跌家数基本持平。"
    )

def _partial_sentiment_text(
    sentiment: dict[str, Any],
) -> str:
    """历史回补日：仅涨停池数据可得，如实呈现，不编造涨跌家数。"""
    parts: list[str] = []

    limit_up = sentiment.get(
        "nonStLimitUpCount"
    )
    st_limit_up = sentiment.get(
        "stLimitUpCount"
    )
    limit_down = sentiment.get(
        "nonStLimitDownCount"
    )
    st_limit_down = sentiment.get(
        "stLimitDownCount"
    )
    broken = sentiment.get(
        "brokenLimitCount"
    )

    if limit_up is not None or st_limit_up is not None:
        parts.append(
            f"非ST涨停 {limit_up or 0} 家、"
            f"ST涨停 {st_limit_up or 0} 家"
        )

    if (
        limit_down is not None
        or st_limit_down is not None
    ):
        parts.append(
            f"非ST跌停 {limit_down or 0} 家、"
            f"ST跌停 {st_limit_down or 0} 家"
        )

    if broken is not None:
        parts.append(
            f"炸板 {broken} 家"
        )

    if parts:
        return (
            "历史回补日涨跌家数不可得；"
            + "；".join(parts)
            + "。"
        )

    return "市场情绪数据不完整，本项不作判断。"

def _rule_fund_flow(
    fund_flow: dict[str, Any] | None,
) -> str:
    if (
        not fund_flow
        or fund_flow.get("status")
        != ModuleStatus.FINAL.value
    ):
        return "主力资金模块暂未取得完整有效数据，本项不作判断。"

    inflow = fund_flow.get(
        "industryInflowTop10",
        [],
    )
    outflow = fund_flow.get(
        "industryOutflowTop10",
        [],
    )

    if not inflow and not outflow:
        return "行业资金流排名暂无有效数值。"

    parts: list[str] = []

    if inflow:
        names = "、".join(
            str(item.get("name", ""))
            for item in inflow[:3]
        )
        parts.append(
            f"行业主力净流入居前：{names}"
        )

    if outflow:
        names = "、".join(
            str(item.get("name", ""))
            for item in outflow[:3]
        )
        parts.append(
            f"行业主力净流出居前：{names}"
        )

    return "；".join(parts) + "。"

def _rule_margin(
    margin: dict[str, Any] | None,
) -> str:
    if not margin:
        return "两融模块暂未取得有效数据，本项不作判断。"

    status = margin.get("status")

    if status == ModuleStatus.PENDING.value:
        return "两融数据按 T+1 节奏回补，目前待披露。"

    if status == ModuleStatus.STALE.value:
        return "两融数据尚未更新至目标交易日。"

    if status != ModuleStatus.FINAL.value:
        return "两融模块暂未取得完整有效数据，本项不作判断。"

    balance = margin.get(
        "marginBalance"
    )
    change = margin.get(
        "marginBalanceChange"
    )

    if balance is None:
        return "两融余额数据不完整，本项不作判断。"

    if change is None:
        return (
            f"两融总余额 {balance:.2f} 亿元；"
            "暂无前一交易日余额变化数据。"
        )

    direction = (
        "增加"
        if change > 0
        else "减少"
        if change < 0
        else "持平"
    )

    return (
        f"两融总余额 {balance:.2f} 亿元，"
        f"较前一交易日{direction} "
        f"{abs(change):.2f} 亿元。"
    )

def _rule_tracks(
    tracks: dict[str, Any] | None,
) -> str:
    if not tracks:
        return "主赛道监测模块暂未取得有效数据，本项不作判断。"

    if (
        tracks.get("status")
        != ModuleStatus.FINAL.value
    ):
        return "主赛道指标尚未形成足够数据覆盖，本项不作达标/规避判断。"

    items = tracks.get(
        "items",
        [],
    )

    valid = [
        item
        for item in items
        if item.get("decision")
        != "INSUFFICIENT"
    ]

    if not valid:
        return "主赛道有效评分覆盖不足，本项不作判断。"

    pass_count = sum(
        item.get("decision") == "PASS"
        for item in valid
    )
    watch_count = sum(
        item.get("decision") == "WATCH"
        for item in valid
    )
    avoid_count = sum(
        item.get("decision") == "AVOID"
        for item in valid
    )

    return (
        f"有效监测赛道中 {pass_count} 条达标、"
        f"{watch_count} 条观察、"
        f"{avoid_count} 条规避。"
    )

def _rule_northbound(
    northbound: dict[str, Any] | None,
) -> str:
    if not northbound:
        return "北向模块暂未取得有效数据，本项不作判断。"

    mode = northbound.get("mode")

    if mode == "POST_20240819_QUARTERLY_ONLY":
        holding = northbound.get(
            "quarterlyHolding",
            {},
        )

        as_of = holding.get("asOf")

        if (
            holding.get("status")
            == ModuleStatus.FINAL.value
            and as_of
        ):
            return (
                "北向旧式日度净流入不再按原口径连续展示；"
                f"当前展示最近一期 HKEX 季度持仓（{as_of}）。"
            )

        return "北向季度持仓本次暂未取得。"

    if mode == "POST_20240819_LEGACY_IMPORTED":
        return (
            "本日北向字段来自 Legacy Excel，"
            "仅用于还原原始报表，不纳入官方连续序列。"
        )

    return "北向模块当前无可比较口径。"

def _rule_risk(
    modules: dict[str, Any],
) -> str:
    errors = [
        name
        for name, module in modules.items()
        if module.get("status")
        == ModuleStatus.ERROR.value
    ]

    pending = [
        name
        for name, module in modules.items()
        if module.get("status")
        == ModuleStatus.PENDING.value
    ]

    stale = [
        name
        for name, module in modules.items()
        if module.get("status")
        == ModuleStatus.STALE.value
    ]

    unavailable = [
        name
        for name, module in modules.items()
        if module.get("status")
        == ModuleStatus.UNAVAILABLE.value
    ]

    partial = [
        name
        for name, module in modules.items()
        if module.get("status")
        == ModuleStatus.PARTIAL.value
    ]

    parts: list[str] = []

    if errors:
        parts.append(
            "获取失败："
            + "、".join(errors)
            + "。"
        )

    if pending:
        parts.append(
            "待披露："
            + "、".join(pending)
            + "。"
        )

    if stale:
        parts.append(
            "数据延迟："
            + "、".join(stale)
            + "。"
        )

    if unavailable:
        parts.append(
            "当前不可用："
            + "、".join(unavailable)
            + "。"
        )

    if partial:
        parts.append(
            "部分数据："
            + "、".join(partial)
            + "。"
        )

    parts.append(
        "本数据仅供市场信息参考，不构成投资建议。"
    )

    return " ".join(parts)
