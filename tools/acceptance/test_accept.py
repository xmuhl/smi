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
# 仓库根也需在 path 上（函数级 `from collector...` / `from tools...` 导入；
# 本地 `python -m pytest` 由 CWD 掩盖，CI 裸 pytest 会暴露——补齐使自足）
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

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
    # R22 后 08-14 状态：sentiment PARTIAL（缺 limitSealRatePct/涨跌家数）；
    # tracks 重生成为 3.3 空池 UNAVAILABLE（上游无板块快照，fail-closed
    # 契约合法，不再计入违约集）；northbound/summary/margin PASS
    # （P1-009：随实现演进同步断言）。
    assert entry["overall"] == "FAIL"
    assert entry["pass"] is False
    fail_mods = {name for name in accept.MODULE_ORDER if not entry["modules"][name]["pass"]}
    assert fail_mods == {"sentiment"}, fail_mods
    # margin 走 D0 PENDING 分支 PASS
    assert entry["modules"]["margin"]["pass"] is True
    assert entry["modules"]["summary"]["pass"] is True
    assert entry["modules"]["northbound"]["pass"] is True


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



# ---------------------------------------------------------------- R14-P2-01 tracks_V2 v4
TRACKS_V4_DATE = "2026-08-21"


def _v4_formal_item(track_id="power", catalyst="迎峰度夏催化", earnings="业绩兑现稳"):
    return {
        "date": TRACKS_V4_DATE,
        "trackId": track_id,
        "trackName": f"测试板块{track_id}",
        "positioning": "测试定位",
        "turnoverRank": 3,
        "mainNetInflow": 5.2,
        "continuousInflowDays": 2,
        "maAlignment": "是",
        "rps60": 88.0,
        "excessReturn20d": None,
        "limitUpCount": 2,
        "ladderCompleteness": "2连板",
        "redStockRatio": "65%",
        "coreCatalyst": catalyst,
        "earningsRealization": earnings,
        "score": 78.0,
        "decision": "次主线/轮动主线",
        "dataReadiness": "READY",
        "historyDays": 60,
    }


def _v4_warming_item():
    return {
        "date": TRACKS_V4_DATE,
        "trackId": "dyn_BK9999",
        "trackName": "动态预热板块",
        "positioning": "动态候选",
        "turnoverRank": 5,
        "mainNetInflow": 3.0,
        "continuousInflowDays": 1,
        "maAlignment": "否",
        "rps60": 70.0,
        "excessReturn20d": None,
        "limitUpCount": 1,
        "ladderCompleteness": "首板",
        "redStockRatio": "55%",
        "coreCatalyst": "",
        "earningsRealization": "",
        "score": None,
        "decision": "数据不足",
        "dataReadiness": "WARMING_UP",
        "historyDays": 3,
    }


def _v4_module(**overrides):
    mod = {
        "status": "PARTIAL",
        "dataDate": TRACKS_V4_DATE,
        "configVersion": "3.3",
        "effectiveFrom": "2026-07-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_SUFFICIENT",
        "dataReadiness": "READY",
        "coveragePct": 82.4,
        "coverageTargetPct": 80.0,
        "coverageHardFloorPct": 65.0,
        "warmingUpBoards": [],
        "items": [
            _v4_formal_item("power"),
            _v4_formal_item("dividend"),
            _v4_formal_item("healthcare"),
            _v4_formal_item("semiconductor"),
            _v4_warming_item(),
        ],
    }
    mod.update(overrides)
    return mod


def _run_tracks_v4(mod, standard):
    snap = {"tradeDate": TRACKS_V4_DATE, "modules": {"tracks": mod}}
    res = accept.check_tracks(snap, standard, trade_date=TRACKS_V4_DATE)
    text = "\n".join(d["detail"] for d in res["details"])
    return res["pass"], text


def test_tracks_v4_partial_sufficient_positive(standard):
    """v4 正例：PARTIAL + TRACKS_SUFFICIENT（coverage≥target）必须 PASS。"""
    ok, text = _run_tracks_v4(_v4_module(), standard)
    assert ok, f"应 PASS 但实际 FAIL：{text}"


