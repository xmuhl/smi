"""历史回补分支测试：THS 板块历史指数 → 历史交易日行业/概念 TOP5/BOTTOM5。

用 monkeypatch 打 akshare（不依赖网络），覆盖：
- 行业/概念全部板块 D 日涨跌幅排序与计算（changePct = 收盘环比）；
- 某板块缺 D 日数据 → 该板块被跳过、其余正常；
- 历史拉取抛异常 → fail-closed UNAVAILABLE + reason=THS_HISTORICAL_FETCH_FAILED；
- 行业侧全失败 → 整体 UNAVAILABLE、不伪造 FINAL；
- 完整模块结果通过 collector.validators.schema.validate_snapshot 契约校验。
"""

from __future__ import annotations

import akshare
import pandas as pd

from collector.modules.sectors import (
    THS_HISTORICAL_METHOD,
    _board_close_change_pct,
    collect_sectors,
)


def _index_df(dates, closes):
    """构造 THS 板块历史指数 DataFrame（列：日期/收盘价）。"""
    return pd.DataFrame(
        {
            "日期": list(dates),
            "收盘价": list(closes),
        }
    )


def _name_df(names):
    return pd.DataFrame({"name": list(names)})


def _patch_ths(
    monkeypatch,
    *,
    industry_names,
    industry_indices,
    concept_names,
    concept_indices,
):
    """把真正的 THS 板块接口替换为离线假实现（按 symbol 分发）。"""
    monkeypatch.setattr(
        akshare,
        "stock_board_industry_name_ths",
        lambda: _name_df(industry_names),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_name_ths",
        lambda: _name_df(concept_names),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_industry_index_ths",
        lambda symbol=None, start_date="", end_date="": industry_indices[symbol],
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_index_ths",
        lambda symbol=None, start_date="", end_date="": concept_indices[symbol],
    )


def test_historical_industry_and_concept_rankings(monkeypatch):
    """3 只行业 + 2 只概念：验证排序、changePct 计算与条目结构。"""
    _patch_ths(
        monkeypatch,
        industry_names=["行业丙", "行业甲", "行业乙"],
        industry_indices={
            # close(2026-08-13)=110, close(2026-08-12)=100 -> +10.0
            "行业甲": _index_df(["2026-08-12", "2026-08-13"], [100, 110]),
            # -> -10.0
            "行业乙": _index_df(["2026-08-12", "2026-08-13"], [100, 90]),
            # -> +5.0
            "行业丙": _index_df(["2026-08-12", "2026-08-13"], [200, 210]),
        },
        concept_names=["概念Y", "概念X"],
        concept_indices={
            "概念X": _index_df(["2026-08-12", "2026-08-13"], [100, 110]),
            "概念Y": _index_df(["2026-08-12", "2026-08-13"], [100, 80]),
        },
    )

    result = collect_sectors("2026-08-13")

    assert result["status"] == "FINAL"
    assert result["dataDate"] == "2026-08-13"
    assert result["method"] == THS_HISTORICAL_METHOD
    assert result["source"] == ["THS"]

    # 行业涨幅前5：甲(+10) > 丙(+5) > 乙(-10)
    industry_names = [e["name"] for e in result["industryTop5"]]
    assert industry_names == ["行业甲", "行业丙", "行业乙"]
    assert result["industryTop5"][0]["changePct"] == 10.0
    assert result["industryTop5"][1]["changePct"] == 5.0
    assert result["industryTop5"][2]["changePct"] == -10.0

    # 行业跌幅前5：乙(-10) < 丙(+5) < 甲(+10)
    bottom_names = [e["name"] for e in result["industryBottom5"]]
    assert bottom_names == ["行业乙", "行业丙", "行业甲"]
    assert result["industryBottom5"][0]["changePct"] == -10.0

    # 概念榜
    concept_names = [e["name"] for e in result["conceptTop5"]]
    assert concept_names == ["概念X", "概念Y"]
    assert result["conceptTop5"][0]["changePct"] == 10.0
    assert result["conceptBottom5"][0]["name"] == "概念Y"
    assert result["conceptBottom5"][0]["changePct"] == -20.0

    # 条目结构：含 name / changePct
    for entry in result["industryTop5"] + result["conceptTop5"]:
        assert "name" in entry
        assert "changePct" in entry


