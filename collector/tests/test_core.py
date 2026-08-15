from __future__ import annotations

import pandas as pd

from collector.calculators.rps import compute_return60
from collector.calculators.tracks import score_tracks
from collector.modules.fund_flow import _split_in_out
from collector.modules.northbound import _convert_hk_date

def test_rps60_uses_last_61_points():
    closes = (
        [1.0] * 9
        + [10.0]
        + [10.0] * 60
    )

    assert len(closes) == 70
    assert compute_return60(closes) == 0.0

def test_fund_flow_uses_yuan_and_outflow_order():
    df = pd.DataFrame(
        {
            "名称": ["A", "B", "C"],
            "今日主力净流入-净额": [
                100_000_000,
                -300_000_000,
                -100_000_000,
            ],
        }
    )

    inflow, outflow = _split_in_out(df)

    assert inflow[0]["netInflowYi"] == 1.0
    assert outflow[0]["netInflowYi"] == -3.0
    assert outflow[1]["netInflowYi"] == -1.0

def test_hkex_date_both_formats():
    assert (
        _convert_hk_date("2026/06/30")
        == "2026-06-30"
    )

    assert (
        _convert_hk_date("30/06/2026")
        == "2026-06-30"
    )

def test_unknown_track_is_not_scored_as_avoid():
    item = {
        "trackId": "x",
        "trackName": "X",
        "positioning": "",
        "turnoverRank": None,
        "mainNetInflow": None,
        "continuousInflowDays": None,
        "maAlignment": None,
        "rps60": None,
        "excessReturn20d": None,
        "limitUpRate": None,
        "ladderCompleteness": None,
        "redStockRatio": None,
        "coreCatalyst": {
            "state": "UNKNOWN",
        },
        "earningsRealization": {
            "state": "UNKNOWN",
        },
    }

    result = score_tracks([item])[0]

    assert result["score"] is None
    assert result["coveragePct"] == 0.0
    assert result["decision"] == "INSUFFICIENT"

def test_validator_rejects_final_module_date_mismatch():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    broken = copy.deepcopy(snapshot)
    broken["modules"]["turnover"]["dataDate"] = "2026-07-16"

    with pytest.raises(ValueError):
        validate_snapshot(broken)


def test_validator_rejects_overall_status_mismatch():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    broken = copy.deepcopy(snapshot)
    broken["overallStatus"] = "PARTIAL_ERROR"

    with pytest.raises(ValueError):
        validate_snapshot(broken)

def test_track_score_rejects_infinite_input():
    item = {
        "trackId": "x",
        "trackName": "X",
        "positioning": "",
        "turnoverRank": None,
        "mainNetInflow": float("inf"),
        "continuousInflowDays": None,
        "maAlignment": None,
        "rps60": None,
        "excessReturn20d": None,
        "limitUpRate": None,
        "ladderCompleteness": None,
        "redStockRatio": None,
        "coreCatalyst": {"state": "UNKNOWN"},
        "earningsRealization": {"state": "UNKNOWN"},
    }

    from collector.calculators.tracks import score_tracks

    result = score_tracks([item])[0]

    assert result["score"] is None
    assert result["decision"] == "INSUFFICIENT"


def test_previous_trading_day_skips_spring_festival():
    from datetime import date

    from collector.calendar import previous_trading_day

    assert (
        previous_trading_day(date(2026, 2, 19))
        == date(2026, 2, 13)
    )


def test_write_if_changed_is_semantically_idempotent(
    tmp_path,
    monkeypatch,
):
    import copy
    import json

    import collector.config as config
    from collector.jobs.common import write_if_changed

    # 使用仓库内已提交 JSON 作为结构 fixture，
    # 不依赖开发机外部 Excel。
    fixture_path = (
        config.PROJECT_ROOT
        / "web"
        / "public"
        / "data"
        / "daily"
        / "2026"
        / "2026-07-17.json"
    )

    baseline = json.loads(
        fixture_path.read_text(encoding="utf-8")
    )

    # 所有写入隔离到 pytest tmp_path，
    # 禁止修改仓库正式 baseline。
    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(
        config,
        "PROJECT_ROOT",
        test_root,
    )
    monkeypatch.setattr(
        config,
        "DATA_DIR",
        test_data,
    )
    monkeypatch.setattr(
        config,
        "DAILY_DIR",
        test_daily,
    )
    monkeypatch.setattr(
        config,
        "CALENDAR_DIR",
        test_calendar,
    )

    target_path = config.daily_path(
        baseline["tradeDate"]
    )
    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target_path.write_text(
        json.dumps(
            baseline,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original_revision = baseline["revision"]

    # 1) 仅伪造 revision，不改变业务语义：
    #    必须 NO_CHANGE，且不能采纳 revision=99。
    same = copy.deepcopy(baseline)
    same["revision"] = 99

    changed, reason = write_if_changed(same)

    assert not changed
    assert reason == "NO_CHANGE"

    on_disk = json.loads(
        target_path.read_text(encoding="utf-8")
    )
    assert on_disk["revision"] == original_revision

    # 2) 真正改变业务语义：
    #    必须 CHANGED，revision 严格从落盘旧值 +1。
    changed_snapshot = copy.deepcopy(baseline)
    changed_snapshot["revision"] = 99
    changed_snapshot["modules"]["summary"][
        "riskWarning"
    ] += " [pytest semantic change]"

    changed, reason = write_if_changed(
        changed_snapshot
    )

    assert changed
    assert reason == "CHANGED"

    on_disk = json.loads(
        target_path.read_text(encoding="utf-8")
    )

    assert (
        on_disk["revision"]
        == original_revision + 1
    )

    # 3) 同一语义再次写入：
    #    必须再次 NO_CHANGE，不继续增加 revision。
    repeated = copy.deepcopy(
        changed_snapshot
    )
    repeated["revision"] = 999

    changed, reason = write_if_changed(
        repeated
    )

    assert not changed
    assert reason == "NO_CHANGE"

    on_disk_again = json.loads(
        target_path.read_text(encoding="utf-8")
    )

    assert (
        on_disk_again["revision"]
        == original_revision + 1
    )

def test_northbound_historical_lookahead_fails_closed(
    monkeypatch,
):
    import collector.modules.northbound as northbound

    fake_items = [
        {
            "code": "600000",
            "hkexStockCode": "00001",
            "name": "测试股份",
            "shareholding": "1000000",
            "pctOfIssued": "1.00%",
        }
    ]

    def fake_fetch(url: str):
        del url

        return (
            fake_items,
            "2026-06-30",
        )

    def fake_load_yaml(name: str):
        assert name == "market-rules.yaml"

        return {
            "northbound": {
                "sh_url": "mock://sh",
                "sz_url": "mock://sz",
                # 测试日期，不宣称是现实市场发布日期；
                # 仅验证 point-in-time 逻辑。
                "quarterly_publication_dates": {
                    "2026-06-30": (
                        "2026-07-10"
                    )
                },
            }
        }

    monkeypatch.setattr(
        northbound,
        "_fetch_quarterly_holding",
        fake_fetch,
    )

    monkeypatch.setattr(
        northbound,
        "load_yaml",
        fake_load_yaml,
    )

    # 发布日前：必须明确 fail-closed，
    # 不接受 ERROR/PENDING 模糊通过。
    before = northbound.collect_northbound(
        "2026-07-01"
    )

    assert (
        before["status"]
        == "UNAVAILABLE"
    )

    holding = before[
        "quarterlyHolding"
    ]

    assert (
        holding["status"]
        == "UNAVAILABLE"
    )

    assert (
        holding["asOf"]
        == "2026-06-30"
    )

    assert (
        holding["publishedAt"]
        == "2026-07-10"
    )

    assert (
        holding["reason"]
        == "NOT_YET_PUBLISHED_AT_TARGET_DATE"
    )

    assert holding["items"] == []

    # 发布日后：同一 mock 季度数据可以进入 FINAL。
    after = northbound.collect_northbound(
        "2026-07-13"
    )

    assert after["status"] == "FINAL"

    holding_after = after[
        "quarterlyHolding"
    ]

    assert (
        holding_after["status"]
        == "FINAL"
    )

    assert (
        holding_after["asOf"]
        == "2026-06-30"
    )

    assert (
        holding_after["publishedAt"]
        == "2026-07-10"
    )

    assert len(
        holding_after["items"]
    ) == 2

def test_validator_rejects_null_final_margin_core():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    broken = copy.deepcopy(snapshot)
    broken["modules"]["margin"]["financingBalance"] = None

    with pytest.raises(ValueError):
        validate_snapshot(broken)

def test_validator_enforces_absolute_margin_balance_tolerance():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    # 构造高余额场景，确保容差仍固定为 0.05 亿元，
    # 不能因为余额变大而自动放宽为相对容差。
    broken = copy.deepcopy(snapshot)
    margin = broken["modules"]["margin"]

    margin["financingBalance"] = 99900.0
    margin["securitiesLendingBalance"] = 100.0
    margin["marginBalance"] = 100000.060001

    with pytest.raises(ValueError):
        validate_snapshot(broken)

def test_validator_accepts_exact_absolute_margin_balance_tolerance():
    import copy
    import json

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    # 业务口径：abs(diff) <= 0.05 应通过。
    # 十进制恰好 0.05 不能被二进制 float 误判为 > 0.05（R5-P3-01）。
    exact = copy.deepcopy(snapshot)
    margin = exact["modules"]["margin"]

    margin["financingBalance"] = 99900.0
    margin["securitiesLendingBalance"] = 100.0
    margin["marginBalance"] = 100000.05

    validate_snapshot(exact)

def test_sentiment_historical_partial_with_limit_pools(
    monkeypatch,
):
    import akshare

    import collector.modules.sentiment as sentiment

    calls: list[str] = []

    def fake_zt_pool(date: str):
        calls.append(("zt", date))
        return pd.DataFrame(
            {
                "名称": [
                    "甲股份",
                    "*ST 乙",
                    "丙股份",
                    "丁股份",
                ]
            }
        )

    def fake_dt_pool(date: str):
        calls.append(("dt", date))
        return pd.DataFrame(
            {
                "名称": ["戊股份"]
            }
        )

    def fake_zbgc(date: str):
        calls.append(("zb", date))
        return pd.DataFrame(
            {
                "名称": ["己股份", "庚股份"]
            }
        )

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_em",
        fake_zt_pool,
    )
    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_dtgc_em",
        fake_dt_pool,
    )
    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_zbgc_em",
        fake_zbgc,
    )

    # 用远期历史日期，避免与"今天"路径冲突。
    result = sentiment.collect_sentiment(
        "2020-01-02"
    )

    assert result["status"] == "PARTIAL"
    assert result["reason"] == (
        "HISTORICAL_LIMIT_POOL_ONLY"
    )
    assert result["riseCount"] is None
    assert result["fallCount"] is None
    assert result["nonStLimitUpCount"] == 3
    assert result["stLimitUpCount"] == 1
    assert result["nonStLimitDownCount"] == 1
    assert result["stLimitDownCount"] == 0
    assert result["brokenLimitCount"] == 2
    assert result["errors"] == []
    assert calls == [
        ("zt", "20200102"),
        ("dt", "20200102"),
        ("zb", "20200102"),
    ]

