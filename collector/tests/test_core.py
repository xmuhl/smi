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