def test_tracks_v4_partial_degraded_positive(standard):
    """v4 正例：PARTIAL + TRACKS_DEGRADED（coverage∈[floor,target)）必须 PASS。"""
    mod = _v4_module(decision="TRACKS_DEGRADED", dataReadiness="DEGRADED",
                     coveragePct=70.0)
    ok, text = _run_tracks_v4(mod, standard)
    assert ok, f"应 PASS 但实际 FAIL：{text}"


def test_tracks_v4_sufficient_below_target_rejected(standard):
    ok, text = _run_tracks_v4(_v4_module(coveragePct=70.0), standard)
    assert not ok and "TRACKS_SUFFICIENT 要求 coverage" in text


def test_tracks_v4_degraded_above_target_rejected(standard):
    mod = _v4_module(decision="TRACKS_DEGRADED", dataReadiness="DEGRADED",
                     coveragePct=85.0)
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "TRACKS_DEGRADED 要求 coverage" in text


def test_tracks_v4_unavailable_requires_insufficient(standard):
    mod = _v4_module(status="UNAVAILABLE", decision="TRACKS_SUFFICIENT")
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "UNAVAILABLE 仅允许 TRACKS_INSUFFICIENT" in text


def test_tracks_v4_unavailable_insufficient_positive(standard):
    """v4 正例：UNAVAILABLE + TRACKS_INSUFFICIENT（items 信息性）必须 PASS。"""
    mod = _v4_module(status="UNAVAILABLE", decision="TRACKS_INSUFFICIENT",
                     dataReadiness="FAILED", coveragePct=40.0, items=[])
    ok, text = _run_tracks_v4(mod, standard)
    assert ok, f"应 PASS 但实际 FAIL：{text}"


def test_tracks_v4_readiness_mismatch_rejected(standard):
    mod = _v4_module(dataReadiness="DEGRADED")  # decision 仍 SUFFICIENT
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "不一致" in text


def test_tracks_v4_warming_mature_score_rejected(standard):
    """WARMING_UP 项输出成熟 score → FAIL（R14 §5.3 契约）。"""
    mod = _v4_module()
    warming = mod["items"][-1]
    warming["score"] = 66.6
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "不得输出成熟 score" in text


def test_tracks_v4_formal_items_floor(standard):
    """正式项 <4（预热不计数）→ FAIL。"""
    mod = _v4_module(items=[
        _v4_formal_item("power"),
        _v4_formal_item("dividend"),
        _v4_formal_item("healthcare"),
        _v4_warming_item(),
    ])
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "正式评分项" in text


def test_tracks_v4_seed_catalyst_required(standard):
    """非动态项定性列必填；动态项允许留白（dyn_ 前缀）。"""
    mod = _v4_module()
    mod["items"][0] = _v4_formal_item("power", catalyst="")
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "必填非空" in text
    # 动态项留白在正例中已覆盖（_v4_warming_item catalyst/earnings 为空）

# ------------------------------------------------- R15 评审阻断点 A~F 负向回归
def test_tracks_v4_partial_insufficient_rejected(standard):
    """阻断点 A：PARTIAL + TRACKS_INSUFFICIENT 必须FAIL（该 decision 仅属 UNAVAILABLE）。"""
    mod = _v4_module(decision="TRACKS_INSUFFICIENT", dataReadiness="FAILED",
                     coveragePct=40.0)
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "PARTIAL 不允许 TRACKS_INSUFFICIENT" in text


def test_tracks_v4_unavailable_missing_decision_rejected(standard):
    """阻断点 B：UNAVAILABLE + decision=null 必须 FAIL。"""
    mod = _v4_module(status="UNAVAILABLE", decision=None, items=[])
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "必须携带模块级 decision" in text


def test_tracks_v4_unavailable_legacy_decision_rejected(standard):
    """阻断点 B：UNAVAILABLE + 旧枚举 'INSUFFICIENT'（非 TRACKS_ 前缀）必须 FAIL。"""
    mod = _v4_module(status="UNAVAILABLE", decision="INSUFFICIENT", items=[])
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "不在契约枚举" in text