def test_sentiment_historical_no_pool_data_unavailable(
    monkeypatch,
):
    import akshare

    import collector.modules.sentiment as sentiment

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_em",
        lambda date: pd.DataFrame(),
    )

    result = sentiment.collect_sentiment(
        "2020-01-02"
    )

    assert (
        result["status"]
        == "UNAVAILABLE"
    )
    assert result["reason"] == (
        "HISTORICAL_LIMIT_POOL_UNAVAILABLE"
    )
    assert result["nonStLimitUpCount"] is None

def test_sentiment_historical_pool_error_fails_closed(
    monkeypatch,
):
    import akshare

    import collector.modules.sentiment as sentiment

    def boom(date: str):
        del date
        raise RuntimeError(
            "push2ex unreachable"
        )

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_em",
        boom,
    )

    result = sentiment.collect_sentiment(
        "2020-01-02"
    )

    assert result["status"] == "ERROR"
    assert result["errors"] == [
        "push2ex unreachable"
    ]

def test_sentiment_historical_partial_keeps_pools_on_zbgc_failure(
    monkeypatch,
):
    import akshare

    import collector.modules.sentiment as sentiment

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_em",
        lambda date: pd.DataFrame(
            {"名称": ["甲股份"]}
        ),
    )
    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_dtgc_em",
        lambda date: pd.DataFrame(
            {"名称": ["乙股份"]}
        ),
    )

    def boom(date: str):
        del date
        raise RuntimeError("zbgc down")

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_zbgc_em",
        boom,
    )

    result = sentiment.collect_sentiment(
        "2020-01-02"
    )

    assert result["status"] == "PARTIAL"
    assert result["nonStLimitUpCount"] == 1
    assert result["brokenLimitCount"] is None
    assert result["errors"] == ["zbgc: zbgc down"]

def test_backfill_merge_keeps_final_against_partial():
    from collector.jobs.manual_backfill import (
        _merge_preserving_valid_history,
    )

    old = {
        "modules": {
            "sentiment": {
                "status": "FINAL",
                "riseCount": 100,
                "dataDate": "2026-08-01",
            }
        }
    }
    new = {
        "modules": {
            "sentiment": {
                "status": "PARTIAL",
                "nonStLimitUpCount": 5,
                "dataDate": "2026-08-01",
            }
        }
    }

    merged = _merge_preserving_valid_history(old, new)

    assert (
        merged["modules"]["sentiment"]["status"]
        == "FINAL"
    )
    assert (
        merged["modules"]["sentiment"]["riseCount"]
        == 100
    )

def test_backfill_merge_keeps_partial_against_unavailable():
    from collector.jobs.manual_backfill import (
        _merge_preserving_valid_history,
    )

    old = {
        "modules": {
            "sentiment": {
                "status": "PARTIAL",
                "nonStLimitUpCount": 42,
                "dataDate": "2026-08-01",
            }
        }
    }
    new = {
        "modules": {
            "sentiment": {
                "status": "UNAVAILABLE",
                "dataDate": "2026-08-01",
            }
        }
    }

    merged = _merge_preserving_valid_history(old, new)

    assert (
        merged["modules"]["sentiment"]["status"]
        == "PARTIAL"
    )
    assert (
        merged["modules"]["sentiment"][
            "nonStLimitUpCount"
        ]
        == 42
    )

def test_backfill_merge_partial_field_union_never_loses_data():
    from collector.jobs.manual_backfill import (
        _merge_preserving_valid_history,
    )

    old = {
        "modules": {
            "sentiment": {
                "status": "PARTIAL",
                "nonStLimitUpCount": 42,
                "stLimitUpCount": 1,
                "brokenLimitCount": 7,
                "dataDate": "2026-08-01",
            }
        }
    }
    new = {
        "modules": {
            "sentiment": {
                "status": "PARTIAL",
                "nonStLimitUpCount": 43,
                "stLimitUpCount": None,
                "brokenLimitCount": None,
                "dataDate": "2026-08-01",
            }
        }
    }

    merged = _merge_preserving_valid_history(old, new)

    module = merged["modules"]["sentiment"]

    assert module["status"] == "PARTIAL"
    # 新值优先
    assert module["nonStLimitUpCount"] == 43
    # 旧的非空字段不得被抹成 None
    assert module["stLimitUpCount"] == 1
    assert module["brokenLimitCount"] == 7

def test_backfill_merge_partial_upgraded_by_final():
    from collector.jobs.manual_backfill import (
        _merge_preserving_valid_history,
    )

    old = {
        "modules": {
            "sentiment": {
                "status": "PARTIAL",
                "nonStLimitUpCount": 42,
                "dataDate": "2026-08-01",
            }
        }
    }
    new = {
        "modules": {
            "sentiment": {
                "status": "FINAL",
                "riseCount": 100,
                "dataDate": "2026-08-01",
            }
        }
    }

    merged = _merge_preserving_valid_history(old, new)

    assert (
        merged["modules"]["sentiment"]["status"]
        == "FINAL"
    )

def _load_legacy_baseline():
    import json

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)

def _partial_sentiment(**overrides):
    module = {
        "status": "PARTIAL",
        "dataDate": "2026-07-17",
        "source": ["EASTMONEY"],
        "reason": "HISTORICAL_LIMIT_POOL_ONLY",
        "riseCount": None,
        "fallCount": None,
        "flatCount": None,
        "suspendedCount": None,
        "nonStLimitUpCount": 5,
        "stLimitUpCount": 1,
        "nonStLimitDownCount": 2,
        "stLimitDownCount": 0,
        "brokenLimitCount": 3,
        "errors": [],
        "warnings": [],
    }
    module.update(overrides)
    return module

def test_validator_accepts_valid_historical_sentiment_partial():
    import copy

    from collector.validators.schema import validate_snapshot

    snapshot = _load_legacy_baseline()
    snapshot["modules"]["sentiment"] = (
        _partial_sentiment()
    )
    snapshot["overallStatus"] = "PARTIAL"

    validate_snapshot(snapshot)

def test_validator_rejects_partial_for_non_sentiment():
    import copy

    import pytest

    from collector.validators.schema import validate_snapshot

    snapshot = _load_legacy_baseline()
    snapshot["modules"]["fundFlow"] = {
        "status": "PARTIAL",
        "dataDate": "2026-07-17",
        "method": "EASTMONEY_MAIN_FORCE",
        "unit": "亿元",
    }
    snapshot["overallStatus"] = "PARTIAL"

    with pytest.raises(ValueError):
        validate_snapshot(snapshot)

