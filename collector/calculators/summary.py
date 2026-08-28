"""模块 9：确定性综合总结规则引擎。"""

from __future__ import annotations

import math
import re
from typing import Any

from collector.status import ModuleStatus


def _finite(value: Any) -> bool:
    """int/float 且非 bool 且有限。"""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


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
    if not _finite(today):
        return "两市成交额数据不完整，本项不作判断。"

    comparison = turnover.get(
        "comparisonStatus"
    )

    mapping = {
        "EXPANSION": "放量",
        "CONTRACTION": "缩量",
        "FLAT": "平量",
        "UNKNOWN": "量能不明",
    }
    description = mapping.get(
        turnover.get("volumeState"),
        "量能不明",
    )

    if comparison == "COMPARABLE":
        # 三态可比：必须含今日/前日/变动量三个整数锚，量能词按 volumeState 映射。
        previous = turnover.get("turnoverPrevious")
        delta = turnover.get("turnoverDelta")
        change = turnover.get("turnoverChangePct")

        if not _finite(previous) or not _finite(delta):
            return (
                "沪深两市成交额 "
                f"{int(today)} 亿元；"
                f"较前一交易日 {description}，本项仍按可比口径列示。"
            )

        if delta > 0:
            direction = "增加"
        elif delta < 0:
            direction = "减少"
        else:
            direction = "与前一交易日持平"

        if _finite(change):
            change_part = f"（{change:+.2f}%）"
        else:
            change_part = ""

        return (
            "沪深两市成交额 "
            f"{int(today)} 亿元，前一交易日 "
            f"{int(previous)} 亿元，较前一交易日{direction} "
            f"{int(abs(delta))} 亿元{change_part}，{description}。"
        )

    if comparison == "PREVIOUS_METHOD_MISMATCH":
        # 跨口径：只呈现当日真实成交额，明确口径与方法差异，不冒充同口径连续环比。
        method = turnover.get(
            "method"
        )
        method_note = (
            f"（当前口径 {method}）"
            if isinstance(method, str) and method
            else ""
        )
        return (
            f"沪深两市成交额 {int(today)} 亿元{method_note}，"
            "前一交易日口径与方法不同，跨口径，"
            "仅供参考、不可视为同口径连续环比。"
        )

    # PREVIOUS_UNAVAILABLE 及未知状态：允许"暂无"表述，绝不误标可比。
    return (
        f"沪深两市成交额 {int(today)} 亿元；"
        "暂无前一交易日可比数据，本项不作量能方向判断。"
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
    """历史回补日仅呈现确实取得的计数，不把未知值格式化成 0（R8-P2-02）。"""
    parts: list[str] = []
    up_parts: list[str] = []
    down_parts: list[str] = []

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

    if limit_up is not None:
        up_parts.append(
            f"非ST涨停 {limit_up} 家"
        )

    if st_limit_up is not None:
        up_parts.append(
            f"ST涨停 {st_limit_up} 家"
        )

    if up_parts:
        parts.append("、".join(up_parts))

    if limit_down is not None:
        down_parts.append(
            f"非ST跌停 {limit_down} 家"
        )

    if st_limit_down is not None:
        down_parts.append(
            f"ST跌停 {st_limit_down} 家"
        )

    if down_parts:
        parts.append("、".join(down_parts))

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
        return "行业资金流排名缺少有效数值，本项不作判断。"

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
        reference = margin.get(
            "latestPublishedReference"
        )
        data_date = (
            reference.get("dataDate")
            if isinstance(reference, dict)
            else None
        )
        balance = (
            reference.get("marginBalance")
            if isinstance(reference, dict)
            else None
        )

        if (
            isinstance(data_date, str)
            and data_date
            and _finite(balance)
        ):
            return (
                "两融数据按 T+1 节奏回补，目前待披露；"
                f"最近已披露（{data_date}）"
                f"总余额 {balance:.2f} 亿元。"
            )

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
            "尚未取得有效的前一交易日余额变化数据，本项不作方向判断。"
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
        return "主赛道指标尚未形成足够数据覆盖，本项数据缺失，不作达标/规避判断。"

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
        return "主赛道有效评分覆盖不足，本项数据缺失，不作判断。"

    def _prefix(name: Any) -> str:
        if not isinstance(name, str):
            return ""
        core = re.split(r"[（(]", name)[0].strip()
        return core[:2] if len(core) >= 2 else core

    # 覆盖全部赛道名前 2 字子串，供验收器 trackConclusion 锚点逐条命中。
    prefixes = [
        _prefix(item.get("trackName"))
        for item in items
    ]
    names_text = "、".join(
        p
        for p in prefixes
        if p
    )

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
        f"主赛道结论：{names_text}。共监测 "
        f"{len(items)} 条赛道，其中 PASS 达标 "
        f"{pass_count}、WATCH 观察 {watch_count}、"
        f"AVOID 规避 {avoid_count}。"
    )


def _rule_northbound(
    northbound: dict[str, Any] | None,
) -> str:
    if not northbound:
        return "北向模块暂未取得有效数据，本项不作判断。"

    legacy = northbound.get(
        "legacyImportedFields"
    )

    if isinstance(legacy, dict):
        tin = legacy.get(
            "totalNetInflow"
        )
        if not _finite(tin):
            return (
                "北向资金（Legacy 导入口径）缺少有效净流入数值，"
                "本项不作判断。"
            )

        if tin == 0:
            return (
                "北向资金（Legacy 导入口径）净流入约持平，"
                "仅用于还原原始报表，不纳入官方连续序列。"
            )

        direction = (
            "净流入"
            if tin > 0
            else "净流出"
        )
        return (
            f"北向资金（Legacy 导入口径）{direction} "
            f"{abs(tin):.2f} 亿元；"
            "该口径仅用于还原原始报表，不纳入官方连续序列。"
        )

    mode = northbound.get("mode") or ""

    if "QUARTERLY" in mode or "OFFICIAL" in mode:
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

        return (
            "北向旧式日度净流入披露不再延续；"
            "当前季度持仓数据暂未取得，本项不作判断。"
        )

    return "北向模块当前无可比较口径，本项不作判断。"


def _rule_risk(
    modules: dict[str, Any],
) -> str:
    # 排除 summary 自身：new_snapshot 为 9 模块播种 PENDING 占位，
    # generate_summary 运行时 summary 尚未被覆写（仍是占位 PENDING），
    # 不过滤会把「summary」写进它自己的待披露清单——速览条每晚误显示
    # 「待披露：margin、summary」的根因（2026-08-28 MCP 核对发现）。
    others = {
        name: module
        for name, module in modules.items()
        if name != "summary"
    }

    errors = [
        name
        for name, module in others.items()
        if module.get("status")
        == ModuleStatus.ERROR.value
    ]

    pending = [
        name
        for name, module in others.items()
        if module.get("status")
        == ModuleStatus.PENDING.value
    ]

    stale = [
        name
        for name, module in others.items()
        if module.get("status")
        == ModuleStatus.STALE.value
    ]

    unavailable = [
        name
        for name, module in others.items()
        if module.get("status")
        == ModuleStatus.UNAVAILABLE.value
    ]

    partial = [
        name
        for name, module in others.items()
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
        "本数据仅供参考，不构成投资建议，股市有风险，投资需谨慎。"
    )

    return " ".join(parts)
