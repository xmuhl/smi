# -*- coding: utf-8 -*-
"""accept.py(v2验收器) 的 pytest 测试套件。

以 07-17 参考日真实快照 web/public/data/daily/2026/2026-07-17.json 为底
(deepcopy 逐一变异)，覆盖 9 模块 18 个负向用例 + 2 个正向用例。
只读验收器/标准/数据，不修改任何既有产出文件。
"""
import copy
import json
import os
import sys

import pytest

# 运行目录必须在 smi 项目根（accept.py 读取 docs/acceptance/... 相对路径）。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ACCEPT_DIR = _HERE  # tools/acceptance
sys.path.insert(0, _ACCEPT_DIR)
sys.path.insert(0, os.path.dirname(_HERE))

import accept  # noqa: E402  (验收器 v2，已存在，只读)

BASE_DATE = "2026-07-17"  # referenceDate

_STD = None


@pytest.fixture(scope="session")
def standard():
    global _STD
    if _STD is None:
        std = accept.load_standard()
        errors = accept.startup_self_check(std)
        assert not errors, f"startup_self_check 应有 0 错误: {errors}"
        _STD = std
    return _STD


@pytest.fixture(scope="session")
def manifest():
    with open(os.path.join("web", "public", "data", "manifest.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def base_snapshot():
    with open(os.path.join("web", "public", "data", "daily", "2026", f"{BASE_DATE}.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _assert_neg(base_snapshot, standard, manifest, module, mutate, keyword, trade_date=BASE_DATE):
    """deepcopy 底快照 -> 变异 -> evaluate_modules，断言目标模块 FAIL 且 details 含关键词。"""
    snap = copy.deepcopy(base_snapshot)
    mutate(snap["modules"])
    checks, all_pass, inv = accept.evaluate_modules(snap, standard, trade_date, manifest)
    target = checks[module]
    text = "\n".join(d["detail"] for d in target["details"])
    assert target["pass"] is False, (
        f"模块 {module} 应 FAIL，但实际 PASS。details={text}"
    )
    assert keyword in text, (
        f"模块 {module} 的 details 应包含关键词 {keyword!r}。实际：{text}"
    )


# ---------------------------------------------------------------- 1-3 marketIndex
def test_marketindex_del_000001(base_snapshot, standard, manifest):
    def m(mods):
        mods["marketIndex"]["items"] = [
            i for i in mods["marketIndex"]["items"] if i.get("code") != "000001"
        ]
    _assert_neg(base_snapshot, standard, manifest, "marketIndex", m, "缺失必需 core 指数")


def test_marketindex_duplicate_code(base_snapshot, standard, manifest):
    def m(mods):
        mods["marketIndex"]["items"][1]["code"] = mods["marketIndex"]["items"][0]["code"]
    _assert_neg(base_snapshot, standard, manifest, "marketIndex", m, "重复")


def test_marketindex_close_not_number(base_snapshot, standard, manifest):
    def m(mods):
        mods["marketIndex"]["items"][0]["close"] = "abc"
    _assert_neg(base_snapshot, standard, manifest, "marketIndex", m, "close")


# ---------------------------------------------------------------- 4-6 turnover
def test_turnover_previous_null(base_snapshot, standard, manifest):
    def m(mods):
        mods["turnover"]["turnoverPrevious"] = None
    _assert_neg(base_snapshot, standard, manifest, "turnover", m, "turnoverPrevious")


def test_turnover_delta_wrong(base_snapshot, standard, manifest):
    def m(mods):
        mods["turnover"]["turnoverDelta"] = 999
    _assert_neg(base_snapshot, standard, manifest, "turnover", m, "恒等")


def test_turnover_volume_state_bad(base_snapshot, standard, manifest):
    def m(mods):
        mods["turnover"]["volumeState"] = "XXX"
    _assert_neg(base_snapshot, standard, manifest, "turnover", m, "volumeState")


# ---------------------------------------------------------------- 7-8 sentiment
def test_sentiment_stlimitup_reverted(base_snapshot, standard, manifest):
    def m(mods):
        mods["sentiment"]["stLimitUpCount"] = 25.0
    _assert_neg(base_snapshot, standard, manifest, "sentiment", m, "stLimitUpCount")


def test_sentiment_missing_risecount(base_snapshot, standard, manifest):
    def m(mods):
        del mods["sentiment"]["riseCount"]
    _assert_neg(base_snapshot, standard, manifest, "sentiment", m, "riseCount")


# ---------------------------------------------------------------- 9-11 sectorPerformance
def test_sector_top5_too_few(base_snapshot, standard, manifest):
    def m(mods):
        mods["sectorPerformance"]["industryTop5"] = mods["sectorPerformance"]["industryTop5"][:4]
    _assert_neg(base_snapshot, standard, manifest, "sectorPerformance", m, "minItems")


def test_sector_top5_unsorted(base_snapshot, standard, manifest):
    def m(mods):
        it = mods["sectorPerformance"]["industryTop5"]
        it[0], it[1] = it[1], it[0]
    _assert_neg(base_snapshot, standard, manifest, "sectorPerformance", m, "排序")


def test_sector_top5_duplicate_name(base_snapshot, standard, manifest):
    def m(mods):
        it = mods["sectorPerformance"]["industryTop5"]
        it[1]["name"] = it[0]["name"]
    _assert_neg(base_snapshot, standard, manifest, "sectorPerformance", m, "重复")


# ---------------------------------------------------------------- 12 fundFlow
def test_fundflow_outflow_positive(base_snapshot, standard, manifest):
    def m(mods):
        mods["fundFlow"]["industryOutflowTop10"][0]["netInflowYi"] = 50.0
    _assert_neg(base_snapshot, standard, manifest, "fundFlow", m, "应为负")


# ---------------------------------------------------------------- 13-14 northbound
def test_northbound_mode_invalid(base_snapshot, standard, manifest):
    def m(mods):
        mods["northbound"]["mode"] = "POST_20240819_XX"
    _assert_neg(base_snapshot, standard, manifest, "northbound", m, "mode")


def test_northbound_inflow_reference_mismatch(base_snapshot, standard, manifest):
    def m(mods):
        mods["northbound"]["legacyImportedFields"]["totalNetInflow"] = -1.0
    _assert_neg(base_snapshot, standard, manifest, "northbound", m, "referenceAssertion")


# ---------------------------------------------------------------- 15 margin
def test_margin_balance_breaks_identity(base_snapshot, standard, manifest):
    def m(mods):
        mods["margin"]["marginBalance"] = 1.0
    _assert_neg(base_snapshot, standard, manifest, "margin", m, "恒等")


# ---------------------------------------------------------------- 16 tracks
def test_tracks_missing_score(base_snapshot, standard, manifest):
    def m(mods):
        del mods["tracks"]["items"][0]["score"]
    _assert_neg(base_snapshot, standard, manifest, "tracks", m, "score")


# ---------------------------------------------------------------- 17-18 summary
def test_summary_riskwarning_missing_phrase(base_snapshot, standard, manifest):
    def m(mods):
        mods["summary"]["riskWarning"] = "hello world"
    _assert_neg(base_snapshot, standard, manifest, "summary", m, "不构成投资建议")


def test_summary_sentiment_english_cjk(base_snapshot, standard, manifest):
    """摘要各段在非参考日强制中文占比；07-17 参考日天然豁免该规则，
    因此用非参考日 tradeDate 驱动以命中中文字符占比规则。"""
    def m(mods):
        mods["summary"]["sentiment"] = "same same same same same same same"
    _assert_neg(base_snapshot, standard, manifest, "summary", m, "中文",
                trade_date="2026-07-20")


# ---------------------------------------------------------------- 正向 A/B
def test_positive_0717_all_pass(base_snapshot, standard, manifest):
    entry = accept.build_entry(BASE_DATE, manifest, standard)
    assert entry["overall"] == "PASS", entry["modules"]
    assert entry["pass"] is True
    for name in accept.MODULE_ORDER:
        assert entry["modules"][name]["pass"] is True, name


def test_positive_0814_fail_set(base_snapshot, standard, manifest):
    entry = accept.build_entry("2026-08-14", manifest, standard)
    assert entry["overall"] == "FAIL"
    assert entry["pass"] is False
    fail_mods = {name for name in accept.MODULE_ORDER if not entry["modules"][name]["pass"]}
    # P0.3 起 summary 方向/数值事实锚点使 08-14 旧文案 summary 也 FAIL（P1 重生成文案后恢复）
    assert fail_mods == {"sentiment", "northbound", "summary", "tracks"}, fail_mods
    # margin 走 D0 PENDING 分支 PASS
    assert entry["modules"]["margin"]["pass"] is True
    assert entry["modules"]["summary"]["pass"] is False


# ---------------------------------------------------------------- P0.4 (P03-001) 新增回归
def _official_nb_snapshot():
    """OFFICIAL_REPLACEMENT 合法 northbound 样本（基于 08-14 真实 quarterlyHolding 数据）。"""
    with open(os.path.join("web", "public", "data", "daily", "2026", "2026-08-14.json"), "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    nb = snap["modules"]["northbound"]
    nb["mode"] = "POST_20240819_OFFICIAL_REPLACEMENT"
    nb["sourceSystem"] = "SELF"
    nb["status"] = "FINAL"
    qh = nb["quarterlyHolding"]
    qh["status"] = "FINAL"
    qh["asOf"] = "2026-06-30"
    qh["publishedAt"] = "2026-07-08"
    snap["modules"]["summary"]["northbound"] = (
        "北向资金官方已停止日度净流入披露，不再提供日度数据；"
        "最近官方季度持仓（point-in-time，截至 2026-06-30）见上方模块。"
    )
    return snap


def test_p04_official_nb_positive(standard, manifest):
    """OFFICIAL 合法样本（真实 HKEX 数值形态）必须 PASS。"""
    snap = _official_nb_snapshot()
    checks, all_pass, inv = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    assert checks["northbound"]["pass"] is True, checks["northbound"]["details"]


def test_p04_pct_of_issued_garbage(standard, manifest):
    snap = _official_nb_snapshot()
    snap["modules"]["northbound"]["quarterlyHolding"]["items"][0]["pctOfIssued"] = "dd.dd%"
    checks, _, _ = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    text = "\n".join(d["detail"] for d in checks["northbound"]["details"])
    assert checks["northbound"]["pass"] is False and "百分比" in text, text


def test_p04_shareholding_nan_and_negative(standard, manifest):
    for bad in ("NaN", "Infinity", "-5"):
        snap = _official_nb_snapshot()
        snap["modules"]["northbound"]["quarterlyHolding"]["items"][0]["shareholding"] = bad
        checks, _, _ = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
        text = "\n".join(d["detail"] for d in checks["northbound"]["details"])
        assert checks["northbound"]["pass"] is False and "数值字符串" in text, (bad, text)


def test_p04_asof_garbage_suffix(standard, manifest):
    snap = _official_nb_snapshot()
    snap["modules"]["northbound"]["quarterlyHolding"]["asOf"] = "2026-06-30THIS_IS_NOT_ISO"
    checks, _, _ = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    text = "\n".join(d["detail"] for d in checks["northbound"]["details"])
    assert checks["northbound"]["pass"] is False and "ISO" in text, text


def test_p04_unit_deleted_invariant(standard, manifest):
    """删除 turnover.unit → INV-UNIT-亿元 必须 false（P0-008）。"""
    snap = _official_nb_snapshot()
    del snap["modules"]["turnover"]["unit"]
    _, _, inv = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    assert inv.get("INV-UNIT-亿元") is False, inv


def test_p04_unit_deleted_margin_invariant(standard, manifest):
    """删除 margin.unit → INV-UNIT-亿元 必须 false（P03-001 评审补漏）。"""
    snap = _official_nb_snapshot()
    del snap["modules"]["margin"]["unit"]
    _, _, inv = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    assert inv.get("INV-UNIT-亿元") is False, inv


def test_p04_official_summary_fabricates_daily(standard, manifest):
    """OFFICIAL 分支 summary 虚构『官方日度净流入』必须 FAIL（P0-007）。"""
    snap = _official_nb_snapshot()
    snap["modules"]["summary"]["northbound"] = "北向官方日度净流入 100 亿元，已连续净流入三日。"
    checks, _, _ = accept.evaluate_modules(snap, standard, "2026-08-14", manifest)
    text = "\n".join(d["detail"] for d in checks["summary"]["details"])
    assert checks["summary"]["pass"] is False and "禁词" in text, text


def test_p04_generic_ruleversion_unsupported(standard, manifest):
    """generic 模块 ruleVersion 改为未支持版本 → startup_self_check 报错（P0-002）。"""
    std = copy.deepcopy(standard)
    std["modules"]["marketIndex"]["ruleVersion"] = 999
    errors = accept.startup_self_check(std)
    assert any("marketIndex" in e and "999" in e for e in errors), errors


def test_p04_tracks_effective_from_garbage(base_snapshot, standard, manifest):
    """tracks effectiveFrom/To 不可解析必须 FAIL（P0-006，非参考日触发）。"""
    def m(mods):
        mods["tracks"]["effectiveFrom"] = "garbage"
        mods["tracks"]["effectiveTo"] = "garbage"
    _assert_neg(base_snapshot, standard, manifest, "tracks", m, "effectiveFrom", trade_date="2026-08-13")


def test_p04_recalc_trackid_mismatch(base_snapshot, standard, manifest, monkeypatch):
    """重算 trackId 集合与快照不一致必须 FAIL（P0-006，单元级直接调用 _recalc_tracks）。"""
    items = copy.deepcopy(base_snapshot["modules"]["tracks"]["items"])
    fake = [{"trackId": "高股息_中特估", "score": 90.0, "decision": "核心防御主线"}]
    monkeypatch.setattr("collector.calculators.tracks.score_tracks", lambda items: fake)
    details = []
    accept._recalc_tracks(items, {"meta": {"legacy": False}}, details)
    text = "\n".join(d["detail"] for d in details)
    assert "trackId 集合" in text, text