def test_validator_rejects_partial_without_limit_up_counts():
    import copy

    import pytest

    from collector.validators.schema import validate_snapshot

    snapshot = _load_legacy_baseline()
    snapshot["modules"]["sentiment"] = (
        _partial_sentiment(
            nonStLimitUpCount=None,
            stLimitUpCount=None,
        )
    )
    snapshot["overallStatus"] = "PARTIAL"

    with pytest.raises(ValueError):
        validate_snapshot(snapshot)

def test_validator_rejects_partial_wrong_reason():
    import copy

    import pytest

    from collector.validators.schema import validate_snapshot

    snapshot = _load_legacy_baseline()
    snapshot["modules"]["sentiment"] = (
        _partial_sentiment(
            reason="HISTORICAL_LIMIT_POOL_UNAVAILABLE",
        )
    )
    snapshot["overallStatus"] = "PARTIAL"

    with pytest.raises(ValueError):
        validate_snapshot(snapshot)

def test_validator_rejects_partial_date_mismatch():
    import copy

    import pytest

    from collector.validators.schema import validate_snapshot

    snapshot = _load_legacy_baseline()
    snapshot["modules"]["sentiment"] = (
        _partial_sentiment(
            dataDate="2026-07-16",
        )
    )
    snapshot["overallStatus"] = "PARTIAL"

    with pytest.raises(ValueError):
        validate_snapshot(snapshot)

def test_sentiment_historical_aux_empty_stays_null(
    monkeypatch,
):
    import akshare

    import collector.modules.sentiment as sentiment

    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_em",
        lambda date: pd.DataFrame(
            {"名称": ["甲股份"]}
        ),
    )
    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_dtgc_em",
        lambda date: pd.DataFrame(),
    )
    monkeypatch.setattr(
        akshare,
        "stock_zt_pool_zbgc_em",
        lambda date: pd.DataFrame(),
    )

    result = sentiment.collect_sentiment(
        "2020-01-02"
    )

    assert result["status"] == "PARTIAL"
    assert result["nonStLimitUpCount"] == 1
    # 空辅助池不得伪装成真实 0（R8-P2-02）
    assert result["nonStLimitDownCount"] is None
    assert result["brokenLimitCount"] is None
    assert result["warnings"] == [
        "dt_pool: EMPTY_OR_UNAVAILABLE",
        "zbgc: EMPTY_OR_UNAVAILABLE",
    ]

def test_summary_partial_text_never_fabricates_zero():
    from collector.calculators.summary import (
        _partial_sentiment_text,
    )

    text = _partial_sentiment_text(
        {
            "status": "PARTIAL",
            "nonStLimitUpCount": 42,
            "stLimitUpCount": None,
            "nonStLimitDownCount": None,
            "stLimitDownCount": None,
            "brokenLimitCount": None,
        }
    )

    assert "非ST涨停 42 家" in text
    assert "跌停" not in text
    assert "炸板" not in text

def test_turnover_historical_via_exchange(
    monkeypatch,
):
    """R9：交易所官方文件源支持历史日期（官方口径，历史回补可补成交额）。"""
    import sys
    from types import ModuleType

    fake = ModuleType("akshare")

    def stock_sh_a_spot_em(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_sz_a_spot_em(*args, **kwargs):
        raise ConnectionError("push2 blocked")

    def stock_zh_a_spot(*args, **kwargs):
        raise ConnectionError("sina blocked")

    def stock_sse_deal_daily(date=None):
        return pd.DataFrame(
            {
                "单日情况": ["挂牌数", "成交金额"],
                "股票": [2353.0, 9917.63],
                "主板A": [1699.0, 6737.09],
                "主板B": [41.0, 0.81],
                "科创板": [613.0, 3179.72],
                "股票回购": [0.0, 0.30],
            }
        )

    def stock_szse_summary(date=None):
        return pd.DataFrame(
            {
                "证券类别": ["股票", "主板A股", "创业板A股"],
                "数量": [2934, 1494, 1402],
                "成交金额": [
                    1.153380e12,
                    5.964477e11,
                    5.568948e11,
                ],
                "总市值": [1.0e13, 1.0e13, 1.0e13],
                "流通市值": [1.0e13, 1.0e13, 1.0e13],
            }
        )

    fake.stock_sh_a_spot_em = stock_sh_a_spot_em
    fake.stock_sz_a_spot_em = stock_sz_a_spot_em
    fake.stock_zh_a_spot = stock_zh_a_spot
    fake.stock_sse_deal_daily = stock_sse_deal_daily
    fake.stock_szse_summary = stock_szse_summary
    sys.modules["akshare"] = fake

    try:
        from collector.modules.turnover import (
            collect_turnover,
        )

        result = collect_turnover(
            "2026-07-20",
            market_rules={},
        )

        assert result["status"] == "FINAL"
        assert result["dataDate"] == "2026-07-20"
        assert result["source"] == ["EXCHANGE"]
        # 沪：(6737.09+3179.72) + 深：(5.964477e11+5.568948e11)/1e8
        import pytest

        assert result["turnoverToday"] == pytest.approx(
            9916.81 + 11533.425,
            abs=0.01,
        )
    finally:
        sys.modules.pop("akshare", None)

def test_eastmoney_delay_adapter_parsing(
    monkeypatch,
):
    """R9：适配器 secid 映射 + 指数解析 + 非当日拒绝。"""
    import pytest

    import collector.adapters.eastmoney_delay as emd

    assert emd.secid_from_symbol("sh000001") == "1.000001"
    assert emd.secid_from_symbol("sz399001") == "0.399001"
    assert emd.secid_from_symbol("bj899050") == "0.899050"
    assert emd.secid_from_symbol("sz399311") == "0.399311"

    index_payload = {
        "rc": 0,
        "data": {
            "diff": [
                {"f12": "1.000001", "f14": "上证指数", "f2": 3927.18, "f3": 0.01, "f18": 3926.79, "f4": 0.39},
                {"f12": "0.399001", "f14": "深证成指", "f2": 14354.31, "f3": 0.45, "f18": 14290.0, "f4": 64.31},
                {"f12": "0.399006", "f14": "创业板指", "f2": 3626.3, "f3": 1.12, "f18": 3586.1, "f4": 40.2},
                {"f12": "1.000688", "f14": "科创50", "f2": 1717.68, "f3": 0.0, "f18": 1717.68, "f4": 0.0},
                {"f12": "1.000300", "f14": "沪深300", "f2": 4665.88, "f3": 0.04, "f18": 4664.01, "f4": 1.87},
                {"f12": "0.899050", "f14": "北证50", "f2": 1087.52, "f3": -0.94, "f18": 1097.84, "f4": -10.32},
                {"f12": "0.399311", "f14": "国证1000", "f2": 5065.96, "f3": 0.18, "f18": 5056.86, "f4": 9.1},
                {"f12": "0.399303", "f14": "国证2000", "f2": 10115.47, "f3": 0.79, "f18": 10036.19, "f4": 79.28},
            ]
        },
    }

    from collector.schema import TZ_SHANGHAI

    today = (
        __import__("datetime")
        .datetime.now(TZ_SHANGHAI)
        .date()
        .isoformat()
    )

    monkeypatch.setattr(
        emd,
        "_get_json",
        lambda url: index_payload,
    )

    quotes = emd.fetch_index_quotes(today)

    assert len(quotes) == 8
    close, previous = quotes["1.000001"]
    assert close == 3927.18
    # R9-P2-05：昨收直接取 f18 字段，不再由涨跌幅反推
    assert previous == 3926.79

    # 非当日必须失败（历史走 tencent/cni/exchange）
    with pytest.raises(ValueError):
        emd.fetch_index_quotes("2026-07-20")


def test_exchange_turnover_fails_closed_on_missing_szse_category(
    monkeypatch,
):
    """R9-P1-01：SZSE 缺少任一必需分类必须失败，不得返回部分总额。"""
    import sys
    from types import ModuleType

    import pytest

    from collector.modules.turnover import (
        _turnover_yuan_from_exchange,
    )

    fake = ModuleType("akshare")

    def stock_sse_deal_daily(date=None):
        return pd.DataFrame(
            {
                "单日情况": ["成交金额"],
                "股票": [9917.63],
                "主板A": [6737.09],
                "主板B": [0.81],
                "科创板": [3179.72],
                "股票回购": [0.30],
            }
        )

    def stock_szse_summary(date=None):
        # 缺创业板A股
        return pd.DataFrame(
            {
                "证券类别": ["主板A股"],
                "数量": [1494],
                "成交金额": [5.964477e11],
                "总市值": [1.0e13],
                "流通市值": [1.0e13],
            }
        )

    fake.stock_sse_deal_daily = stock_sse_deal_daily
    fake.stock_szse_summary = stock_szse_summary
    sys.modules["akshare"] = fake

    try:
        with pytest.raises(ValueError):
            _turnover_yuan_from_exchange("2026-07-20")
    finally:
        sys.modules.pop("akshare", None)

def test_exchange_turnover_fails_closed_on_missing_sse_column(
    monkeypatch,
):
    """R9-P1-01：SSE 缺必需列必须失败。"""
    import sys
    from types import ModuleType

    import pytest

    from collector.modules.turnover import (
        _turnover_yuan_from_exchange,
    )

    fake = ModuleType("akshare")

    def stock_sse_deal_daily(date=None):
        return pd.DataFrame(
            {
                "单日情况": ["成交金额"],
                "股票": [9917.63],
                "主板A": [6737.09],
                # 缺科创板列
            }
        )

    fake.stock_sse_deal_daily = stock_sse_deal_daily
    sys.modules["akshare"] = fake

    try:
        with pytest.raises(ValueError):
            _turnover_yuan_from_exchange("2026-07-20")
    finally:
        sys.modules.pop("akshare", None)

def test_delay_cache_fetch_failure_does_not_poison_cache(
    monkeypatch,
):
    """R9-P2-02：新日期抓取失败不得把旧日期 quotes 复用为新日期。"""
    import collector.modules.market_index as mi

    mi._DELAY_CACHE["date"] = "2026-08-14"
    mi._DELAY_CACHE["quotes"] = {"stale": (1.0, 1.0)}

    calls = []

    def good_fetcher(trade_date: str):
        calls.append(("good", trade_date))
        return {"fresh": (2.0, 2.0)}

    def bad_fetcher(trade_date: str):
        calls.append(("bad", trade_date))
        raise RuntimeError("network down")

    try:
        with __import__("pytest").raises(RuntimeError):
            mi._delay_index_quotes("2026-08-15", bad_fetcher)

        # 失败后 cache 不得被标记为新日期+旧数据
        assert mi._DELAY_CACHE["quotes"] == {"stale": (1.0, 1.0)}

        # 下一次同日调用必须重新抓取，而不是复用旧 quotes
        quotes = mi._delay_index_quotes(
            "2026-08-15",
            good_fetcher,
        )
        assert quotes == {"fresh": (2.0, 2.0)}
        assert calls == [
            ("bad", "2026-08-15"),
            ("good", "2026-08-15"),
        ]
    finally:
        mi._DELAY_CACHE["date"] = None
        mi._DELAY_CACHE["quotes"] = None

def test_turnover_method_inference():
    """R9-P2-01：口径血缘推断（Legacy 未知 / spot 统一口径）。"""
    from collector.modules.turnover import (
        _infer_turnover_method,
    )

    legacy = {
        "source": ["TONGDAXIN_LEGACY"],
        "turnoverToday": 26549.58,
    }
    assert _infer_turnover_method(legacy) == (
        "LEGACY_UNKNOWN"
    )

    sina = {
        "source": ["SINA"],
        "turnoverToday": 21422.77,
    }
    assert _infer_turnover_method(sina) == (
        "SH_SZ_A_NO_B_NO_BJ_V1"
    )

def test_manual_backfill_rejects_non_past_date():
    """R9-P2-04：manual_backfill 仅允许历史日（R9.2：动态明日，跨午夜稳定）。"""
    import subprocess
    import sys
    from datetime import date, timedelta

    from collector.schema import TZ_SHANGHAI

    target = (
        date.fromisoformat(
            __import__("datetime")
            .datetime.now(TZ_SHANGHAI)
            .date()
            .isoformat()
        )
        + timedelta(days=1)
    ).isoformat()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "collector.jobs.manual_backfill",
            "--date",
            target,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=".",
    )

    assert result.returncode == 2
    assert (
        "BACKFILL_REQUIRES_PAST_DATE"
        in (result.stdout or "")
    )


