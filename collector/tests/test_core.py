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

def test_manual_backfill_rejects_today():
    """R9-P2-04：manual_backfill 仅允许历史日。"""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "collector.jobs.manual_backfill",
            "--date",
            "2026-08-15",
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