def test_tracks_v4_final_below_target_rejected(standard):
    """阻断点 C：FINAL + TRACKS_SUFFICIENT 但 coverage<target 必须 FAIL。"""
    mod = _v4_module(status="FINAL", coveragePct=79.9)
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "FINAL/TRACKS_SUFFICIENT 要求 coverage" in text


def test_tracks_v4_final_coverage_missing_rejected(standard):
    """阻断点 C：FINAL + coverage 缺失必须 FAIL。"""
    mod = _v4_module(status="FINAL", coveragePct=None)
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "FINAL/TRACKS_SUFFICIENT 要求 coverage" in text


def test_tracks_v4_insufficient_items_not_formal(standard):
    """阻断点 E：INSUFFICIENT readiness 项不得充当正式评分项（minFormalItems）。"""
    def insuff(tid):
        it = _v4_formal_item(tid)
        it["dataReadiness"] = "INSUFFICIENT"
        it["score"] = None
        it["decision"] = "数据不足"
        it["decisionCode"] = "INSUFFICIENT"
        return it
    mod = _v4_module(items=[insuff(t) for t in ("power", "dividend", "healthcare", "semiconductor")])
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "正式评分项" in text and "0 < 4" in text


def test_tracks_v4_warming_coverage_pct_rejected(standard):
    """阻断点 F：WARMING_UP 项 coveragePct 非 null 必须 FAIL。"""
    mod = _v4_module()
    mod["items"][-1]["coveragePct"] = 50.0
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "coveragePct 必须为 null" in text


def test_tracks_v4_warming_dimension_pass_rejected(standard):
    """阻断点 F：WARMING_UP 项 dimensionPass 非 null 必须 FAIL。"""
    mod = _v4_module()
    mod["items"][-1]["dimensionPass"] = {"capital": None}
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "dimensionPass 必须为 null" in text


def test_tracks_v4_strict_missing_readiness_rejected(standard):
    """阻断点 D：configVersion>=3.2 必须携带模块级 dataReadiness。"""
    mod = _v4_module()
    del mod["dataReadiness"]
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "必须携带模块级 dataReadiness" in text


def test_tracks_v4_strict_threshold_field_mismatch_rejected(standard):
    """阻断点 D：coverageTargetPct 缺失/与 decisionContract 不一致必须 FAIL。"""
    mod = _v4_module()
    del mod["coverageTargetPct"]
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "必须携带有限 coverageTargetPct" in text

    mod2 = _v4_module(coverageTargetPct=90.0)
    ok2, text2 = _run_tracks_v4(mod2, standard)
    assert not ok2 and "与 decisionContract(80.0) 不一致" in text2


def _run_tracks_v4_dated(mod, standard, trade_date):
    snap = {"tradeDate": trade_date, "modules": {"tracks": mod}}
    res = accept.check_tracks(snap, standard, trade_date=trade_date)
    text = "\n".join(d["detail"] for d in res["details"])
    return res["pass"], text


def test_tracks_v4_legacy_30_shape_still_passes(standard):
    """阻断点 G 正例：真实 2026-08-20 的 3.0 存量形态（无 dataReadiness/
    阈值透传字段）经显式版本分支 + 权威版本表合法通过。"""
    mod = {
        "status": "UNAVAILABLE",
        "dataDate": "2026-08-20",
        "configVersion": "3.0",
        "effectiveFrom": "2026-08-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_INSUFFICIENT",
        "coveragePct": 71.4,
        "items": [],
    }
    ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-20")
    assert ok, f"3.0 存量形态（2026-08-20）应 PASS：{text}"


def test_tracks_v4_version_schedule_blocks_future_downgrade(standard):
    """R16-P2-01 负向：cutoff（2026-08-21）之后的新交易日自报 3.0 必须 FAIL。

    configVersion 是被验收事实，不得作为验收强度的可信依据（自证循环）；
    未来快照版本回退（旧 worker/错误常量）不再能伪装成"历史兼容"。
    """
    mod = {
        "status": "UNAVAILABLE",
        "dataDate": "2026-08-24",
        "configVersion": "3.0",
        "effectiveFrom": "2026-08-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_INSUFFICIENT",
        "coveragePct": 71.4,
        "items": [],
    }
    ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-24")
    assert not ok and "权威下限" in text and "版本降级旁路" in text, text