def test_turnover_comparison_state_machine():
    """R9.2：统一比较函数状态机（COMPARABLE/UNAVAILABLE/MISMATCH/前值无效）。"""
    from collector.modules.turnover import (
        TURNOVER_METHOD,
        _turnover_comparison,
    )

    rules = {"volume_state": {"expansion_threshold_pct": 5, "contraction_threshold_pct": -5}}

    # 1) 无前值 -> UNAVAILABLE + previousMethod null
    r1 = _turnover_comparison(100.0, None, rules)
    assert r1["comparisonStatus"] == "PREVIOUS_UNAVAILABLE"
    assert r1["previousMethod"] is None
    assert r1["turnoverPrevious"] is None
    assert r1["volumeState"] == "UNKNOWN"

    # 2) 前值口径不可证明 -> UNAVAILABLE（不得误标 MISMATCH）
    r2 = _turnover_comparison(100.0, {"value": 90.0, "method": None}, rules)
    assert r2["comparisonStatus"] == "PREVIOUS_UNAVAILABLE"
    assert r2["previousMethod"] is None

    # 3) 前值口径不同 -> MISMATCH + previousMethod 保留
    r3 = _turnover_comparison(100.0, {"value": 90.0, "method": "LEGACY_UNKNOWN"}, rules)
    assert r3["comparisonStatus"] == "PREVIOUS_METHOD_MISMATCH"
    assert r3["previousMethod"] == "LEGACY_UNKNOWN"
    assert r3["turnoverDelta"] is None

    # 4) 前值无效（0/负/NaN）-> UNAVAILABLE + previousMethod null
    for bad in (0.0, -5.0, float("nan")):
        r4 = _turnover_comparison(100.0, {"value": bad, "method": TURNOVER_METHOD}, rules)
        assert r4["comparisonStatus"] == "PREVIOUS_UNAVAILABLE"
        assert r4["previousMethod"] is None

    # 5) 正常可比 -> COMPARABLE + 数值
    r5 = _turnover_comparison(110.0, {"value": 100.0, "method": TURNOVER_METHOD}, rules)
    assert r5["comparisonStatus"] == "COMPARABLE"
    assert r5["turnoverPrevious"] == 100.0
    assert r5["turnoverDelta"] == 10.0
    assert r5["turnoverChangePct"] == 10.0
    assert r5["volumeState"] == "EXPANSION"

def test_reconcile_day_idempotent_when_unchanged():
    """R9.2-N2：派生字段无变化时 reconcile 不得 bump revision。"""
    from collector.jobs.reconcile_turnover_chain import (
        _reconcile_day,
    )

    snapshot = {
        "tradeDate": "2026-08-13",
        "modules": {
            "turnover": {
                "status": "FINAL",
                "dataDate": "2026-08-13",
                "method": "SH_SZ_A_NO_B_NO_BJ_V1",
                "turnoverToday": 25538.20,
                "turnoverPrevious": 27037.72,
                "turnoverDelta": -1499.52,
                "turnoverChangePct": -5.55,
                "volumeState": "CONTRACTION",
                "previousMethod": "SH_SZ_A_NO_B_NO_BJ_V1",
                "comparisonStatus": "COMPARABLE",
                "source": ["EXCHANGE"],
                "unit": "亿元",
            },
        },
    }

    from collector.calculators.summary import generate_summary

    # summary 用真实生成结果填充，保证幂等比较命中
    snapshot["modules"]["summary"] = generate_summary(snapshot)

    prev = {
        "tradeDate": "2026-08-12",
        "modules": {
            "turnover": {
                "status": "FINAL",
                "dataDate": "2026-08-12",
                "turnoverToday": 27037.72,
                "method": "SH_SZ_A_NO_B_NO_BJ_V1",
                "source": ["EXCHANGE"],
            }
        }
    }

    rules = {"volume_state": {"expansion_threshold_pct": 5, "contraction_threshold_pct": -5}}

    # 首次：派生字段已与比较结果一致（含 summary 一致）→ 不得变更
    changed = _reconcile_day(snapshot, prev, rules)
    assert changed is False

    # 修改一个字段后：必须检测到变化并纠正
    snapshot["modules"]["turnover"]["turnoverDelta"] = 999.0
    changed2 = _reconcile_day(snapshot, prev, rules)
    assert changed2 is True
    assert snapshot["modules"]["turnover"]["turnoverDelta"] == -1499.52

def test_reconcile_previous_missing_is_unavailable():
    """R9.2-N1：真实上一交易日缺失 -> PREVIOUS_UNAVAILABLE，绝不跨日误比。"""
    from collector.jobs.reconcile_turnover_chain import (
        _reconcile_day,
    )

    snapshot = {
        "tradeDate": "2026-08-13",
        "modules": {
            "turnover": {
                "status": "FINAL",
                "dataDate": "2026-08-13",
                "turnoverToday": 25538.20,
                "method": "SH_SZ_A_NO_B_NO_BJ_V1",
                "source": ["EXCHANGE"],
                "unit": "亿元",
                # 旧值（此前与某个早前日期比较过）必须被纠正
                "turnoverPrevious": 100.0,
                "turnoverDelta": 1.0,
                "turnoverChangePct": 1.0,
                "volumeState": "FLAT",
                "previousMethod": "SH_SZ_A_NO_B_NO_BJ_V1",
                "comparisonStatus": "COMPARABLE",
            },
        },
    }

    from collector.calculators.summary import generate_summary

    snapshot["modules"]["summary"] = generate_summary(snapshot)

    rules = {"volume_state": {"expansion_threshold_pct": 5, "contraction_threshold_pct": -5}}

    changed = _reconcile_day(snapshot, None, rules)

    assert changed is True
    module = snapshot["modules"]["turnover"]
    assert module["comparisonStatus"] == "PREVIOUS_UNAVAILABLE"
    assert module["previousMethod"] is None
    assert module["turnoverPrevious"] is None
    assert module["volumeState"] == "UNKNOWN"

