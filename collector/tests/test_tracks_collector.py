"""真实采集器（模块 8：主赛道监测）测试。

Monkeypatch collector.archive.read_records（零联网）。覆盖：
- 3+ 个 track 假 board-close 序列（含 60 日数据）→ maAlignment 正确（多头排列与非排列两组）、
  rps60 排名正确（最强≈100）、turnoverRank 名次正确；
- flow 假数据 → mainNetInflow / continuousInflowDays（含中断日为 0 用例）；
- limit-up-pool 假数据 → limitUpCount 与 ladderCompleteness（"3连板"/"无连板"）；
- tracks.yaml 定性配置读取 → coreCatalyst 非空中文；
- 模块结果字段齐全、status 契约符合 validator（放入最小快照跑 validate_snapshot 不抛）。
"""

from __future__ import annotations

import datetime as _dt

import collector.archive as _archive
import collector.modules.tracks as tracks_mod
from collector.schema import new_snapshot, finalize_snapshot
from collector.status import ModuleStatus

TRADE_DATE = "2026-08-13"


def _business_days_back(count: int, end: _dt.date) -> list[str]:
    """返回以 end 为末日的 count 个交易日（含 end），向前按工作日步进。"""
    dates: list[str] = []
    cursor = end
    while len(dates) < count:
        if cursor.weekday() < 5:  # 周一到周五
            dates.append(cursor.isoformat())
        cursor -= _dt.timedelta(days=1)
    dates.reverse()
    return dates


def _close_row(dt: str, close: float, amount: float, board_code: str, track_id: str) -> dict:
    return {
        "tradeDate": dt,
        "trackId": track_id,
        "boardCode": board_code,
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": amount * 10.0,
        "amount": amount,
        "kind": "track-board-close",
        "source": "TEST",
        "capturedAt": "2026-08-13T15:00:00+08:00",
    }


def _close_series(
    track_id: str,
    board_code: str,
    start_close: float,
    step: float,
    day_count: int = 65,
    amount_base: float = 1000.0,
) -> list[dict]:
    """生成一条从 start_close 起步、每步 step 的 close 序列（升序，末=最强）。"""
    days = _business_days_back(day_count, _dt.date.fromisoformat(TRADE_DATE))
    rows = []
    for i, dt in enumerate(days):
        close = start_close + step * i
        # 让近期 amount 随 i 增长，确保降序排名按日序稳定
        amount = amount_base + i * 5.0
        rows.append(_close_row(dt, round(close, 2), round(amount, 2), board_code, track_id))
    return rows


def _flow_row(dt: str, value: float, board_code: str, track_id: str) -> dict:
    return {
        "tradeDate": dt,
        "trackId": track_id,
        "boardCode": board_code,
        "mainNetInflow": value,
        "kind": "track-board-flow",
        "source": "TEST",
        "capturedAt": "2026-08-13T15:00:00+08:00",
    }


def _pool_record(trade_date: str, items: list[dict]) -> dict:
    counts = {
        "nonStLimitUpCount": len(items),
        "stLimitUpCount": 0,
        "droppedItemCount": None,
    }
    return {
        "tradeDate": trade_date,
        "kind": "limit-up-pool",
        "source": "TEST",
        "capturedAt": "2026-08-13T15:00:00+08:00",
        "counts": counts,
        "items": items,
    }


