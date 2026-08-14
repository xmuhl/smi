"""R5-P2-01：多源降级适配器与模块降级路径测试。"""

from __future__ import annotations

import sys
from types import ModuleType

import pandas as pd

from collector.adapters.sources import source_order, try_sources


def test_source_order_merges_primary_fallback_and_defaults():
    order = source_order("spot", ["eastmoney"])

    assert order[0] == "eastmoney"
    assert order[1] == "sina"
    assert order == ["eastmoney", "sina"]


def test_source_order_deduplicates():
    order = source_order(
        "market",
        ["eastmoney", "tencent", "sina"],
    )

    assert order == ["eastmoney", "tencent", "sina"]


def test_try_sources_falls_back_on_failure():
    calls = []

    def call(source):
        calls.append(source)
        if source == "eastmoney":
            raise ConnectionError("blocked")
        return "ok-" + source

    value, used, errors = try_sources(
        "spot",
        ["eastmoney"],
        call,
    )

    assert value == "ok-sina"
    assert used == "sina"
    assert errors == []
    assert calls == ["eastmoney", "sina"]


def test_try_sources_all_fail_returns_errors():
    def call(source):
        raise ValueError(f"{source} exploded")

    value, used, errors = try_sources(
        "spot",
        ["eastmoney"],
        call,
    )

    assert value is None
    assert used is None
    assert len(errors) == 2
    assert "eastmoney" in errors[0]
    assert "sina" in errors[1]


def test_market_index_falls_back_to_tencent():
    fake = ModuleType("akshare")

    def stock_zh_index_daily_em(*args, **kwargs):
        raise ConnectionError("push2his blocked")

    def stock_zh_index_daily_tx(symbol=None):
        return pd.DataFrame({
            "date": ["2026-08-13", "2026-08-14"],
            "open": [100.0, 101.0],
            "close": [100.5, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 100.0],
        })

    fake.stock_zh_index_daily_em = stock_zh_index_daily_em
    fake.stock_zh_index_daily_tx = stock_zh_index_daily_tx
    sys.modules["akshare"] = fake

    try:
        from collector.modules.market_index import collect_market_index

        result = collect_market_index("2026-08-14")

        assert result["status"] == "FINAL"
        sh = next(
            item for item in result["items"]
            if item["code"] == "000001"
        )
        assert sh["close"] == 102.0
        assert sh["previousClose"] == 100.5
        assert sh["source"] == "TENCENT"
    finally:
        sys.modules.pop("akshare", None)


def test_turnover_falls_back_to_sina_spot():
    fake = ModuleType("akshare")

    def stock_sh_a_spot_em(*args, **kwargs):
        raise ConnectionError("82.push2 blocked")

    def stock_sz_a_spot_em(*args, **kwargs):
        raise ConnectionError("82.push2 blocked")

    def stock_zh_a_spot(*args, **kwargs):
        return pd.DataFrame({
            "代码": ["sh600000", "sz000001", "bj899050"],
            "成交额": [5.0e9, 3.0e9, 1.0e8],
        })

    fake.stock_sh_a_spot_em = stock_sh_a_spot_em
    fake.stock_sz_a_spot_em = stock_sz_a_spot_em
    fake.stock_zh_a_spot = stock_zh_a_spot
    sys.modules["akshare"] = fake

    try:
        from collector.modules.turnover import collect_turnover

        result = collect_turnover(
            "2026-08-14",
            market_rules={},
        )

        assert result["status"] == "FINAL"
        # 8.0e9 元 = 80 亿元（不含北交所 1 亿）
        assert result["turnoverToday"] == 80.0
        assert result["source"] == ["SINA"]
    finally:
        sys.modules.pop("akshare", None)


def test_sentiment_falls_back_to_sina_spot():
    fake = ModuleType("akshare")

    def stock_zh_a_spot_em(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_zh_a_spot(*args, **kwargs):
        return pd.DataFrame({
            "代码": ["sh600000", "sz000001", "sz300001", "sz300002"],
            "涨跌幅": [1.0, -1.0, 0.0, None],
        })

    def stock_zt_pool_em(*args, **kwargs):
        raise ConnectionError("zt pool blocked")

    def stock_zt_pool_dtgc_em(*args, **kwargs):
        raise ConnectionError("dt pool blocked")

    def stock_zt_pool_zbgc_em(*args, **kwargs):
        raise ConnectionError("zbgc pool blocked")

    fake.stock_zh_a_spot_em = stock_zh_a_spot_em
    fake.stock_zh_a_spot = stock_zh_a_spot
    fake.stock_zt_pool_em = stock_zt_pool_em
    fake.stock_zt_pool_dtgc_em = stock_zt_pool_dtgc_em
    fake.stock_zt_pool_zbgc_em = stock_zt_pool_zbgc_em
    sys.modules["akshare"] = fake

    try:
        from collector.modules.sentiment import collect_sentiment

        result = collect_sentiment("2026-08-14")

        assert result["riseCount"] == 1
        assert result["fallCount"] == 1
        assert result["flatCount"] == 1
        assert result["suspendedCount"] == 1
        assert result["spotSource"] == "SINA"
        # 东财独有池接口失败 → 状态如实标记 ERROR
        assert result["status"] == "ERROR"
    finally:
        sys.modules.pop("akshare", None)


def test_is_retryable_classifies_errors():
    from collector.jobs.close_snapshot import _is_retryable

    assert _is_retryable(["REQUIRED_INDEX_MISSING"])
    assert _is_retryable(["MARKET_DATE_NOT_VERIFIED"])
    assert _is_retryable(["STOCK_UNIVERSE_TOO_SMALL:5<4000"])
    assert not _is_retryable(["CALENDAR_NOT_TRADING_DAY"])
    assert not _is_retryable([])
    assert not _is_retryable(["REQUIRED_INDEX_MISSING", "CALENDAR_NOT_TRADING_DAY"])