def test_exchange_rejects_before_lower_bound(
    monkeypatch,
):
    """R9.2-N5：2021-12-27 之前必须直接失败（不发起网络请求）。"""
    import sys
    from types import ModuleType

    import pytest

    from collector.modules.turnover import (
        _turnover_yuan_from_exchange,
    )

    called = []

    fake = ModuleType("akshare")

    def stock_sse_deal_daily(date=None):
        called.append(date)
        raise AssertionError("must not call network")

    fake.stock_sse_deal_daily = stock_sse_deal_daily
    sys.modules["akshare"] = fake

    try:
        with pytest.raises(ValueError):
            _turnover_yuan_from_exchange("2021-12-26")
        assert called == []
    finally:
        sys.modules.pop("akshare", None)

def test_validator_turnover_lineage_negative_cases():
    """R9.2-N4：validator 深度契约负向 + legacy 豁免。"""
    import copy

    import pytest

    from collector.validators.schema import validate_snapshot

    base = _load_legacy_baseline()
    base["meta"]["legacy"] = False
    base["modules"]["turnover"]["method"] = "SH_SZ_A_NO_B_NO_BJ_V1"

    # COMPARABLE 但 previous 为 null -> REJECT
    broken = copy.deepcopy(base)
    broken["modules"]["turnover"].update({
        "comparisonStatus": "COMPARABLE",
        "previousMethod": "SH_SZ_A_NO_B_NO_BJ_V1",
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    })
    with pytest.raises(ValueError):
        validate_snapshot(broken)

    # UNAVAILABLE 但 previousMethod 非 null -> REJECT
    broken2 = copy.deepcopy(base)
    broken2["modules"]["turnover"].update({
        "comparisonStatus": "PREVIOUS_UNAVAILABLE",
        "previousMethod": "SH_SZ_A_NO_B_NO_BJ_V1",
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    })
    with pytest.raises(ValueError):
        validate_snapshot(broken2)

    # MISMATCH 但 delta 非 null -> REJECT
    broken3 = copy.deepcopy(base)
    broken3["modules"]["turnover"].update({
        "comparisonStatus": "PREVIOUS_METHOD_MISMATCH",
        "previousMethod": "LEGACY_UNKNOWN",
        "turnoverPrevious": None,
        "turnoverDelta": 1.0,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    })
    with pytest.raises(ValueError):
        validate_snapshot(broken3)

    # 合法 COMPARABLE -> PASS
    ok = copy.deepcopy(base)
    ok["modules"]["turnover"].update({
        "comparisonStatus": "COMPARABLE",
        "previousMethod": "SH_SZ_A_NO_B_NO_BJ_V1",
        "turnoverPrevious": 100.0,
        "turnoverDelta": 5.0,
        "turnoverChangePct": 5.26,
        "volumeState": "EXPANSION",
    })
    validate_snapshot(ok)

    # Legacy 豁免：meta.legacy=true 且无 lineage 字段 -> PASS
    legacy_ok = _load_legacy_baseline()
    legacy_ok["modules"]["turnover"].pop("method", None)
    legacy_ok["modules"]["turnover"].pop("comparisonStatus", None)
    validate_snapshot(legacy_ok)


def test_reconcile_read_rejects_filename_trade_date_mismatch(
    tmp_path,
):
    """R9.2-P2-01：文件名日期 != tradeDate 的快照必须视为损坏。"""
    import json

    from collector.jobs.reconcile_turnover_chain import (
        _read_snapshot,
    )

    path = tmp_path / "2026-08-12.json"

    path.write_text(
        json.dumps(
            {
                "tradeDate": "2026-08-11",
                "modules": {
                    "turnover": {
                        "status": "FINAL",
                        "dataDate": "2026-08-11",
                        "turnoverToday": 100.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert _read_snapshot(path) is None

def test_reconcile_rejects_semantically_mislabeled_previous():
    """R9.2-P2-01：可解析但内部日期身份损坏的 previous 必须拒绝。"""
    from collector.jobs.reconcile_turnover_chain import (
        _previous_info_from_snapshot,
    )

    previous = {
        "tradeDate": "2026-08-11",
        "modules": {
            "turnover": {
                "status": "FINAL",
                "dataDate": "2026-08-11",
                "turnoverToday": 21546.58,
                "method": "SH_SZ_A_NO_B_NO_BJ_V1",
                "source": ["EXCHANGE"],
            }
        },
    }

    # 内部身份一致 -> 可提取
    assert (
        _previous_info_from_snapshot(previous)
        is not None
    )

    # 内部身份损坏（dataDate != tradeDate）-> 必须拒绝
    broken = {
        **previous,
        "modules": {
            "turnover": {
                **previous["modules"]["turnover"],
                "dataDate": "2026-08-12",
            }
        },
    }

    assert (
        _previous_info_from_snapshot(broken)
        is None
    )

def test_market_index_explicit_chain_keeps_prior_errors(
    monkeypatch,
):
    """R9-P3-02：国证显式链（cni->tencent->sina）成功时保留前序失败。"""
    import collector.modules.market_index as mi

    calls = []

    def fake_fetch(index, trade_date, start, end, source):
        calls.append(source)
        if source == "cni":
            raise RuntimeError("cni blocked")
        return 2.0, 1.0

    monkeypatch.setattr(
        mi,
        "_fetch_index_close",
        fake_fetch,
    )

    close, previous, used, errors = mi._with_source_list(
        {"symbol_em": "sz399311"},
        "2026-07-20",
        "20260701",
        "20260720",
        ["cni", "tencent", "sina"],
    )

    assert close == 2.0
    assert previous == 1.0
    assert used == "tencent"
    assert errors == ["cni: cni blocked"]
    assert calls == ["cni", "tencent"]






# ---------------------------------------------------------------------------
# ④ D0/D+1 两阶段完整性模型（R7-P1 / R6-P1-04）
# ---------------------------------------------------------------------------

def _phase_snapshot(module_statuses):
    """构造一个只带 status 的快照骨架，供 snapshot_phase 测试。"""
    from collector.schema import new_snapshot
    snap = new_snapshot("2026-08-14")
    for name, status in module_statuses.items():
        snap["modules"][name]["status"] = status
    return snap


def test_phase_all_final_is_final():
    from collector.completeness import PHASE_FINAL, snapshot_phase
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "margin", "tracks", "summary",
    )}
    assert snapshot_phase(_phase_snapshot(statuses)) == PHASE_FINAL


def test_phase_margin_pending_with_tracks_final_is_close_complete():
    from collector.completeness import (
        PHASE_CLOSE_COMPLETE,
        snapshot_phase,
    )
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "tracks", "summary",
    )}
    statuses["margin"] = "PENDING"
    assert snapshot_phase(_phase_snapshot(statuses)) == PHASE_CLOSE_COMPLETE


def test_phase_tracks_unavailable_is_captured_not_close_complete():
    """当前 tracks 占位 UNAVAILABLE -> 无 CLOSE_COMPLETE 日（R7 原文语义）。"""
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "UNAVAILABLE"
    assert snapshot_phase(_phase_snapshot(statuses)) == PHASE_CAPTURED


def test_phase_tracks_sufficient_with_coverage_is_close_complete():
    from collector.completeness import (
        PHASE_CLOSE_COMPLETE,
        snapshot_phase,
    )
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "FINAL"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 85.0
    assert snapshot_phase(snap) == PHASE_CLOSE_COMPLETE


def test_phase_margin_error_is_captured():
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "tracks", "summary",
    )}
    statuses["margin"] = "ERROR"
    assert snapshot_phase(_phase_snapshot(statuses)) == PHASE_CAPTURED


def test_phase_any_module_missing_is_captured():
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )
    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "tracks", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["sentiment"] = "PARTIAL"
    assert snapshot_phase(_phase_snapshot(statuses)) == PHASE_CAPTURED


def test_margin_d0_reference_attached_when_pending(
    tmp_path,
    monkeypatch,
):
    """D0 时 margin=PENDING 必须附加最近已披露 T-1 参考值。"""
    import json

    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    # 前一日（08-13）已披露 FINAL 两融
    prev_dir = test_daily / "2026"
    prev_dir.mkdir(parents=True, exist_ok=True)

    prev_snapshot = {
        "tradeDate": "2026-08-13",
        "modules": {
            "margin": {
                "status": "FINAL",
                "dataDate": "2026-08-13",
                "financingBalance": 100.0,
                "securitiesLendingBalance": 5.0,
                "marginBalance": 105.0,
            }
        },
    }

    (prev_dir / "2026-08-13.json").write_text(
        json.dumps(prev_snapshot),
        encoding="utf-8",
    )

    ref = _latest_published_reference("2026-08-14")

    assert ref is not None
    assert ref["dataDate"] == "2026-08-13"
    assert ref["marginBalance"] == 105.0


