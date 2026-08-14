"""模块 5：主力资金流向（东方财富口径，统一换算为亿元）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus

def collect_fund_flow(
    trade_date: str,
) -> dict[str, Any]:
    import akshare as ak

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
        industry = (
            ak.stock_sector_fund_flow_rank(
                indicator="今日",
                sector_type="行业资金流",
            )
        )

        inflow, outflow = _split_in_out(
            industry
        )

        result["industryInflowTop10"] = (
            inflow[:10]
        )
        result["industryOutflowTop10"] = (
            outflow[:10]
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"industry flow: {exc}"
        )

    try:
        concept = (
            ak.stock_sector_fund_flow_rank(
                indicator="今日",
                sector_type="概念资金流",
            )
        )

        inflow, outflow = _split_in_out(
            concept
        )

        result["conceptInflowTop10"] = (
            inflow[:10]
        )
        result["conceptOutflowTop10"] = (
            outflow[:10]
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"concept flow: {exc}"
        )

    try:
        stock = (
            ak.stock_individual_fund_flow_rank(
                indicator="今日"
            )
        )

        inflow, outflow = _split_in_out(
            stock
        )

        result["stockInflowTop10"] = inflow[:10]
        result["stockOutflowTop10"] = outflow[:10]

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"stock flow: {exc}"
        )

    if result["errors"]:
        result["status"] = ModuleStatus.ERROR.value

    return result

def _split_in_out(
    df,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
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

        # 东方财富资金流排名净额按原始金额处理，
        # SMI 统一换算为亿元。
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