def test_historical_industry_skips_board_missing_d(monkeypatch):
    """某行业板块缺 D 日数据 → 该板块被跳过，其余板块正常入榜。"""
    _patch_ths(
        monkeypatch,
        industry_names=["行业甲", "行业丁", "行业丙"],
        industry_indices={
            "行业甲": _index_df(["2026-08-12", "2026-08-13"], [100, 110]),
            # 缺 2026-08-13：无法定位 D -> 跳过
            "行业丁": _index_df(["2026-08-08", "2026-08-12"], [100, 90]),
            "行业丙": _index_df(["2026-08-12", "2026-08-13"], [200, 210]),
        },
        concept_names=["概念X"],
        concept_indices={
            "概念X": _index_df(["2026-08-12", "2026-08-13"], [100, 200]),
        },
    )

    result = collect_sectors("2026-08-13")

    assert result["status"] == "FINAL"
    ranked_names = [
        e["name"]
        for e in result["industryTop5"] + result["industryBottom5"]
    ]
    assert "行业丁" not in ranked_names
    assert "行业甲" in ranked_names
    assert "行业丙" in ranked_names


def test_historical_fetch_exception_fails_closed(monkeypatch):
    """指数接口抛异常（模拟网络/封锁）→ UNAVAILABLE + THS_HISTORICAL_FETCH_FAILED。"""
    def boom(symbol=None, start_date="", end_date=""):
        del symbol, start_date, end_date
        raise RuntimeError("push2ex unreachable")

    monkeypatch.setattr(
        akshare,
        "stock_board_industry_name_ths",
        lambda: _name_df(["行业甲"]),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_industry_index_ths",
        boom,
    )
    # 概念侧同样打补丁为失败：不 patch 会触发真实网络请求导致测试挂起
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_name_ths",
        lambda: _name_df(["概念X"]),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_index_ths",
        boom,
    )

    result = collect_sectors("2026-08-13")

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"].startswith("THS_HISTORICAL_")
    assert result["industryTop5"] == []
    assert result["conceptTop5"] == []
    # 实现约定：双侧全失败 → THS_HISTORICAL_UNAVAILABLE；失败明细记入 sourceWarnings
    assert any(
        "FETCH_FAILED" in (err or "")
        for err in result.get("sourceWarnings") or []
    )


def test_historical_side_empty_stays_unavailable(monkeypatch):
    """行业侧板块名单为空（全失败）→ 整体 UNAVAILABLE，不伪造 FINAL。"""
    monkeypatch.setattr(
        akshare,
        "stock_board_industry_name_ths",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_name_ths",
        lambda: _name_df(["概念X"]),
    )
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_index_ths",
        lambda symbol=None, start_date="", end_date="": _index_df(
            ["2026-08-12", "2026-08-13"], [100, 110]
        ),
    )

    result = collect_sectors("2026-08-13")

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "THS_HISTORICAL_UNAVAILABLE"
    assert result["conceptTop5"] == []


def test_board_close_change_pct_direct():
    """直接校验 _board_close_change_pct 计算口径。"""
    df = _index_df(["2026-08-12", "2026-08-13"], [100.0, 110.0])
    assert _board_close_change_pct(df, "2026-08-13") == 10.0

    # 缺 D
    assert (
        _board_close_change_pct(
            _index_df(["2026-08-12"], [100.0]),
            "2026-08-13",
        )
        is None
    )

    # 只有一行，无法取前日
    assert (
        _board_close_change_pct(
            _index_df(["2026-08-13"], [100.0]),
            "2026-08-13",
        )
        is None
    )

    # 空 DataFrame
    assert (
        _board_close_change_pct(
            pd.DataFrame(columns=["日期", "收盘价"]),
            "2026-08-13",
        )
        is None
    )


def test_historical_result_validates_against_schema(monkeypatch):
    """完整模块结果放入最小快照，须通过 validate_snapshot 的 sectorPerformance 契约。"""
    from collector.schema import finalize_snapshot, new_snapshot
    from collector.validators.schema import validate_snapshot

    _patch_ths(
        monkeypatch,
        industry_names=["行业甲", "行业乙"],
        industry_indices={
            "行业甲": _index_df(["2026-08-12", "2026-08-13"], [100, 110]),
            "行业乙": _index_df(["2026-08-12", "2026-08-13"], [100, 90]),
        },
        concept_names=["概念X"],
        concept_indices={
            "概念X": _index_df(["2026-08-12", "2026-08-13"], [100, 200]),
        },
    )

    module = collect_sectors("2026-08-13")

    assert module["status"] == "FINAL"

    snapshot = new_snapshot("2026-08-13")
    for name, mod in snapshot["modules"].items():
        mod["status"] = "UNAVAILABLE"
        mod["dataDate"] = "2026-08-13"

    snapshot["modules"]["sectorPerformance"] = module
    finalize_snapshot(snapshot)

    # 契约校验：FINAL sectorPerformance dataDate==tradeDate，不抛异常
    validate_snapshot(snapshot)