def test_margin_d0_reference_none_without_prior_final(
    tmp_path,
    monkeypatch,
):
    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_daily = test_root / "data" / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    assert (
        _latest_published_reference("2026-08-14")
        is None
    )


def test_margin_reference_skips_pending_previous_day(
    tmp_path,
    monkeypatch,
):
    """前一日 margin 仍 PENDING 时必须继续回退找更早 FINAL 日。"""
    import json

    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_daily = test_root / "data" / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    prev_dir = test_daily / "2026"
    prev_dir.mkdir(parents=True, exist_ok=True)

    (prev_dir / "2026-08-13.json").write_text(
        json.dumps({
            "tradeDate": "2026-08-13",
            "modules": {"margin": {"status": "PENDING"}},
        }),
        encoding="utf-8",
    )

    (prev_dir / "2026-08-12.json").write_text(
        json.dumps({
            "tradeDate": "2026-08-12",
            "modules": {
                "margin": {
                    "status": "FINAL",
                    "dataDate": "2026-08-12",
                    "financingBalance": 90.0,
                    "securitiesLendingBalance": 4.0,
                    "marginBalance": 94.0,
                }
            },
        }),
        encoding="utf-8",
    )

    ref = _latest_published_reference("2026-08-14")

    assert ref is not None
    assert ref["dataDate"] == "2026-08-12"
    assert ref["marginBalance"] == 94.0


def test_validator_accepts_margin_reference_on_pending():
    import copy
    import json

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    mutated = copy.deepcopy(snapshot)
    margin = mutated["modules"]["margin"]
    margin["status"] = "PENDING"
    margin["dataDate"] = None
    margin["latestPublishedReference"] = {
        "dataDate": "2026-07-16",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": 105.0,
    }
    mutated["overallStatus"] = "PARTIAL_PENDING"

    validate_snapshot(mutated)


def test_validator_rejects_final_margin_with_reference():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    mutated = copy.deepcopy(snapshot)
    mutated["modules"]["margin"]["latestPublishedReference"] = {
        "dataDate": "2026-07-16",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": 105.0,
    }

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_validator_rejects_reference_date_not_before_trade_date():
    import copy
    import json

    import pytest

    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    mutated = copy.deepcopy(snapshot)
    margin = mutated["modules"]["margin"]
    margin["status"] = "PENDING"
    margin["dataDate"] = None
    margin["latestPublishedReference"] = {
        "dataDate": "2026-07-17",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": 105.0,
    }
    mutated["overallStatus"] = "PARTIAL_PENDING"

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_summary_margin_pending_with_reference_text():
    from collector.calculators.summary import _rule_margin

    text = _rule_margin({
        "status": "PENDING",
        "latestPublishedReference": {
            "dataDate": "2026-08-13",
            "marginBalance": 105.0,
        },
    })

    assert "2026-08-13" in text
    assert "105.00" in text


def test_manifest_three_pointers_computed(
    tmp_path,
    monkeypatch,
):
    """manifest 三指针：captured=最新、closeComplete=最新 CLOSE_COMPLETE、final=最新 FINAL。"""
    import json

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        update_manifest_and_latest,
    )

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    # common 模块在 import 时绑定了 DAILY_DIR，需同步打补丁
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    def build_day(d, margin_status, tracks_status):
        from collector.schema import new_snapshot
        snap = new_snapshot(d)
        for name in (
            "marketIndex", "turnover", "sentiment",
            "sectorPerformance", "fundFlow", "northbound",
            "summary",
        ):
            snap["modules"][name]["status"] = "FINAL"
            snap["modules"][name]["dataDate"] = d
        snap["modules"]["margin"]["status"] = margin_status
        if margin_status == "FINAL":
            snap["modules"]["margin"]["dataDate"] = d
        snap["modules"]["tracks"]["status"] = tracks_status
        if tracks_status == "FINAL":
            snap["modules"]["tracks"]["dataDate"] = d
        if margin_status == "PENDING" and tracks_status == "FINAL":
            snap["overallStatus"] = "PARTIAL_PENDING"
        elif margin_status == "FINAL" and tracks_status == "FINAL":
            snap["overallStatus"] = "FINAL"
        else:
            snap["overallStatus"] = "PARTIAL"
        return snap

    # 08-12：全 FINAL（D+1）
    snap_a = build_day("2026-08-12", "FINAL", "FINAL")
    _write_json_atomic(day_dir / "2026-08-12.json", snap_a)

    # 08-13：margin PENDING + tracks FINAL（D0 CLOSE_COMPLETE）
    snap_b = build_day("2026-08-13", "PENDING", "FINAL")
    _write_json_atomic(day_dir / "2026-08-13.json", snap_b)

    # 08-14：tracks UNAVAILABLE（CAPTURED，最新采集日）
    snap_c = build_day("2026-08-14", "PENDING", "UNAVAILABLE")
    _write_json_atomic(day_dir / "2026-08-14.json", snap_c)

    manifest = update_manifest_and_latest(
        "2026-08-14",
        snap_c,
    )

    assert manifest["latestCapturedDate"] == "2026-08-14"
    assert manifest["latestCloseCompleteDate"] == "2026-08-13"
    assert manifest["latestFinalDate"] == "2026-08-12"
    assert manifest["latestDate"] == "2026-08-14"

    status = json.loads(
        (test_data / "status.json").read_text(encoding="utf-8")
    )

    assert status["latestCapturedDate"] == "2026-08-14"
    assert status["latestCloseCompleteDate"] == "2026-08-13"
    assert status["latestFinalDate"] == "2026-08-12"


# ---------------------------------------------------------------------------
# ④ 复核补充：snapshot_phase / validator / manifest 边界用例（GLM-5.3 复核）
# ---------------------------------------------------------------------------

def test_phase_final_requires_all_nine_modules_by_name():
    """缺 tracks 模块键的快照不得判 FINAL（按名锚定，防 8/9 FINAL 误抬指针）。"""
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )

    snap = _phase_snapshot(
        {name: "FINAL" for name in (
            "marketIndex", "turnover", "sentiment",
            "sectorPerformance", "fundFlow", "northbound",
            "margin", "summary",
        )}
    )
    # 不设置 tracks（模块键缺失）
    del snap["modules"]["tracks"]

    assert snapshot_phase(snap) == PHASE_CAPTURED


def test_phase_tracks_sufficient_boundary_at_80():
    from collector.completeness import (
        PHASE_CLOSE_COMPLETE,
        snapshot_phase,
    )

    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "PARTIAL"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 80.0
    assert snapshot_phase(snap) == PHASE_CLOSE_COMPLETE


def test_phase_tracks_sufficient_below_80_is_captured():
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )

    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "PARTIAL"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 79.9
    assert snapshot_phase(snap) == PHASE_CAPTURED


def test_phase_tracks_error_with_sufficient_decision_is_captured():
    """矛盾数据（ERROR + TRACKS_SUFFICIENT + 达标覆盖率）不得点亮 CLOSE_COMPLETE。"""
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )

    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "ERROR"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 95.0
    assert snapshot_phase(snap) == PHASE_CAPTURED


def test_phase_legacy_2026_07_17_snapshot_file_is_final():
    """锚定设计边界：07-17 Legacy 为 9 模块全 FINAL（隐含 CLOSE_COMPLETE）。

    同时守护 FIX-1：若该文件缺任一必需模块键，本用例失败，
    说明落地 latestFinalDate=07-17 需重新裁决。
    """
    import json

    from collector.completeness import (
        PHASE_FINAL,
        snapshot_phase,
    )

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    assert snapshot_phase(snapshot) == PHASE_FINAL


def _margin_pending_mutation(reference):
    import copy
    import json

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snapshot = json.load(f)

    mutated = copy.deepcopy(snapshot)
    margin = mutated["modules"]["margin"]
    margin["status"] = "PENDING"
    margin["dataDate"] = None
    margin["latestPublishedReference"] = reference
    mutated["overallStatus"] = "PARTIAL_PENDING"
    return mutated


