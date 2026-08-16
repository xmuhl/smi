# -*- coding: utf-8 -*-
"""⑧ daily raw archive 测试：核心 append 幂等/校验 + 采集器归一化（离线）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from datetime import date

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# archive.append_record / read_records / count_records（纯本地，tmp_path 隔离）
# ---------------------------------------------------------------------------

def _patch_archive_dir(tmp_path, monkeypatch):
    import collector.config as config
    import collector.archive as archive

    test_root = tmp_path / "repo"
    test_archive = test_root / "data" / "archive"

    monkeypatch.setattr(config, "PROJECT_ROOT", test_root)
    monkeypatch.setattr(config, "DATA_DIR", test_root / "data")
    monkeypatch.setattr(config, "DAILY_DIR", test_root / "data" / "daily")
    monkeypatch.setattr(config, "CALENDAR_DIR", test_root / "data" / "calendar")
    monkeypatch.setattr(config, "ARCHIVE_DIR", test_archive)
    # archive 模块 import 时绑定了 ARCHIVE_DIR，需同步打补丁
    monkeypatch.setattr(archive, "ARCHIVE_DIR", test_archive)

    return archive


def test_archive_append_and_read_roundtrip(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 1985.0,
            "high": 1990.0,
            "low": 1929.0,
            "close": 1937.4,
            "volume": 100,
            "amount": 1e9,
        },
    )

    assert ok
    assert reason == "APPENDED"

    records = archive.read_records(
        "track-board-close",
        trade_date="2026-08-14",
    )

    assert len(records) == 1
    assert records[0]["close"] == 1937.4
    assert records[0]["kind"] == "track-board-close"

    assert archive.count_records("track-board-close") == 1


def test_archive_append_idempotent_dedupe(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    record = {
        "tradeDate": "2026-08-14",
        "trackId": "power",
        "boardCode": "BK0428",
        "source": "THS_INDEX_V1",
        "open": 1985.0,
        "high": 1990.0,
        "low": 1929.0,
        "close": 1937.4,
        "volume": 100,
        "amount": 1e9,
    }

    ok1, r1 = archive.append_record("track-board-close", record)
    ok2, r2 = archive.append_record("track-board-close", record)

    assert ok1 and r1 == "APPENDED"
    assert not ok2 and r2 == "ALREADY_EXISTS"
    assert archive.count_records("track-board-close") == 1


def test_archive_rejects_invalid_trade_date(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "08/14/2026",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 1,
            "amount": 1,
        },
    )

    assert not ok
    assert reason.startswith("INVALID")
    assert archive.count_records("track-board-close") == 0


def test_archive_rejects_nonfinite_close(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": float("nan"),
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 1,
            "amount": 1,
        },
    )

    assert not ok
    assert reason.startswith("INVALID")


def test_archive_rejects_bad_limit_up_pool_codes(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "limit-up-pool",
        {
            "tradeDate": "2026-08-14",
            "trackId": "*",
            "boardCode": "*",
            "source": "EM_ZT_POOL_V1",
            "items": [
                {"code": "000936", "name": "A"},
                {"code": "abc", "name": "BAD"},
            ],
            "counts": {
                "nonStLimitUpCount": 1,
                "stLimitUpCount": 0,
            },
        },
    )

    assert not ok
    assert reason.startswith("INVALID")


def test_archive_rejects_negative_counts(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "limit-up-pool",
        {
            "tradeDate": "2026-08-14",
            "trackId": "*",
            "boardCode": "*",
            "source": "EM_ZT_POOL_V1",
            "items": [],
            "counts": {
                "nonStLimitUpCount": -1,
                "stLimitUpCount": 0,
            },
        },
    )

    assert not ok
    assert reason.startswith("INVALID")


def test_archive_unknown_kind_rejected(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "not-a-kind",
        {"tradeDate": "2026-08-14"},
    )

    assert not ok
    assert reason.startswith("UNKNOWN_KIND")


# ---------------------------------------------------------------------------
# 采集器归一化（monkeypatch akshare，离线）
# ---------------------------------------------------------------------------

def _install_fake_akshare(monkeypatch):
    fake = ModuleType("akshare")

    def stock_board_concept_index_ths(
        symbol=None,
        start_date=None,
        end_date=None,
    ):
        return pd.DataFrame({
            "日期": [date(2026, 8, 13), date(2026, 8, 14)],
            "开盘价": [100.0, 101.0],
            "最高价": [102.0, 103.0],
            "最低价": [99.0, 100.0],
            "收盘价": [101.0, 102.5],
            "成交量": [1000, 1100],
            "成交额": [1e9, 1.1e9],
        })

    def stock_board_industry_index_ths(
        symbol=None,
        start_date=None,
        end_date=None,
    ):
        return stock_board_concept_index_ths(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def stock_fund_flow_industry(symbol=None):
        return pd.DataFrame({
            "行业": ["电力", "其他"],
            "净额": [12.5, -3.0],
        })

    def stock_fund_flow_concept(symbol=None):
        return pd.DataFrame({
            "行业": ["同花顺中特估100", "其他"],
            "净额": [5.0, -1.0],
        })

    def stock_zt_pool_em(date=None):
        return pd.DataFrame({
            "代码": ["000936", "600001"],
            "名称": ["华西股份", "ST测试"],
            "涨跌幅": [9.9, 5.0],
            "最新价": [6.97, 2.0],
            "成交额": [1e8, 2e8],
            "换手率": [15.4, 5.0],
            "封板资金": [4e7, 1e7],
            "首次封板时间": ["092500", "100000"],
            "最后封板时间": ["105703", "110000"],
            "炸板次数": [7, 0],
            "涨停统计": ["3/3", "1/1"],
            "连板数": [3, 1],
            "所属行业": ["化学纤维", "综合"],
        })

    def stock_board_industry_cons_em(symbol=None):
        return pd.DataFrame({
            "代码": ["600011", "600021", "600027"],
            "名称": ["A", "B", "C"],
        })

    fake.stock_board_concept_index_ths = stock_board_concept_index_ths
    fake.stock_board_industry_index_ths = stock_board_industry_index_ths
    fake.stock_fund_flow_industry = stock_fund_flow_industry
    fake.stock_fund_flow_concept = stock_fund_flow_concept
    fake.stock_zt_pool_em = stock_zt_pool_em
    fake.stock_board_industry_cons_em = stock_board_industry_cons_em

    monkeypatch.setitem(sys.modules, "akshare", fake)


def test_collect_board_close_ok(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_board_close,
    )

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_board_close("2026-08-14", power)

    assert result["ok"]
    assert result["record"]["close"] == 102.5
    assert result["record"]["source"] == "THS_INDEX_V1"


def test_collect_board_close_date_not_found(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_board_close,
    )

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_board_close("2026-08-11", power)

    assert not result["ok"]
    assert result["reason"] == "DATE_NOT_FOUND"


def test_collect_board_flow_ok_when_today(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.schema import TZ_SHANGHAI
    from datetime import datetime

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_board_flow,
    )

    today = datetime.now(TZ_SHANGHAI).date().isoformat()

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_board_flow(today, power)

    assert result["ok"]
    assert result["record"]["mainNetInflow"] == 12.5


def test_collect_board_flow_rejects_history(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_board_flow,
    )

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_board_flow("2026-08-14", power)

    assert not result["ok"]
    assert result["reason"] == "HISTORICAL_FLOW_UNSUPPORTED"


def test_collect_limit_up_pool_ok(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import collect_limit_up_pool

    result = collect_limit_up_pool("2026-08-14")

    assert result["ok"]
    assert result["record"]["counts"]["nonStLimitUpCount"] == 1
    assert result["record"]["counts"]["stLimitUpCount"] == 1
    assert len(result["record"]["items"]) == 2
    assert result["record"]["items"][0]["streak"] == 3


def test_collect_membership_ok_when_today(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.schema import TZ_SHANGHAI
    from datetime import datetime

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_membership,
    )

    today = datetime.now(TZ_SHANGHAI).date().isoformat()

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_membership(today, power)

    assert result["ok"]
    assert len(result["record"]["members"]) == 3
    assert result["record"]["memberCount"] == 3


def test_collect_membership_rejects_history(
    monkeypatch,
):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_membership,
    )

    power = next(
        t
        for t in _expanded_tracks()
        if t["trackId"] == "power"
    )

    result = collect_membership("2026-08-14", power)

    assert not result["ok"]
    assert result["reason"] == "HISTORICAL_MEMBERSHIP_UNSUPPORTED"
# ---------------------------------------------------------------------------
# [FIX] 补充测试：并发 / 损坏行 / 边界校验 / composite / 异常包装 / ST 谓词
# ---------------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor


@pytest.mark.skipif(sys.platform == "win32", reason="flock only on POSIX; Windows relies on single-writer convention (sec 39.5.5)")
def test_archive_concurrent_appends_no_loss(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    def append_one(i: int):
        return archive.append_record(
            "track-board-flow",
            {
                "tradeDate": "2026-08-14",
                "trackId": "power",
                "boardCode": f"BK{i:04d}",
                "source": "THS_FLOW_V1",
                "mainNetInflow": float(i),
                "unit": "亿元",
            },
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(append_one, range(24)))

    assert all(ok for ok, _ in results)
    assert archive.count_records("track-board-flow") == 24


def test_archive_tolerates_corrupt_lines(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    path = archive.ARCHIVE_DIR / "track-board-close.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "{not json\n"
        "[1,2,3]\n"
        "\"just a string\"\n"
        "42\n"
        "{\"kind\":\"track-board-close\",\"tradeDate\":\"2026-08-13\","
        "\"trackId\":\"power\",\"boardCode\":\"BK0428\","
        "\"source\":\"THS_INDEX_V1\",\"open\":1,\"high\":2,\"low\":0.5,"
        "\"close\":1.5,\"volume\":1,\"amount\":1}\n",
        encoding="utf-8",
    )

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 1,
            "amount": 1,
        },
    )

    assert ok, reason
    assert archive.count_records("track-board-close") == 2
    assert len(archive.read_records("track-board-close")) == 2


def test_archive_rejects_low_gt_high(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 3.0,
            "high": 2.0,
            "low": 5.0,
            "close": 1.5,
            "volume": 1,
            "amount": 1,
        },
    )

    assert not ok
    assert "low > high" in reason


def test_archive_rejects_close_out_of_range(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 1.5,
            "high": 2.0,
            "low": 1.0,
            "close": 3.0,
            "volume": 1,
            "amount": 1,
        },
    )

    assert not ok
    assert "close out of" in reason


def test_archive_high_none_rejected_not_crash(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_INDEX_V1",
            "open": 1.0,
            "high": None,
            "low": 0.5,
            "close": 1.5,
            "volume": 1,
            "amount": 1,
        },
    )

    assert not ok
    assert "high must be finite number" in reason


def test_archive_rejects_nan_in_zt_item_numeric(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "limit-up-pool",
        {
            "tradeDate": "2026-08-14",
            "trackId": "*",
            "boardCode": "*",
            "source": "EM_ZT_POOL_V1",
            "items": [
                {"code": "000936", "name": "A", "changePct": float("nan")},
            ],
            "counts": {
                "nonStLimitUpCount": 1,
                "stLimitUpCount": 0,
            },
        },
    )

    assert not ok
    assert "changePct" in reason


def test_archive_rejects_counts_items_mismatch(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "limit-up-pool",
        {
            "tradeDate": "2026-08-14",
            "trackId": "*",
            "boardCode": "*",
            "source": "EM_ZT_POOL_V1",
            "items": [
                {"code": "000936", "name": "A"},
                {"code": "600001", "name": "B"},
            ],
            "counts": {
                "nonStLimitUpCount": 3,
                "stLimitUpCount": 0,
            },
        },
    )

    assert not ok
    assert "len(items)" in reason


def test_archive_rejects_missing_track_id(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-flow",
        {
            "tradeDate": "2026-08-14",
            "boardCode": "BK0428",
            "source": "THS_FLOW_V1",
            "mainNetInflow": 1.0,
        },
    )

    assert not ok
    assert "missing trackId" in reason


def test_archive_rejects_member_count_mismatch(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-membership-snapshot",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "EM_BOARD_CONS_V1",
            "members": ["600011", "600021", "600027"],
            "memberCount": 2,
        },
    )

    assert not ok
    assert "memberCount" in reason


def test_archive_serialize_failure_returns_invalid(tmp_path, monkeypatch):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    record = {
        "tradeDate": "2026-08-14",
        "trackId": "power",
        "boardCode": "BK0428",
        "source": "THS_FLOW_V1",
        "mainNetInflow": 1.0,
        "extraNote": float("nan"),  # 未知字段绕过行级校验，序列化必须兜底
    }

    ok, reason = archive.append_record("track-board-flow", record)

    assert not ok
    assert reason.startswith("INVALID:serialize")
    assert archive.count_records("track-board-flow") == 0


def test_expanded_tracks_composite(monkeypatch):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import _expanded_tracks

    rows = _expanded_tracks()

    assert len(rows) == 5  # 3 个普通 track + semiconductor_ai 拆 2 子板块

    semi = [r for r in rows if r["trackId"] == "semiconductor_ai"]
    assert {r["boardCode"] for r in semi} == {"BK1036", "BK1134"}

    by_code = {r["boardCode"]: r for r in semi}
    assert by_code["BK1036"]["boardType"] == "industry"
    assert by_code["BK1036"]["indexNameThs"] == "半导体"
    assert by_code["BK1134"]["boardType"] == "concept"
    assert by_code["BK1134"]["indexNameThs"] == "东数西算(算力)"
    assert by_code["BK1036"]["weight"] == 0.5


def test_collect_board_close_missing_index_name(monkeypatch):
    _install_fake_akshare(monkeypatch)

    from collector.modules.raw_archive import collect_board_close

    track = {
        "trackId": "x",
        "trackName": "X",
        "boardType": "industry",
        "boardCode": "BK0000",
        "boardName": "",
        "indexNameThs": None,
    }

    result = collect_board_close("2026-08-14", track)

    assert not result["ok"]
    assert result["reason"] == "INDEX_NAME_THS_MISSING"


def test_collect_membership_concept_disabled(monkeypatch):
    _install_fake_akshare(monkeypatch)

    from datetime import datetime

    from collector.schema import TZ_SHANGHAI
    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_membership,
    )

    today = datetime.now(TZ_SHANGHAI).date().isoformat()

    cnsoe = next(
        t for t in _expanded_tracks() if t["trackId"] == "dividend_cnsoe"
    )

    result = collect_membership(today, cnsoe)

    assert not result["ok"]
    assert result["reason"] == "CONCEPT_CONS_DISABLED"


def test_collect_wraps_upstream_exception(monkeypatch):
    fake = ModuleType("akshare")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    fake.stock_board_industry_index_ths = boom
    fake.stock_board_concept_index_ths = boom
    monkeypatch.setitem(sys.modules, "akshare", fake)

    from collector.modules.raw_archive import (
        _expanded_tracks,
        collect_board_close,
    )

    power = next(t for t in _expanded_tracks() if t["trackId"] == "power")

    result = collect_board_close("2026-08-14", power)

    assert not result["ok"]
    assert result["reason"].startswith("FETCH_FAILED")


def test_collect_limit_up_pool_filters_bad_codes(monkeypatch):
    fake = ModuleType("akshare")

    def stock_zt_pool_em(date=None):
        return pd.DataFrame({
            "代码": ["000936", "600001", "abc", None],
            "名称": ["华西股份", "ST测试", "坏", None],
            "涨跌幅": [9.9, 5.0, 0.0, 0.0],
            "最新价": [6.97, 2.0, 0.0, 0.0],
            "成交额": [1e8, 2e8, 0.0, 0.0],
            "换手率": [15.4, 5.0, 0.0, 0.0],
            "封板资金": [4e7, 1e7, 0.0, 0.0],
            "首次封板时间": ["092500", "100000", "", ""],
            "最后封板时间": ["105703", "110000", "", ""],
            "炸板次数": [7, 0, 0, 0],
            "涨停统计": ["3/3", "1/1", "", ""],
            "连板数": [3, 1, 0, 0],
            "所属行业": ["化学纤维", "综合", "", ""],
        })

    fake.stock_zt_pool_em = stock_zt_pool_em
    monkeypatch.setitem(sys.modules, "akshare", fake)

    from collector.modules.raw_archive import collect_limit_up_pool

    result = collect_limit_up_pool("2026-08-14")

    assert result["ok"]
    assert len(result["record"]["items"]) == 2
    assert result["record"]["counts"]["droppedItemCount"] == 2
    assert result["record"]["counts"]["nonStLimitUpCount"] == 1
    assert result["record"]["counts"]["stLimitUpCount"] == 1


@pytest.mark.parametrize(
    "name,expected",
    [
        ("ST测试", True),
        ("*ST广泰", True),
        ("S*ST前锋", True),
        ("SST华新", True),
        ("st慧球", True),
        ("华西股份", False),
        ("S佳通", False),
        ("电力", False),
        ("", False),
        (None, False),
    ],
)
def test_is_st_stock_name(name, expected):
    from collector.modules.raw_archive import is_st_stock_name

    assert is_st_stock_name(name) is expected



# ---------------------------------------------------------------------------
# [R11.2] ChatGPT R11.1 复核回归：耐久/坏尾行/kind 分叉/零代码 sentinel
# ---------------------------------------------------------------------------


def test_archive_unterminated_corrupt_tail_preserves_new_record(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    path = archive.ARCHIVE_DIR / "track-board-flow.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"broken":', encoding="utf-8")

    ok, reason = archive.append_record(
        "track-board-flow",
        {
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_FLOW_V1",
            "mainNetInflow": 1.2,
        },
    )

    assert ok and reason == "APPENDED"
    records = archive.read_records("track-board-flow")
    assert len(records) == 1
    assert records[0]["trackId"] == "power"


def test_archive_rejects_record_kind_mismatch(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    ok, reason = archive.append_record(
        "track-board-close",
        {
            "kind": "track-board-flow",
            "tradeDate": "2026-08-14",
            "trackId": "power",
            "boardCode": "BK0428",
            "source": "THS_FLOW_V1",
            "mainNetInflow": 1.2,
        },
    )

    assert not ok
    assert reason.startswith("INVALID:kind mismatch")


def test_archive_retry_reconfirms_parent_fsync_after_replace_failure(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    calls = {"n": 0}
    real_fsync_directory = archive._fsync_directory

    def flaky_fsync_directory(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected parent fsync failure")
        return real_fsync_directory(path)

    monkeypatch.setattr(
        archive,
        "_fsync_directory",
        flaky_fsync_directory,
    )

    record = {
        "tradeDate": "2026-08-14",
        "trackId": "power",
        "boardCode": "BK0428",
        "source": "THS_FLOW_V1",
        "mainNetInflow": 1.2,
    }

    with pytest.raises(OSError):
        archive.append_record("track-board-flow", record)

    ok, reason = archive.append_record(
        "track-board-flow",
        record,
    )

    assert not ok
    assert reason == "ALREADY_EXISTS"
    assert calls["n"] >= 2


@pytest.mark.parametrize(
    "value",
    [
        "000000",
        "0",
        0,
    ],
)
def test_clean_stock_code_rejects_zero_sentinel(value):
    from collector.modules.raw_archive import _clean_stock_code

    assert _clean_stock_code(value) is None



# ---------------------------------------------------------------------------
# [R11.3] ChatGPT R11.2 复核回归：payload-aware dedupe / readback 失败重试
# ---------------------------------------------------------------------------


def test_archive_same_key_different_payload_is_conflict(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    base = {
        "tradeDate": "2026-08-14",
        "trackId": "power",
        "boardCode": "BK0428",
        "source": "THS_FLOW_V1",
        "mainNetInflow": 1.2,
    }

    ok, reason = archive.append_record(
        "track-board-flow",
        base,
    )

    assert ok
    assert reason == "APPENDED"

    changed = dict(base)
    changed["mainNetInflow"] = 9.9

    with pytest.raises(
        RuntimeError,
        match="archive key conflict",
    ):
        archive.append_record(
            "track-board-flow",
            changed,
        )


def test_archive_readback_mismatch_retry_stays_fail_closed(
    tmp_path,
    monkeypatch,
):
    archive = _patch_archive_dir(tmp_path, monkeypatch)

    record = {
        "tradeDate": "2026-08-14",
        "trackId": "power",
        "boardCode": "BK0428",
        "source": "THS_FLOW_V1",
        "mainNetInflow": 1.2,
    }

    real_replace = archive.os.replace
    injected = {"done": False}

    def corrupt_after_replace(src, dst):
        real_replace(src, dst)

        if injected["done"]:
            return

        injected["done"] = True

        path = Path(dst)
        obj = json.loads(
            path.read_text(
                encoding="utf-8",
            ).strip()
        )

        obj["mainNetInflow"] = 999.0

        path.write_text(
            json.dumps(
                obj,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        archive.os,
        "replace",
        corrupt_after_replace,
    )

    with pytest.raises(
        RuntimeError,
        match="strict readback mismatch",
    ):
        archive.append_record(
            "track-board-flow",
            record,
        )

    monkeypatch.setattr(
        archive.os,
        "replace",
        real_replace,
    )

    with pytest.raises(
        RuntimeError,
        match="archive key conflict",
    ):
        archive.append_record(
            "track-board-flow",
            record,
        )



# ---------------------------------------------------------------------------
# [R11.4] ChatGPT R11.3 复核回归：workflow 发布门禁合约（rc!=0 禁止 build/deploy）
# ---------------------------------------------------------------------------


def test_archive_workflow_nonzero_rc_cannot_build_or_deploy():
    root = Path(__file__).resolve().parents[2]
    workflow = (
        root
        / ".github"
        / "workflows"
        / "archive-raw.yml"
    ).read_text(encoding="utf-8")

    archive_gate = "steps.archive.outputs.exit_code == '0'"

    for step_name in (
        "Setup Node",
        "Install web dependencies",
        "Type check",
        "Build",
        "Deploy to Cloudflare Pages",
    ):
        marker = f"- name: {step_name}"
        start = workflow.index(marker)
        next_step = workflow.find("\n      - name:", start + len(marker))

        block = (
            workflow[start:]
            if next_step < 0
            else workflow[start:next_step]
        )

        assert archive_gate in block, (
            f"{step_name} must be gated by archive exit_code == 0"
        )

    propagate = workflow.index("- name: Propagate archive failure")
    setup_node = workflow.index("- name: Setup Node")

    assert propagate < setup_node
