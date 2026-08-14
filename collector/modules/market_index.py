"""模块 1：宽基指数收盘数据采集。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from collector.status import ModuleStatus

INDICES = [
    {
        "code": "000001",
        "name": "上证指数",
        "symbol_em": "sh000001",
    },
    {
        "code": "399001",
        "name": "深证成指",
        "symbol_em": "sz399001",
    },
    {
        "code": "399006",
        "name": "创业板指",
        "symbol_em": "sz399006",
    },
    {
        "code": "000688",
        "name": "科创50",
        "symbol_em": "sh000688",
    },
    {
        "code": "000300",
        "name": "沪深300",
        "symbol_em": "sh000300",
    },
    {
        "code": "899050",
        "name": "北证50",
        "symbol_em": "bj899050",
    },
    {
        "code": "399311",
        "name": "国证1000",
        "symbol_cni": "399311",
    },
    {
        "code": "399303",
        "name": "国证2000",
        "symbol_cni": "399303",
    },
]

def collect_market_index(
    trade_date: str,
) -> dict[str, Any]:
    """使用至少两个交易日计算真正的“昨收→今收”涨跌幅。"""
    import akshare as ak

    target = date.fromisoformat(trade_date)
    start = (
        target - timedelta(days=30)
    ).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")

    items: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx in INDICES:
        entry = {
            "code": idx["code"],
            "name": idx["name"],
            "close": None,
            "previousClose": None,
            "changePct": None,
            "source": None,
        }

        try:
            if "symbol_cni" in idx:
                df = ak.index_hist_cni(
                    symbol=idx["symbol_cni"],
                    start_date=start,
                    end_date=end,
                )

                current_row, previous_row = (
                    _target_and_previous(
                        df,
                        trade_date,
                        date_columns=("日期",),
                    )
                )

                close = _num(
                    current_row.get("收盘价")
                )
                previous_close = _num(
                    previous_row.get("收盘价")
                )

                source = "CNINDEX"
            else:
                df = ak.stock_zh_index_daily_em(
                    symbol=idx["symbol_em"],
                    start_date=start,
                    end_date=end,
                )

                current_row, previous_row = (
                    _target_and_previous(
                        df,
                        trade_date,
                        date_columns=("date", "日期"),
                    )
                )

                close = _num(
                    current_row.get("close")
                )
                previous_close = _num(
                    previous_row.get("close")
                )

                source = "EASTMONEY"

            if close is None or previous_close is None:
                raise ValueError(
                    "close/previous close missing"
                )

            if previous_close <= 0:
                raise ValueError(
                    f"invalid previous close: {previous_close}"
                )

            entry["close"] = round(close, 4)
            entry["previousClose"] = round(
                previous_close,
                4,
            )
            entry["changePct"] = round(
                (close / previous_close - 1) * 100,
                2,
            )
            entry["source"] = source

        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"{idx['code']} {idx['name']}: {exc}"
            )

        items.append(entry)

    status = (
        ModuleStatus.ERROR.value
        if errors
        else ModuleStatus.FINAL.value
    )

    result: dict[str, Any] = {
        "status": status,
        "dataDate": trade_date,
        "source": [
            "EASTMONEY",
            "CNINDEX",
        ],
        "items": items,
    }

    if errors:
        result["errors"] = errors

    return result

def _target_and_previous(
    df,
    trade_date: str,
    *,
    date_columns: tuple[str, ...],
):
    if df is None or df.empty:
        raise ValueError("empty dataframe")

    date_col = next(
        (
            name
            for name in date_columns
            if name in df.columns
        ),
        None,
    )

    if date_col is None:
        raise ValueError(
            f"date column missing: {list(df.columns)}"
        )

    work = df.copy()

    work["__date"] = pd.to_datetime(
        work[date_col],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    work = work[
        work["__date"].notna()
        & (work["__date"] <= trade_date)
    ].sort_values("__date")

    target_rows = work[
        work["__date"] == trade_date
    ]

    if target_rows.empty:
        raise ValueError(
            f"no data for target date {trade_date}"
        )

    target_index = target_rows.index[-1]
    position = work.index.get_loc(target_index)

    if not isinstance(position, int) or position <= 0:
        raise ValueError(
            f"previous close unavailable for {trade_date}"
        )

    return (
        work.iloc[position],
        work.iloc[position - 1],
    )

def _num(value) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if pd.isna(number):
        return None

    return number