def test_validator_rejects_negative_reference_balance():
    import pytest

    from collector.validators.schema import validate_snapshot

    mutated = _margin_pending_mutation({
        "dataDate": "2026-07-16",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": -1.0,
    })

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_validator_rejects_noncanonical_reference_date():
    import pytest

    from collector.validators.schema import validate_snapshot

    mutated = _margin_pending_mutation({
        "dataDate": "20260716",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": 105.0,
    })

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_validator_rejects_reference_missing_balance_field():
    import pytest

    from collector.validators.schema import validate_snapshot

    mutated = _margin_pending_mutation({
        "dataDate": "2026-07-16",
    })

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_manifest_final_implies_close_complete(
    tmp_path,
    monkeypatch,
):
    """唯一一天为 D+1 FINAL 时，CLOSE_COMPLETE 指针应与 FINAL 指针同日
    （FINAL 隐含 CLOSE_COMPLETE 的直接断言）。"""
    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        update_manifest_and_latest,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    snap = new_snapshot("2026-08-12")
    for module in snap["modules"].values():
        module["status"] = "FINAL"
        module["dataDate"] = "2026-08-12"
    snap["overallStatus"] = "FINAL"
    _write_json_atomic(day_dir / "2026-08-12.json", snap)

    manifest = update_manifest_and_latest(
        "2026-08-12",
        snap,
    )

    assert manifest["latestCapturedDate"] == "2026-08-12"
    assert manifest["latestCloseCompleteDate"] == "2026-08-12"
    assert manifest["latestFinalDate"] == "2026-08-12"


# ---------------------------------------------------------------------------
# R10.1 评审修复回归（ChatGPT 6 项：P1-01 事务恢复 / P1-02 tracks 状态域 /
# P2-01 身份校验 / P3-01 文档 / P3-02 TS 形状）
# ---------------------------------------------------------------------------

def test_phase_tracks_stale_sufficient_is_captured():
    """STALE + TRACKS_SUFFICIENT + 80 不得点亮 CLOSE_COMPLETE（R10-P1-02）。"""
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )

    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "STALE"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 80.0
    assert snapshot_phase(snap) == PHASE_CAPTURED


def test_phase_tracks_pending_sufficient_is_captured():
    """PENDING + TRACKS_SUFFICIENT + 80 不得点亮 CLOSE_COMPLETE（R10-P1-02）。"""
    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )

    statuses = {name: "FINAL" for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    )}
    statuses["margin"] = "PENDING"
    statuses["tracks"] = "PENDING"
    snap = _phase_snapshot(statuses)
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 80.0
    assert snapshot_phase(snap) == PHASE_CAPTURED


def test_phase_tracks_partial_sufficient_80_is_close_complete():
    """PARTIAL + TRACKS_SUFFICIENT + 80 -> CLOSE_COMPLETE + validator PASS。"""
    import copy
    import json

    from collector.completeness import (
        PHASE_CLOSE_COMPLETE,
        snapshot_phase,
    )
    from collector.validators.schema import validate_snapshot

    with open(
        "web/public/data/daily/2026/2026-07-17.json",
        "r",
        encoding="utf-8",
    ) as f:
        snap = json.load(f)

    # 以真实 FINAL 快照为基础，仅把 tracks 降级为受约束 PARTIAL sufficient
    snap["modules"]["tracks"]["status"] = "PARTIAL"
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 80.0
    snap["modules"]["tracks"]["dataDate"] = "2026-07-17"
    snap["overallStatus"] = "PARTIAL"

    assert snapshot_phase(snap) == PHASE_CLOSE_COMPLETE
    validate_snapshot(snap)


def test_phase_tracks_partial_invalid_coverage_fails_closed():
    """PARTIAL sufficient 的 Inf/101/bool/79.9 均不得点亮，validator 拒绝。"""
    import pytest

    from collector.completeness import (
        PHASE_CAPTURED,
        snapshot_phase,
    )
    from collector.validators.schema import validate_snapshot

    for coverage in (float("inf"), 101.0, True, 79.9):
        statuses = {name: "FINAL" for name in (
            "marketIndex", "turnover", "sentiment", "sectorPerformance",
            "fundFlow", "northbound", "summary",
        )}
        statuses["margin"] = "PENDING"
        statuses["tracks"] = "PARTIAL"
        snap = _phase_snapshot(statuses)
        snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
        snap["modules"]["tracks"]["coveragePct"] = coverage
        snap["modules"]["tracks"]["dataDate"] = "2026-08-14"
        snap["overallStatus"] = "PARTIAL"

        assert snapshot_phase(snap) == PHASE_CAPTURED

        with pytest.raises(ValueError):
            validate_snapshot(snap)


def test_margin_reference_rejects_filename_trade_date_mismatch(
    tmp_path,
    monkeypatch,
):
    """文件名=08-13、snapshot.tradeDate=08-12 -> reference 必须跳过（R10-P2-01）。"""
    import json

    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_daily = test_root / "data" / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    prev_dir = test_daily / "2026"
    prev_dir.mkdir(parents=True, exist_ok=True)

    (prev_dir / "2026-08-13.json").write_text(
        json.dumps({
            "tradeDate": "2026-08-12",
            "modules": {
                "margin": {
                    "status": "FINAL",
                    "dataDate": "2026-08-12",
                    "financingBalance": 100.0,
                    "securitiesLendingBalance": 5.0,
                    "marginBalance": 105.0,
                }
            },
        }),
        encoding="utf-8",
    )

    assert (
        _latest_published_reference("2026-08-14")
        is None
    )


def test_margin_reference_rejects_margin_data_date_mismatch(
    tmp_path,
    monkeypatch,
):
    """snapshot.tradeDate=08-13、margin.dataDate=08-12 -> 跳过（R10-P2-01）。"""
    import json

    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_daily = test_root / "data" / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    prev_dir = test_daily / "2026"
    prev_dir.mkdir(parents=True, exist_ok=True)

    (prev_dir / "2026-08-13.json").write_text(
        json.dumps({
            "tradeDate": "2026-08-13",
            "modules": {
                "margin": {
                    "status": "FINAL",
                    "dataDate": "2026-08-12",
                    "financingBalance": 100.0,
                    "securitiesLendingBalance": 5.0,
                    "marginBalance": 105.0,
                }
            },
        }),
        encoding="utf-8",
    )

    assert (
        _latest_published_reference("2026-08-14")
        is None
    )


def test_manifest_rejects_daily_identity_mismatch(
    tmp_path,
    monkeypatch,
):
    """文件名=08-14、snapshot.tradeDate=08-13 -> manifest 更新必须抛错（R10-P2-01）。"""
    import pytest

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        update_manifest_and_latest,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    snap = new_snapshot("2026-08-13")
    for module in snap["modules"].values():
        module["status"] = "FINAL"
        module["dataDate"] = "2026-08-13"
    snap["overallStatus"] = "FINAL"

    # 故意错名：内容 tradeDate=08-13 却写到 08-14 文件名
    _write_json_atomic(day_dir / "2026-08-14.json", snap)

    with pytest.raises(RuntimeError):
        update_manifest_and_latest(
            "2026-08-14",
            snap,
        )


def test_derived_publish_recovers_after_second_file_failure(
    tmp_path,
    monkeypatch,
):
    """第二派生文件写失败后，下一次 ensure_derived_state_consistent 必须恢复（R10-P1-01）。"""
    import json

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        ensure_derived_state_consistent,
        update_manifest_and_latest,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    snap = new_snapshot("2026-08-14")
    for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    ):
        snap["modules"][name]["status"] = "FINAL"
        snap["modules"][name]["dataDate"] = "2026-08-14"
    snap["modules"]["margin"]["status"] = "PENDING"
    snap["modules"]["tracks"]["status"] = "UNAVAILABLE"
    snap["overallStatus"] = "PARTIAL_PENDING"

    _write_json_atomic(day_dir / "2026-08-14.json", snap)

    # 首次正常更新
    update_manifest_and_latest("2026-08-14", snap)

    # 故障注入：模拟第二派生文件(latest)失败——把 latest.json 删掉
    (test_data / "latest.json").unlink()

    # 一致性修复入口必须重建 latest.json
    repaired = ensure_derived_state_consistent("2026-08-14", snap)

    assert repaired is True
    assert (test_data / "latest.json").exists()

    restored = json.loads(
        (test_data / "latest.json").read_text(encoding="utf-8")
    )

    assert restored["tradeDate"] == "2026-08-14"

    # 再次执行应为 NO_REPAIR（幂等）
    assert ensure_derived_state_consistent("2026-08-14", snap) is False


def test_no_change_path_repairs_interrupted_derived_publish(
    tmp_path,
    monkeypatch,
):
    """NO_CHANGE 路径也必须修复派生分叉，且不制造无意义时间戳（R10-P1-01）。"""
    import json

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        ensure_derived_state_consistent,
        write_if_changed,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    import json

    # 以真实 08-14 快照为基（V1 口径、margin 已 PENDING），仅修正 tracks
    with open(
        "web/public/data/daily/2026/2026-08-14.json",
        "r",
        encoding="utf-8",
    ) as f:
        snap = json.load(f)

    snap["modules"]["tracks"]["status"] = "UNAVAILABLE"
    snap["modules"]["tracks"]["dataDate"] = "2026-08-14"
    snap["overallStatus"] = "PARTIAL_PENDING"

    # 首次写入
    changed, _ = write_if_changed(snap)
    assert changed

    from collector.jobs.common import update_manifest_and_latest

    update_manifest_and_latest("2026-08-14", snap)

    # 模拟派生分叉：删掉 status.json
    (test_data / "status.json").unlink()

    # 同语义重跑 -> NO_CHANGE，但 ensure 必须修复 status.json
    changed, reason = write_if_changed(snap)
    assert not changed
    assert reason == "NO_CHANGE"

    repaired = ensure_derived_state_consistent("2026-08-14", snap)
    assert repaired is True
    assert (test_data / "status.json").exists()

    # 再次 ensure 幂等
    assert ensure_derived_state_consistent("2026-08-14", snap) is False


