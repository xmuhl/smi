"""模块 1：宽基指数收盘数据采集。

多源降级（R5-P2-01）：按 config/sources.yaml 的 market 顺序
依次尝试 eastmoney / tencent / sina；国证指数优先 CNINDEX。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.status import ModuleStatus

INDICES = [
    {
        "code": "000001",
        "name": "上证指数",
        "symbol_em": "sh000001",
        "symbol_tx": "sh000001",
        "symbol_sina": "sh000001",
    },
    {
        "code": "399001",
        "name": "深证成指",
        "symbol_em": "sz399001",
        "symbol_tx": "sz399001",
        "symbol_sina": "sz399001",
    },
    {
        "code": "399006",
        "name": "创业板指",
        "symbol_em": "sz399006",
        "symbol_tx": "sz399006",
        "symbol_sina": "sz399006",
    },
    {
        "code": "000688",
        "name": "科创50",
        "symbol_em": "sh000688",
        "symbol_tx": "sh000688",
        "symbol_sina": "sh000688",
    },
    {
        "code": "000300",
        "name": "沪深300",
        "symbol_em": "sh000300",
        "symbol_tx": "sh000300",
        "symbol_sina": "sh000300",
    },
    {
        "code": "899050",
        "name": "北证50",
        "symbol_em": "bj899050",
        "symbol_tx": "bj899050",
        "symbol_sina": "bj899050",
    },
    {
        "code": "399311",
        "name": "国证1000",
        "symbol_cni": "399311",
        "symbol_tx": "sz399311",
        "symbol_sina": "sz399311",
        "sources": ["cni", "tencent", "sina"],
    },
    {
        "code": "399303",
        "name": "国证2000",
        "symbol_cni": "399303",
        "symbol_tx": "sz399303",
        "symbol_sina": "sz399303",
        "sources": ["cni", "tencent", "sina"],
    },
]


def _fetch_index_close(
    index: dict[str, Any],
    trade_date: str,
    start: str,
    end: str,
    source: str,
) -> tuple[float | None, float | None]:
    """按指定源获取 (close, previous_close)。源失败时抛出异常。"""
    import akshare as ak

    if source == "eastmoney":
        df = ak.stock_zh_index_daily_em(
            symbol=index["symbol_em"],
            start_date=start,
            end_date=end,
        )
        current_row, previous_row = _target_and_previous(
            df,
            trade_date,
            date_columns=("date", "日期"),
        )
        return (
            _num(current_row.get("close")),
            _num(previous_row.get("close")),
        )

    if source == "tencent":
        df = ak.stock_zh_index_daily_tx(
            symbol=index["symbol_tx"],
        )
        current_row, previous_row = _target_and_previous(
            df,
            trade_date,
            date_columns=("date", "日期"),
        )
        return (
            _num(current_row.get("close")),
            _num(previous_row.get("close")),
        )

    if source == "sina":
        df = ak.stock_zh_index_daily(
            symbol=index["symbol_sina"],
        )
        current_row, previous_row = _target_and_previous(
            df,
            trade_date,
            date_columns=("date", "日期"),
        )
        return (
            _num(current_row.get("close")),
            _num(previous_row.get("close")),
        )

    if source == "cni":
        df = ak.index_hist_cni(
            symbol=index["symbol_cni"],
            start_date=start,
            end_date=end,
        )
        current_row, previous_row = _target_and_previous(
            df,
            trade_date,
            date_columns=("日期",),
        )
        return (
            _num(current_row.get("收盘价")),
            _num(previous_row.get("收盘价")),
        )

    raise ValueError(f"unknown market source: {source}")


def collect_market_index(
    trade_date: str,
) -> dict[str, Any]:
    """使用至少两个交易日计算真正的“昨收→今收”涨跌幅。"""
    target = date.fromisoformat(trade_date)
    start = (
        target - timedelta(days=30)
    ).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")

    items: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx in INDICES:
        entry: dict[str, Any] = {
            "code": idx["code"],
            "name": idx["name"],
            "close": None,
            "previousClose": None,
            "changePct": None,
            "source": None,
        }

        try:
            if "sources" in idx:
                close, previous_close, used = _with_source_list(
                    idx,
                    trade_date,
                    start,
                    end,
                    list(idx["sources"]),
                )
            else:
                close, previous_close, used = _with_source_order(
                    idx,
                    trade_date,
                    start,
                    end,
                    "market",
                    ["eastmoney", "tencent", "sina"],
                )

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
            entry["source"] = used.upper() if used else None

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
        "source": ["EASTMONEY", "TENCENT", "SINA", "CNINDEX"],
        "items": items,
    }

    if errors:
        result["errors"] = errors

    return result


def _with_source_order(
    index: dict[str, Any],
    trade_date: str,
    start: str,
    end: str,
    kind: str,
    defaults: list[str],
) -> tuple[float | None, float | None, str | None]:
    """按 sources.yaml 优先级取 (close, previous_close, used_source)。"""
    value, used, _ = try_sources(
        kind,
        defaults,
        lambda source: _fetch_index_close(
            index,
            trade_date,
            start,
            end,
            source,
        ),
    )
    if value is None:
        raise ValueError("all market sources failed")
    return value[0], value[1], used


def _with_source_list(
    index: dict[str, Any],
    trade_date: str,
    start: str,
    end: str,
    sources: list[str],
) -> tuple[float | None, float | None, str | None]:
    """按显式源列表尝试取 (close, previous_close, used_source)。"""
    errors: list[str] = []

    for source in sources:
        try:
            close, previous_close = _fetch_index_close(
                index,
                trade_date,
                start,
                end,
                source,
            )
            return close, previous_close, source
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")

    raise ValueError(
        "all sources failed: " + "; ".join(errors)
    )


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
