"""模块 1：宽基指数收盘数据采集。

多源降级（R5-P2-01）：按 config/sources.yaml 的 market 顺序
依次尝试 eastmoney / eastmoney_delay（东财延迟主机，仅当日 8 指数
ulist，见 collector/adapters/eastmoney_delay.py）/ tencent / sina；
国证指数优先 CNINDEX（显式链 cni -> tencent -> sina）。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.status import ModuleStatus
from collector.netguard import net_guard

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


# 多只指数受控并发度：6 线程为保守值，防触发源站限流；串行 37 只/天实测
# 237s（东财被封时每源超时重试），受控并发显著缩短采集耗时。
_MI_CONCURRENCY = 6


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

    if source == "eastmoney_delay":
        # R9：东财延迟主机（push2delay）当日收盘行情，ulist 一次取全。
        # 该主机无历史，非当日调用在适配器内直接失败，由降级链兜底。
        from collector.adapters.eastmoney_delay import (
            fetch_index_quotes,
            secid_from_symbol,
        )

        quotes = _delay_index_quotes(
            trade_date,
            fetch_index_quotes,
        )
        secid = secid_from_symbol(
            index["symbol_em"]
        )

        if secid not in quotes:
            raise ValueError(
                f"eastmoney_delay missing {secid}"
            )

        close, previous = quotes[secid]
        return close, previous

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


def _fetch_index_entry(
    idx: dict[str, Any],
    trade_date: str,
    start: str,
    end: str,
) -> tuple[dict[str, Any], dict[str, Any] | Exception | None]:
    """并发工作函数：单只指数多源降级 -> (index, entry_or_exc)。

    - 与 sectors._fetch_th_boards_concurrent 同风格：工作函数返回
      (index, entry_or_exc) 元组，主线程按 INDICES 原序汇总；
    - 线程内不共享可变状态，akshare 在 _fetch_index_close 内独立 import
      （经 sys.modules 缓存命中测试 monkeypatch 的模块级属性）；
    - 单只指数异常只影响自身：entry 保持 None 骨架并随 exc 返回，
      不中断其它指数（与串行语义一致）。
    """
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
            (
                close,
                previous_close,
                used,
                source_warnings,
            ) = _with_source_list(
                idx,
                trade_date,
                start,
                end,
                list(idx["sources"]),
            )
        else:
            (
                close,
                previous_close,
                used,
                source_warnings,
            ) = _with_source_order(
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

        if source_warnings:
            entry["sourceWarnings"] = source_warnings

        return idx, entry

    except Exception as exc:  # noqa: BLE001
        return idx, exc


@net_guard(timeout=180.0, retries=1)
def collect_market_index(
    trade_date: str,
) -> dict[str, Any]:
    """使用至少两个交易日计算真正的昨收->今收涨跌幅。

    多只指数用 ThreadPoolExecutor（_MI_CONCURRENCY=6）受控并发拉取，
    替代逐指数串行多源降级（东财被封时每源超时重试，37 只/天实测 237s）。
    executor.map 按 INDICES 提交顺序返回结果，主线程串行汇总，输出顺序
    与串行完全一致；线程内无共享可变状态，单只异常不波及其它指数。
    """
    target = date.fromisoformat(trade_date)
    start = (
        target - timedelta(days=30)
    ).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")

    from concurrent.futures import ThreadPoolExecutor

    items: list[dict[str, Any]] = []
    errors: list[str] = []

    def _fetch_one(
        idx: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | Exception | None]:
        # akshare 由 _fetch_index_close 内独立 import（经 sys.modules 缓存
        # 命中测试 monkeypatch 的模块级属性），此处复用同一 worker。
        return _fetch_index_entry(idx, trade_date, start, end)

    with ThreadPoolExecutor(
        max_workers=_MI_CONCURRENCY
    ) as executor:
        for idx, entry_or_exc in executor.map(
            _fetch_one,
            INDICES,
        ):
            if isinstance(entry_or_exc, Exception):
                errors.append(
                    f"{idx['code']} {idx['name']}: {entry_or_exc}"
                )
                items.append(
                    {
                        "code": idx["code"],
                        "name": idx["name"],
                        "close": None,
                        "previousClose": None,
                        "changePct": None,
                        "source": None,
                    }
                )
            else:
                items.append(entry_or_exc)

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
            "EASTMONEY_DELAY",
            "TENCENT",
            "SINA",
            "CNINDEX",
        ],
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
) -> tuple[float | None, float | None, str | None, list[str]]:
    """按 sources.yaml 优先级取 (close, previous_close, used_source, prior_errors)。

    R9-P3-02：try_sources 成功时也保留前序源失败记录（运维观测），
    不放入业务 errors（不影响 health）。
    """
    value, used, source_errors = try_sources(
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
    return value[0], value[1], used, source_errors


def _with_source_list(
    index: dict[str, Any],
    trade_date: str,
    start: str,
    end: str,
    sources: list[str],
) -> tuple[float | None, float | None, str | None, list[str]]:
    """按显式源列表取指数，并保留成功前失败记录（R9-P3-02）。"""
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
            return close, previous_close, source, errors
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")

    raise ValueError(
        "all sources failed: " + "; ".join(errors)
    )


def _delay_index_quotes(
    trade_date: str,
    fetcher,
) -> dict[str, tuple[float, float]]:
    """东财 delay 指数行情按交易日缓存，避免每个指数重复拉取。

    R9-P2-02：先抓取成功再原子更新 cache——新日期抓取失败时不得把
    旧日期 quotes 重新标成新日期（否则下一次同日调用会误用旧数据）。
    """
    if (
        _DELAY_CACHE["date"] != trade_date
        or _DELAY_CACHE["quotes"] is None
    ):
        quotes = fetcher(trade_date)
        _DELAY_CACHE["date"] = trade_date
        _DELAY_CACHE["quotes"] = quotes

    return _DELAY_CACHE["quotes"]


_DELAY_CACHE: dict[str, Any] = {
    "date": None,
    "quotes": None,
}


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