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


def test_sectors_falls_back_to_ths():
    fake = ModuleType("akshare")

    def stock_board_industry_name_em(*args, **kwargs):
        raise ConnectionError("17.push2 blocked")

    def stock_board_concept_name_em(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_fund_flow_industry(symbol=None):
        return pd.DataFrame({
            "行业": ["电子化学品", "半导体", "白酒", "煤炭", "银行", "房地产"],
            "行业-涨跌幅": [4.07, 3.2, -0.5, -1.1, -0.3, -2.0],
            "净额": [16.19, 10.0, -2.0, -3.0, -1.0, -5.0],
            "公司家数": [43, 120, 20, 30, 42, 90],
            "领涨股": ["中石科技", "北方华创", "贵州茅台", "中国神华", "招商银行", "万科A"],
        })

    def stock_fund_flow_concept(symbol=None):
        return pd.DataFrame({
            "行业": ["CPO", "F5G", "AI", "光伏"],
            "行业-涨跌幅": [2.94, 2.91, -0.8, -1.5],
            "净额": [132.76, 77.44, -5.0, -8.0],
            "公司家数": [205, 36, 300, 150],
            "领涨股": ["金戈新材", "共进股份", "寒武纪", "隆基绿能"],
        })

    fake.stock_board_industry_name_em = stock_board_industry_name_em
    fake.stock_board_concept_name_em = stock_board_concept_name_em
    fake.stock_fund_flow_industry = stock_fund_flow_industry
    fake.stock_fund_flow_concept = stock_fund_flow_concept
    sys.modules["akshare"] = fake

    try:
        from collector.modules.sectors import collect_sectors

        result = collect_sectors("2026-08-14")

        assert result["status"] == "FINAL"
        assert result["method"] == "THS"
        assert result["industryTop5"][0]["name"] == "电子化学品"
        assert result["industryTop5"][0]["changePct"] == 4.07
        assert result["industryTop5"][0]["leader"] == "中石科技"
        assert result["industryBottom5"][0]["name"] == "房地产"
        assert result["conceptTop5"][0]["name"] == "CPO"
    finally:
        sys.modules.pop("akshare", None)


def test_fund_flow_falls_back_to_ths():
    fake = ModuleType("akshare")

    def stock_sector_fund_flow_rank(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_individual_fund_flow_rank(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_fund_flow_industry(symbol=None):
        return pd.DataFrame({
            "行业": ["电子化学品", "银行", "煤炭"],
            "净额": [16.19, -3.5, -1.0],
        })

    def stock_fund_flow_concept(symbol=None):
        return pd.DataFrame({
            "行业": ["CPO", "光伏"],
            "净额": [132.76, -8.0],
        })

    def stock_fund_flow_individual(symbol=None):
        return pd.DataFrame({
            "股票代码": ["688485", "688286", "300684"],
            "股票简称": ["九州一轨", "敏芯股份", "中石科技"],
            "净额": ["4216.11万", "1.35亿", "-2.86亿"],
        })

    fake.stock_sector_fund_flow_rank = stock_sector_fund_flow_rank
    fake.stock_individual_fund_flow_rank = stock_individual_fund_flow_rank
    fake.stock_fund_flow_industry = stock_fund_flow_industry
    fake.stock_fund_flow_concept = stock_fund_flow_concept
    fake.stock_fund_flow_individual = stock_fund_flow_individual
    sys.modules["akshare"] = fake

    try:
        from collector.modules.fund_flow import collect_fund_flow

        result = collect_fund_flow("2026-08-14")

        assert result["status"] == "FINAL"
        assert result["method"] == "THS_MAIN_FORCE"
        assert result["industryInflowTop10"][0]["name"] == "电子化学品"
        assert result["industryInflowTop10"][0]["netInflowYi"] == 16.19
        assert result["industryOutflowTop10"][0]["name"] == "银行"
        assert result["conceptInflowTop10"][0]["netInflowYi"] == 132.76
        assert result["stockInflowTop10"][0]["name"] == "敏芯股份"
        assert result["stockInflowTop10"][0]["netInflowYi"] == 1.35
        assert result["stockOutflowTop10"][0]["name"] == "中石科技"
        assert result["stockOutflowTop10"][0]["netInflowYi"] == -2.86
    finally:
        sys.modules.pop("akshare", None)


def test_parse_yi_amount_units():
    from collector.modules.fund_flow import _parse_yi_amount

    # string_mode=True：个股带单位字符串
    assert _parse_yi_amount("1.35亿", string_mode=True) == 1.35
    assert abs(_parse_yi_amount("4216.11万", string_mode=True) - 0.421611) < 1e-9
    assert _parse_yi_amount("0.00", string_mode=True) == 0.0
    assert _parse_yi_amount("-2.86亿", string_mode=True) == -2.86
    # 无单位按元计：THS 小额净额 "9542.00" = 9542 元
    assert abs(_parse_yi_amount("9542.00", string_mode=True) - 0.00009542) < 1e-9
    # 异常大值拒绝
    assert _parse_yi_amount("9542.00亿", string_mode=True) is None
    assert _parse_yi_amount(None, string_mode=True) is None
    assert _parse_yi_amount("--", string_mode=True) is None
    # string_mode=False：行业/概念已是亿元数字
    assert _parse_yi_amount(16.19) == 16.19
    assert _parse_yi_amount("16.19") == 16.19
    assert _parse_yi_amount(None) is None