def test_tracks_v4_version_schedule_unknown_legacy_version_in_window(standard):
    """R16-P2-01 边界：cutoff 之前的非数值版本（如误报）不在权威版本表
    allowedConfigVersions 内必须 FAIL（时间表是白名单不是自由放行）。"""
    mod = {
        "status": "UNAVAILABLE",
        "dataDate": "2026-08-19",
        "configVersion": "9.9",
        "effectiveFrom": "2026-08-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_INSUFFICIENT",
        "coveragePct": 71.4,
        "items": [],
    }
    ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-19")
    assert not ok and "权威版本表" in text, text


def test_tracks_v4_version_schedule_future_nonnumeric_rejected(standard):
    """R17-P2-01 负向：cutoff 后自报 "legacy"（非数值）必须 FAIL。

    旧实现解析失败后静默 pass（依赖不存在的白名单兜底）→ fail-open
    版本降级旁路：future+3.0 FAIL 但 future+legacy PASS。
    """
    mod = {
        "status": "UNAVAILABLE",
        "dataDate": "2026-08-24",
        "configVersion": "legacy",
        "effectiveFrom": "2026-08-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_INSUFFICIENT",
        "coveragePct": 71.4,
        "items": [],
    }
    ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-24")
    assert not ok and "非规范 x.y 数值版本" in text, text


def test_tracks_v4_version_schedule_future_malformed_rejected(standard):
    """R17-P2-01 负向：cutoff 后自报 "3.x"（损坏值）必须 FAIL。"""
    mod = {
        "status": "UNAVAILABLE",
        "dataDate": "2026-08-24",
        "configVersion": "3.x",
        "effectiveFrom": "2026-08-20",
        "effectiveTo": "2026-12-31",
        "sourceSystem": "THS_UNIVERSE",
        "decision": "TRACKS_INSUFFICIENT",
        "coveragePct": 71.4,
        "items": [],
    }
    ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-24")
    assert not ok and "非规范 x.y 数值版本" in text, text


def test_tracks_v4_version_schedule_malformed_versions_rejected(standard):
    """R18：cutoff 后多段/尾点/单段/尾空白/空串版本一律 FAIL（严格解析器）。"""
    for bad in ("3.2.1", "3.2.", "4", "3.2 ", " 3.2", "03.02", ""):
        mod = {
            "status": "UNAVAILABLE",
            "dataDate": "2026-08-24",
            "configVersion": bad,
            "effectiveFrom": "2026-08-20",
            "effectiveTo": "2026-12-31",
            "sourceSystem": "THS_UNIVERSE",
            "decision": "TRACKS_INSUFFICIENT",
            "coveragePct": 71.4,
            "items": [],
        }
        ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-24")
        assert not ok, f"configVersion={bad!r} 应 FAIL：{text}"
        if bad == "":
            # 空串同时命中 configVersion 缺失类 gap；其余形态必有版本 gap
            continue
        assert "非规范 x.y 数值版本" in text or "权威下限" in text, \
            f"configVersion={bad!r} 缺版本 gap：{text}"


def test_tracks_v4_version_schedule_future_40_passes(standard):
    """R18：cutoff 后合法新版本（4.0，规范 x.y 且 >=3.2）+ 完整 strict 字段 → PASS。"""
    mod = _v4_module(configVersion="4.0")
    ok, text = _run_tracks_v4(mod, standard)
    assert ok, f"4.0 应 PASS：{text}"