def test_validator_rejects_reference_unbalanced_balance():
    """reference 三项余额不守恒（|total-(fin+lend)|>0.05）必须拒绝（R10.2-N04）。"""
    import pytest

    from collector.validators.schema import validate_snapshot

    mutated = _margin_pending_mutation({
        "dataDate": "2026-07-16",
        "financingBalance": 100.0,
        "securitiesLendingBalance": 5.0,
        "marginBalance": 110.0,  # 100+5=105，偏差 5 > 0.05
    })

    with pytest.raises(ValueError):
        validate_snapshot(mutated)


def test_write_if_changed_raises_on_readback_corruption(
    tmp_path,
    monkeypatch,
):
    """严格回读防线：落盘后读回失败必须 raise，不得静默成功（R10-P1-01 变异敏感度）。"""
    import json

    import pytest

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import write_if_changed

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    with open(
        "web/public/data/daily/2026/2026-08-14.json",
        "r",
        encoding="utf-8",
    ) as f:
        snap = json.load(f)

    original_read = common._read_json

    def corrupting_read(path):
        value = original_read(path)
        if (
            value is not None
            and isinstance(value, dict)
            and value.get("tradeDate") == "2026-08-14"
        ):
            return None  # 模拟回读失败/损坏
        return value

    monkeypatch.setattr(
        common,
        "_read_json",
        corrupting_read,
    )

    with pytest.raises(RuntimeError):
        write_if_changed(snap)


def test_write_json_atomic_raises_on_readback_corruption(
    tmp_path,
    monkeypatch,
):
    """派生文件严格回读防线：读回失败必须 raise（R10-P1-01 变异敏感度）。"""
    import pytest

    import collector.jobs.common as common

    monkeypatch.setattr(
        common,
        "_read_json",
        lambda path: None,
    )

    with pytest.raises(RuntimeError):
        common._write_json_atomic(
            tmp_path / "derived.json",
            {"k": 1},
        )


def test_daily_no_change_retry_reconfirms_parent_fsync(
    tmp_path,
    monkeypatch,
):
    """R10.2-P1-01：replace 成功后 parent fsync 失败 -> 同语义重试必须重新 fsync。"""
    import json

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import write_if_changed

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    with open(
        "web/public/data/daily/2026/2026-08-14.json",
        "r",
        encoding="utf-8",
    ) as f:
        snap = json.load(f)

    # 首次写入成功
    changed, _ = write_if_changed(snap)
    assert changed

    # 故障注入：parent fsync 首次调用抛错
    original_fsync = common._fsync_directory
    calls = {"n": 0}

    def flaky_fsync(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected fsync failure")
        return original_fsync(path)

    monkeypatch.setattr(common, "_fsync_directory", flaky_fsync)

    # 同语义重试：首次（写入路径）fsync 失败 -> raise
    import pytest

    with pytest.raises(OSError):
        write_if_changed(snap)

    # 恢复后再次同语义调用 -> NO_CHANGE 且必须重新 fsync（防 durability 不确定被压平）
    monkeypatch.setattr(common, "_fsync_directory", original_fsync)
    fsync_calls = {"n": 0}

    def counting_fsync(path):
        fsync_calls["n"] += 1
        return original_fsync(path)

    monkeypatch.setattr(common, "_fsync_directory", counting_fsync)

    changed, reason = write_if_changed(snap)
    assert not changed
    assert reason == "NO_CHANGE"
    assert fsync_calls["n"] >= 1


def test_derived_no_repair_reconfirms_parent_fsync(
    tmp_path,
    monkeypatch,
):
    """R10.2-P1-01：派生一致但上一事务 fsync 未确认 -> no-repair 路径也必须重新 fsync。"""
    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        ensure_derived_state_consistent,
        update_manifest_and_latest,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    snap = new_snapshot("2026-08-14")
    for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    ):
        snap["modules"][name]["status"] = "FINAL"
        snap["modules"][name]["dataDate"] = "2026-08-14"
    snap["modules"]["margin"]["status"] = "PENDING"
    snap["modules"]["tracks"]["status"] = "UNAVAILABLE"
    snap["overallStatus"] = "PARTIAL_PENDING"

    _write_json_atomic(day_dir / "2026-08-14.json", snap)
    update_manifest_and_latest("2026-08-14", snap)

    original_fsync = common._fsync_directory
    fsync_calls = {"n": 0}

    def counting_fsync(path):
        fsync_calls["n"] += 1
        return original_fsync(path)

    monkeypatch.setattr(common, "_fsync_directory", counting_fsync)

    # 派生已一致 -> no-repair，但必须重新 fsync 数据目录
    repaired = ensure_derived_state_consistent("2026-08-14", snap)

    assert repaired is False
    assert fsync_calls["n"] >= 1


def test_manifest_rejects_partial_tracks_data_date_mismatch(
    tmp_path,
    monkeypatch,
):
    """R10.2-P2-01：PARTIAL tracks dataDate 错日不得参与索引（CC 指针不可被推进）。"""
    import pytest

    import collector.config as config
    import collector.jobs.common as common
    from collector.jobs.common import (
        _write_json_atomic,
        update_manifest_and_latest,
    )
    from collector.schema import new_snapshot

    test_root = tmp_path / "repo"
    test_data = test_root / "data"
    test_daily = test_data / "daily"
    test_calendar = test_data / "calendar"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)
    monkeypatch.setattr(config, "CALENDAR_DIR", test_calendar)
    monkeypatch.setattr(common, "DAILY_DIR", test_daily)

    day_dir = test_daily / "2026"
    day_dir.mkdir(parents=True, exist_ok=True)

    snap = new_snapshot("2026-08-14")
    for name in (
        "marketIndex", "turnover", "sentiment", "sectorPerformance",
        "fundFlow", "northbound", "summary",
    ):
        snap["modules"][name]["status"] = "FINAL"
        snap["modules"][name]["dataDate"] = "2026-08-14"
    snap["modules"]["margin"]["status"] = "PENDING"
    snap["modules"]["tracks"]["status"] = "PARTIAL"
    snap["modules"]["tracks"]["decision"] = "TRACKS_SUFFICIENT"
    snap["modules"]["tracks"]["coveragePct"] = 80.0
    snap["modules"]["tracks"]["dataDate"] = "2026-08-13"  # 错日
    snap["overallStatus"] = "PARTIAL"

    _write_json_atomic(day_dir / "2026-08-14.json", snap)

    with pytest.raises(RuntimeError):
        update_manifest_and_latest("2026-08-14", snap)


def test_margin_reference_accepts_exact_boundary_conservation(
    tmp_path,
    monkeypatch,
):
    """R10.2-P2-02：Decimal 口径——恰好 +0.05 的 reference 必须被 collector 接受。"""
    import json

    import collector.config as config
    from collector.modules.margin import (
        _latest_published_reference,
    )

    test_root = tmp_path / "repo"
    test_daily = test_root / "data" / "daily"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_daily)

    prev_dir = test_daily / "2026"
    prev_dir.mkdir(parents=True, exist_ok=True)

    # 十进制精确差 = 0.05，按业务规则应通过
    (prev_dir / "2026-08-13.json").write_text(
        json.dumps({
            "tradeDate": "2026-08-13",
            "modules": {
                "margin": {
                    "status": "FINAL",
                    "dataDate": "2026-08-13",
                    "financingBalance": 99900.0,
                    "securitiesLendingBalance": 100.0,
                    "marginBalance": 100000.05,
                }
            },
        }),
        encoding="utf-8",
    )

    ref = _latest_published_reference("2026-08-14")

    assert ref is not None
    assert ref["dataDate"] == "2026-08-13"


def test_validator_reference_boundary_decimal():
    """R10.2-P2-02：validator 恰好 +0.05 通过；+0.06 拒绝。"""
    import pytest

    from collector.validators.schema import validate_snapshot

    valid = _margin_pending_mutation({
        "dataDate": "2026-07-16",
        "financingBalance": 99900.0,
        "securitiesLendingBalance": 100.0,
        "marginBalance": 100000.05,
    })
    validate_snapshot(valid)

    invalid = _margin_pending_mutation({
        "dataDate": "2026-07-16",
        "financingBalance": 99900.0,
        "securitiesLendingBalance": 100.0,
        "marginBalance": 100000.06,
    })

    with pytest.raises(ValueError):
        validate_snapshot(invalid)