def _build_fake_archive() -> dict[str, list[dict]]:
    """构造覆盖全部 track 的假归档数据。"""
    close_records: list[dict] = []
    flow_records: list[dict] = []
    pool_records: list[dict] = []

    # --- close：3 条简单赛道 + 半导体 composite 两子板 ---
    # dividend：强多头排列（start_close 低、step 大 → 近期盘最强），近5日 amount 最大
    close_records += _close_series("dividend_cnsoe", "BK1139", 1000.0, 8.0, amount_base=5000.0)
    # power：中等多头排列
    close_records += _close_series("power", "BK0428", 1500.0, 3.0, amount_base=3000.0)
    # healthcare：下跌（step 负 → 近端弱），ma5<ma10<ma20 → "否"
    close_records += _close_series("healthcare", "BK1216", 2000.0, -6.0, amount_base=2000.0)
    # semiconductor_ai composite 两子板
    close_records += _close_series("semiconductor_ai", "BK1036", 1200.0, 1.0, amount_base=2500.0)
    close_records += _close_series("semiconductor_ai", "BK1134", 1300.0, 1.5, amount_base=2200.0)

    # --- flow：近 5 个交易日的净流入（按板） ---
    days = _business_days_back(5, _dt.date.fromisoformat(TRADE_DATE))
    d = days[-1]
    d1, d2, d3, d4 = days[-2], days[-3], days[-4], days[-5]

    # dividend：5 日连续净流入
    for dt, v in ((d, 5.0), (d1, 4.0), (d2, 3.0), (d3, 2.0), (d4, 1.0)):
        flow_records.append(_flow_row(dt, v, "BK1139", "dividend_cnsoe"))
    # power：D、D-1 净流入，D-2 中断（<=0）
    for dt, v in ((d, 8.0), (d1, 2.0), (d2, -1.0), (d3, 3.0), (d4, 1.0)):
        flow_records.append(_flow_row(dt, v, "BK0428", "power"))
    # healthcare：D 净流出（<=0）
    for dt, v in ((d, -3.0), (d1, -2.0), (d2, 1.0), (d3, 2.0), (d4, 3.0)):
        flow_records.append(_flow_row(dt, v, "BK1216", "healthcare"))
    # semiconductor composite 两子板当日净流入为正（用于合成连续）
    for dt, v in ((d, 2.0), (d1, 1.0), (d2, 1.0), (d3, 1.0), (d4, 1.0)):
        flow_records.append(_flow_row(dt, v, "BK1036", "semiconductor_ai"))
        flow_records.append(_flow_row(dt, v + 1.0, "BK1134", "semiconductor_ai"))

    # --- limit-up pool：D 当日 ---
    pool_items = [
        # 命中 dividend（行业/名称含 中特估）
        {"code": "601111", "name": "中国中车", "所属行业": "中特估", "streak": 3, "changePct": 10.0, "close": 12.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
        {"code": "601190", "name": "中铁装配", "所属行业": "中特估", "streak": 3, "changePct": 10.0, "close": 8.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
        # 命中 power（行业=电力）：1 个首板 + 1 个二连（即最大 2 连板）
        {"code": "601900", "name": "长江电力", "所属行业": "电力", "streak": 2, "changePct": 10.0, "close": 25.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
        {"code": "600027", "name": "华电国际", "所属行业": "电力", "streak": 1, "changePct": 10.0, "close": 6.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
        # 命中半导体/AI 算力（composite 子板）：1 个首板
        {"code": "688256", "name": "寒武纪", "所属行业": "半导体", "streak": 1, "changePct": 20.0, "close": 300.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
        # 不命中任何赛道
        {"code": "000001", "name": "平安银行", "所属行业": "银行", "streak": 1, "changePct": 10.0, "close": 10.0, "amount": 1.0, "turnoverRate": 1.0, "sealAmount": 1.0, "brokenTimes": 0},
    ]
    pool_records = [_pool_record(TRADE_DATE, pool_items)]

    # --- membership snapshot：仅存在成分快照但不能提供行情源（红盘占比诚实缺口） ---
    member_records = [
        {
            "tradeDate": TRADE_DATE,
            "trackId": "power",
            "boardCode": "BK0428",
            "kind": "track-membership-snapshot",
            "source": "TEST",
            "capturedAt": "2026-08-13T15:00:00+08:00",
            "members": ["600900", "600027"],
            "memberCount": 2,
        }
    ]

    return {
        "track-board-close": close_records,
        "track-board-flow": flow_records,
        "limit-up-pool": pool_records,
        "track-membership-snapshot": member_records,
    }


def _patch_archive(monkeypatch, fake):
    def fake_read(kind, **kwargs):
        return fake.get(kind, [])

    monkeypatch.setattr(_archive, "read_records", fake_read)


def _by_id(items, track_id):
    return next(it for it in items if it["trackId"] == track_id)


def test_ma_alignment_and_rps_and_turnover(monkeypatch):
    fake = _build_fake_archive()
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)
    items = result["items"]
    assert len(items) >= 4

    div = _by_id(items, "dividend_cnsoe")
    health = _by_id(items, "healthcare")

    # dividend 强多头排列 → "是"
    assert div["maAlignment"] == "是"
    # healthcare 下跌 → "否"
    assert health["maAlignment"] == "否"

    # dividend 60 日收益最强 → rps60≈100
    assert div["rps60"] is not None
    assert 95.0 <= float(div["rps60"]) <= 100.0
    # dividend 近5日 amount 最大 → turnoverRank=1
    assert div["turnoverRank"] == 1
    # healthcare 下跌且近5日 amount 最小 → turnoverRank 最后
    ranks = [it["turnoverRank"] for it in items if it["turnoverRank"] is not None]
    assert health["turnoverRank"] == max(ranks)
    # rps 数值合法范围
    for it in items:
        if it["rps60"] is not None:
            assert 0 <= float(it["rps60"]) <= 100


def test_inflow_and_continuous_days(monkeypatch):
    fake = _build_fake_archive()
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)
    items = result["items"]

    div = _by_id(items, "dividend_cnsoe")
    power = _by_id(items, "power")
    health = _by_id(items, "healthcare")

    # dividend：D=5 且连续 5 日净流入
    assert div["mainNetInflow"] == 5.0
    assert div["continuousInflowDays"] == 5
    # power：D=8、D-1=2 连续，D-2 中断 → 2 天
    assert power["mainNetInflow"] == 8.0
    assert power["continuousInflowDays"] == 2
    # healthcare：D 净流出 → 0 天（中断日为 0 用例）
    assert health["mainNetInflow"] == -3.0
    assert health["continuousInflowDays"] == 0
    # 非负约束
    for it in items:
        assert it["continuousInflowDays"] is None or it["continuousInflowDays"] >= 0


def test_limit_up_count_and_ladder(monkeypatch):
    fake = _build_fake_archive()
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)
    items = result["items"]

    div = _by_id(items, "dividend_cnsoe")
    power = _by_id(items, "power")
    health = _by_id(items, "healthcare")
    semi = _by_id(items, "semiconductor_ai")

    # dividend：2 只命中，均 3 连板 → count 2、"3连板"
    assert div["limitUpCount"] == 2
    assert div["ladderCompleteness"] == "3连板"
    # power：1 二连 + 1 首板 → count 2、"2连板"
    assert power["limitUpCount"] == 2
    assert power["ladderCompleteness"] == "2连板"
    # healthcare：无命中 → 0、"无连板"
    assert health["limitUpCount"] == 0
    assert health["ladderCompleteness"] == "无连板"
    # semiconductor：1 只命中（首板）→ count 1、"1连板"
    assert semi["limitUpCount"] == 1
    assert semi["ladderCompleteness"] == "1连板"


def test_core_catalyst_nonempty_chinese(monkeypatch):
    fake = _build_fake_archive()
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)
    items = result["items"]
    assert len(items) >= 4
    for it in items:
        assert isinstance(it["coreCatalyst"], str) and len(it["coreCatalyst"]) >= 2
        assert isinstance(it["earningsRealization"], str) and len(it["earningsRealization"]) >= 2
        # 非占位符
        assert not any(
            ph in it["coreCatalyst"] + it["earningsRealization"]
            for ph in ("TODO", "N/A", "待补充", "占位")
        )


def test_module_result_contract_and_validate_snapshot(monkeypatch):
    fake = _build_fake_archive()
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)

    # 模块级字段齐全
    assert result["status"] == ModuleStatus.PARTIAL.value
    assert result["dataDate"] == TRADE_DATE
    assert result["configVersion"] == "2.0"
    assert result["effectiveFrom"] == "2026-07-01"
    assert result["effectiveTo"] == "2026-12-31"
    assert result["sourceSystem"] == "SELF"
    assert result["decision"] == "TRACKS_SUFFICIENT"
    assert 80.0 <= result["coveragePct"] <= 100.0

    items = result["items"]
    assert len(items) >= 4
    for it in items:
        assert it["date"] == TRADE_DATE
        # 每条赛道 items 字段 typed 契约
        assert it["trackId"] and isinstance(it["trackId"], str)
        assert it["trackName"] and isinstance(it["trackName"], str)
        assert it["positioning"] and isinstance(it["positioning"], str)
        assert isinstance(it["turnoverRank"], int) and it["turnoverRank"] >= 1
        assert isinstance(it["mainNetInflow"], (int, float))
        assert isinstance(it["continuousInflowDays"], int) and it["continuousInflowDays"] >= 0
        assert it["maAlignment"] in ("是", "否", None)
        assert it["rps60"] is None or (0 <= float(it["rps60"]) <= 100)
        assert isinstance(it["limitUpCount"], int) and it["limitUpCount"] >= 0
        assert isinstance(it["ladderCompleteness"], str) and len(it["ladderCompleteness"]) >= 1
        assert it["redStockRatio"] is None  # 本轮诚实缺口
        assert isinstance(it["score"], (int, float)) and 0 <= float(it["score"]) <= 100
        assert it["decision"] in {"核心防御主线", "次主线", "主跌浪", "退潮主线", "观察", "达标", "规避", "数据不足"}

    # 放入最小快照（其他模块 UNAVAILABLE），validate_snapshot 不抛
    from collector.validators.schema import validate_snapshot

    snapshot = new_snapshot(TRADE_DATE)
    for name in (
        "marketIndex",
        "turnover",
        "sentiment",
        "sectorPerformance",
        "fundFlow",
        "northbound",
        "margin",
        "summary",
    ):
        snapshot["modules"][name] = {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": TRADE_DATE,
            "source": ["TEST"],
            "name": name,
        }
    snapshot["modules"]["tracks"] = result
    finalize_snapshot(snapshot)
    validate_snapshot(snapshot)
