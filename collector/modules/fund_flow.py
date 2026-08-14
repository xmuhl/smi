"""模块 5：主力资金流向（统一换算为亿元，多源降级）。

R6：东财失败时降级同花顺（THS）资金流表，method 字段区分口径：
EASTMONEY_MAIN_FORCE / THS_MAIN_FORCE。THS 行业/概念净额已是亿元；
个股净额为带单位字符串（亿/万）。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus


def _parse_yi_amount(
    value,
    *,\
    string_mode: bool = False,
) -> float | None:
    """解析 THS 资金流净额为亿元。

    string_mode=False（行业/概念）：列值已是亿元数字；
    string_mode=True（个股）：列值为带单位字符串，
    亿/万 后缀分别换算，无单位按元计（THS 小额净额格式）。
    超过 500 亿视为数据异常，返回 None 跳过。
    """
    if string_mode:
        text = str(value or "").strip().replace(",", "")
        match = re.match(r"^(-?[\d.]+)(亿|万)?$", text)
        if not match:
            return None
        try:
            number = float(match.group(1))
        except (TypeError, ValueError):
            return None
        unit = match.group(2)
        if unit == "万":
            number = number / 1e4
        elif not unit:
            number = number / 1e8
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    if pd.isna(number):
        return None
    if abs(number) > 500:
        return None
    return number


def _normalize_code(value) -> str | None:
    """A 股代码规范化：int/str → 标准 6 位字符串（R7-P2-02 修复）。

    拒绝 NaN/空/非纯数字/超过 6 位异常值。
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    if len(text) > 6:
        return None
    return text.zfill(6)

def _fetch_fund_flow(
    source: str,
) -> dict[str, Any]:
    """按指定源返回六组 TOP10 资金流。"""
    import akshare as ak

    if source == "eastmoney":
        industry = ak.stock_sector_fund_flow_rank(
            indicator="今日",
            sector_type="行业资金流",
        )
        concept = ak.stock_sector_fund_flow_rank(
            indicator="今日",
            sector_type="概念资金流",
        )
        stock = ak.stock_individual_fund_flow_rank(
            indicator="今日",
        )
        return {
            "industryInflowTop10": _split_in_out(industry)[0][:10],
            "industryOutflowTop10": _split_in_out(industry)[1][:10],
            "conceptInflowTop10": _split_in_out(concept)[0][:10],
            "conceptOutflowTop10": _split_in_out(concept)[1][:10],
            "stockInflowTop10": _split_in_out(stock)[0][:10],
            "stockOutflowTop10": _split_in_out(stock)[1][:10],
        }

    if source == "ths":
        industry = ak.stock_fund_flow_industry(
            symbol="即时",
        )
        concept = ak.stock_fund_flow_concept(
            symbol="即时",
        )
        stock = ak.stock_fund_flow_individual(
            symbol="即时",
        )
        return {
            "industryInflowTop10": _split_ths(industry, "行业", "净额")[0][:10],
            "industryOutflowTop10": _split_ths(industry, "行业", "净额")[1][:10],
            "conceptInflowTop10": _split_ths(concept, "行业", "净额")[0][:10],
            "conceptOutflowTop10": _split_ths(concept, "行业", "净额")[1][:10],
            "stockInflowTop10": _split_ths(stock, "股票简称", "净额", code_col="股票代码")[0][:10],
            "stockOutflowTop10": _split_ths(stock, "股票简称", "净额", code_col="股票代码")[1][:10],
        }

    raise ValueError(f"unknown fundflow source: {source}")


def collect_fund_flow(
    trade_date: str,
) -> dict[str, Any]:
    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": trade_date,
            "method": "EASTMONEY_MAIN_FORCE",
            "unit": "亿元",
            "reason": "HISTORICAL_TODAY_RANK_NOT_SUPPORTED",
            "industryInflowTop10": [],
            "industryOutflowTop10": [],
            "conceptInflowTop10": [],
            "conceptOutflowTop10": [],
            "stockInflowTop10": [],
            "stockOutflowTop10": [],
        }

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "method": "EASTMONEY_MAIN_FORCE",
        "unit": "亿元",
        "industryInflowTop10": [],
        "industryOutflowTop10": [],
        "conceptInflowTop10": [],
        "conceptOutflowTop10": [],
        "stockInflowTop10": [],
        "stockOutflowTop10": [],
        "errors": [],
    }

    try:
        flow, used, source_errors = try_sources(
            "fundflow",
            ["eastmoney"],
            _fetch_fund_flow,
        )

        if flow is None:
            raise ValueError(
                "all fundflow sources failed: "
                + "; ".join(source_errors or [])
            )

        result.update(flow)
        result["method"] = (
            "THS_MAIN_FORCE"
            if used == "ths"
            else "EASTMONEY_MAIN_FORCE"
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(str(exc))
        result["status"] = ModuleStatus.ERROR.value

    return result


def _split_in_out(
    df,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """东财口径：净额原始金额 → 亿元。"""
    if df is None or df.empty:
        raise ValueError("empty fund-flow dataframe")

    name_col = _pick_col(
        df,
        (
            "名称",
            "name",
            "股票名称",
        ),
    )

    code_col = _pick_col(
        df,
        (
            "代码",
            "code",
        ),
    )

    main_col = _pick_col(
        df,
        (
            "今日主力净流入-净额",
            "主力净流入-净额",
            "主力净流入",
            "主力净额",
        ),
    )

    if name_col is None:
        raise ValueError(
            f"name column missing: {list(df.columns)}"
        )

    if main_col is None:
        raise ValueError(
            f"main-flow column missing: {list(df.columns)}"
        )

    rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        raw_value = pd.to_numeric(
            row.get(main_col),
            errors="coerce",
        )

        if pd.isna(raw_value):
            continue

        value_yi = float(raw_value) / 1e8

        rows.append(
            {
                "code": (
                    str(row.get(code_col, "") or "")
                    if code_col
                    else ""
                ),
                "name": str(
                    row.get(name_col, "") or ""
                ),
                "netInflowYi": round(
                    value_yi,
                    4,
                ),
            }
        )

    if not rows:
        raise ValueError(
            "no valid fund-flow rows"
        )

    return _sort_in_out(rows)


def _split_ths(
    df,
    name_col: str,
    net_col: str,
    *,
    code_col: str | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """同花顺口径：净额已是亿元（个股为带单位字符串）。"""
    if df is None or df.empty:
        raise ValueError("empty ths fund-flow dataframe")

    rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        value_yi = _parse_yi_amount(
            row.get(net_col),
            string_mode=code_col is not None,
        )

        if value_yi is None:
            continue

        rows.append(
            {
                "code": (
                    _normalize_code(row.get(code_col))
                    if code_col
                    else ""
                ),
                "name": str(
                    row.get(name_col, "") or ""
                ),
                "netInflowYi": round(
                    value_yi,
                    4,
                ),
            }
        )

    if not rows:
        raise ValueError(
            "no valid ths fund-flow rows"
        )

    return _sort_in_out(rows)


def _sort_in_out(
    rows: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    inflow = sorted(
        (
            row
            for row in rows
            if row["netInflowYi"] > 0
        ),
        key=lambda row: row["netInflowYi"],
        reverse=True,
    )

    outflow = sorted(
        (
            row
            for row in rows
            if row["netInflowYi"] < 0
        ),
        key=lambda row: row["netInflowYi"],
    )

    return inflow, outflow


def _pick_col(
    df,
    candidates: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None