def test_strict_version_parser_matrix():
    """R19：唯一解析器的完整形态矩阵（ASCII 规范串 <=> 唯一版本元组）。

    fullmatch（非行尾锚，"3.2\n" 拒绝）+ [0-9]（非 Unicode 数字类，
    全角/阿拉伯-印度数字拒绝）+ 段长<=9（超长拒绝）。R19 §9/§10 全表。
    """
    from tools.acceptance.accept import _parse_strict_version as pv

    for s, want in {
        "0.0": (0, 0), "3.2": (3, 2), "4.0": (4, 0),
        "32.2": (32, 2), "1.0": (1, 0), "2.0": (2, 0),
    }.items():
        assert pv(s) == want, s
    for s in (
        "03.02", "3.02", "3", "3.", "3.2.1", "3.2.", "3.2x",
        "3.2 ", " 3.2", "3.2\n", "3２.2", "3٢.2",   # 全角２/阿拉伯-印度٢
        "legacy", "", "1234567890.0", None, 3.2,
    ):
        assert pv(s) is None, s


def test_tracks_v4_version_schedule_unicode_and_newline_rejected(standard):
    """R19 集成回归：cutoff 后 "3.2\n"（尾部换行）与 "3２.2"（全角数字）
    必须 FAIL（旧行尾锚 + Unicode 数字类曾放过这两种形态）。"""
    for bad in ("3.2\n", "3２.2", "3٢.2", "1234567890.0"):
        mod = {
            "status": "UNAVAILABLE",
            "dataDate": "2026-08-24",
            "configVersion": bad,
            "effectiveFrom": "2026-08-20",
            "effectiveTo": "2026-12-31",
            "sourceSystem": "THS_UNIVERSE",
            "decision": "TRACKS_INSUFFICIENT",
            "coveragePct": 71.4,
            "items": [],
        }
        ok, text = _run_tracks_v4_dated(mod, standard, "2026-08-24")
        assert not ok, f"configVersion={bad!r} 应 FAIL：{text}"
        assert "非规范 x.y 数值版本" in text or "权威下限" in text, \
            f"configVersion={bad!r} 缺版本 gap：{text}"


def test_tracks_v4_warming_boards_string_array_passes(standard):
    """warmingUpBoards 是板块名字符串数组（生产 3.2 实际输出形态）：
    非空清单必须 PASS；旧数组校验无条件要求 dict 元素会误判 FAIL。"""
    mod = _v4_module(warmingUpBoards=["银行", "煤炭"])
    ok, text = _run_tracks_v4(mod, standard)
    assert ok, f"warmingUpBoards 字符串数组应 PASS：{text}"


def test_tracks_v4_warming_boards_bad_element_rejected(standard):
    """warmingUpBoards 元素必须是非空字符串：空串/非字符串元素 FAIL。"""
    mod = _v4_module(warmingUpBoards=["银行", ""])
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "非非空字符串" in text, text
    mod2 = _v4_module(warmingUpBoards=["银行", 42])
    ok2, text2 = _run_tracks_v4(mod2, standard)
    assert not ok2 and "非非空字符串" in text2, text2


def test_tracks_v4_insufficient_item_missing_ratio_passes(standard):
    """INSUFFICIENT（数据不足）项缺 redStockRatio 合法（诚实缺口）：
    生产 2026-08-21 真实 3.2 输出暴露——旧标准把 redStockRatio 声明为
    无条件必填，数据不足项被误判 FAIL。"""
    def insuff(tid):
        it = _v4_formal_item(tid)
        it["dataReadiness"] = "INSUFFICIENT"
        it["score"] = None
        it["decision"] = "数据不足"
        it["redStockRatio"] = None
        return it
    mod = _v4_module(items=[
        _v4_formal_item("power"),
        _v4_formal_item("dividend"),
        _v4_formal_item("healthcare"),
        _v4_formal_item("semiconductor"),
        insuff("dyncand"),
    ])
    ok, text = _run_tracks_v4(mod, standard)
    assert ok, f"INSUFFICIENT 项缺 redStockRatio 应 PASS：{text}"


def test_tracks_v4_formal_item_missing_ratio_rejected(standard):
    """正式项（READY）缺 redStockRatio 必须 FAIL（条件必填）。"""
    mod = _v4_module()
    mod["items"][0]["redStockRatio"] = None
    ok, text = _run_tracks_v4(mod, standard)
    assert not ok and "redStockRatio 必填" in text, text
