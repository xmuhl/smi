"""综合总结生成器事实锚点测试（零联网，纯函数级断言）。

验证 collector/calculators/summary.generate_summary 的逐段文案满足
验收器 tools/acceptance/accept.py 的 summaryFacts 锚点门禁：
- COMPARABLE 成交额 -> marketEnvironment 含三整数锚 + 量能词，无禁词；
- PREVIOUS_METHOD_MISMATCH -> 含"跨口径"且不冒充同口径；
- margin PENDING / FINAL(方向词) 与待披露词；
- northbound legacy(净流出) 与 OFFICIAL(停发/季度组合、禁词)；
- tracks FINAL 4 赛道 -> trackConclusion 全前 2 字子串 + 判定字符串；
- 8 段 minChars>=10、CJK>=0.5、无 rejectedPlaceholders；riskWarning 含固定句。
"""

from collector.calculators.summary import generate_summary

REJECTED = [
    "暂无",
    "待补",
    "占位",
    "TBD",
    "N/A",
    "nan",
    "null",
    "（无）",
    "None",
    "无数据",
    "未知",
]


def _cjk_ratio(text):
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    denom = cjk + latin
    return cjk / denom if denom else 0.0


def _summary(modules):
    """生成综合总结并直接返回其模块 dict（generate_summary 的返回即 summary 模块）。"""
    return generate_summary(
        {"tradeDate": "2026-08-20", "modules": modules}
    )


def _assert_segment(segment, name="segment"):
    assert isinstance(segment, str) and segment.strip()
    assert len(segment.strip()) >= 10, f"{name} minChars<10: {segment!r}"
    assert _cjk_ratio(segment.strip()) >= 0.5, f"{name} CJK<0.5: {segment!r}"
    for word in REJECTED:
        assert word not in segment, f"{name} 含占位词 {word!r}: {segment!r}"


def _base_modules():
    return {
        "marketIndex": {
            "status": "FINAL",
            "items": [
                {"name": "上证指数", "changePct": 1.2},
                {"name": "创业板指", "changePct": 0.8},
                {"name": "沪深300", "changePct": 0.5},
            ],
        },
        "sentiment": {
            "status": "FINAL",
            "riseCount": 2800,
            "fallCount": 2200,
            "nonStLimitUpCount": 45,
        },
        "fundFlow": {
            "status": "FINAL",
            "industryInflowTop10": [
                {"name": "通信设备"},
                {"name": "半导体"},
                {"name": "证券"},
            ],
            "industryOutflowTop10": [
                {"name": "电力"},
                {"name": "医药"},
            ],
        },
        "margin": {
            "status": "FINAL",
            "marginBalance": 27000.0,
            "marginBalanceChange": 120.0,
        },
        "tracks": {
            "status": "FINAL",
            "items": [
                {"trackName": "高股息中特估", "decision": "PASS"},
                {"trackName": "电力", "decision": "WATCH"},
                {"trackName": "医药生物", "decision": "AVOID"},
                {"trackName": "半导体/AI算力", "decision": "PASS"},
            ],
        },
        "turnover": {
            "status": "FINAL",
            "turnoverToday": 21422.77,
            "turnoverPrevious": 25538.2,
            "turnoverDelta": -4115.43,
            "turnoverChangePct": -16.11,
            "volumeState": "CONTRACTION",
            "comparisonStatus": "COMPARABLE",
        },
        "northbound": {
            "status": "FINAL",
            "mode": "POST_20240819_OFFICIAL_REPLACEMENT",
            "quarterlyHolding": {
                "status": "FINAL",
                "asOf": "2026-06-30",
                "publishedAt": "2026-07-07",
                "items": [],
            },
        },
    }


def test_market_environment_comparable_anchors():
    """COMPARABLE：marketEnvironment 含三整数锚 + 量能词，不含禁词。"""
    modules = _base_modules()
    to = modules["turnover"]
    me = _summary(modules)["marketEnvironment"]

    assert str(int(to["turnoverToday"])) in me
    assert str(int(to["turnoverPrevious"])) in me
    assert str(int(abs(to["turnoverDelta"]))) in me
    assert "缩量" in me  # CONTRACTION -> 缩量

    for w in ["暂无", "无可比较", "暂无可比较", "不可比", "无上一交易日"]:
        assert w not in me
    _assert_segment(me, "marketEnvironment")


def test_market_environment_mismatch():
    """PREVIOUS_METHOD_MISMATCH：含"跨口径"，且不得冒充同口径。"""
    modules = _base_modules()
    modules["turnover"] = {
        "status": "FINAL",
        "turnoverToday": 27037.72,
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
        "method": "SH_SZ_A_EXCLUDE_B",
        "comparisonStatus": "PREVIOUS_METHOD_MISMATCH",
    }
    me = _summary(modules)["marketEnvironment"]

    assert "跨口径" in me
    for w in ["无可比较", "暂无可比较"]:
        assert w not in me
    _assert_segment(me, "marketEnvironment")


def test_market_environment_previous_unavailable_allows_placeholder():
    """PREVIOUS_UNAVAILABLE：允许"暂无"承接（非 COMPARABLE 分支）。"""
    modules = _base_modules()
    modules["turnover"] = {
        "status": "FINAL",
        "turnoverToday": 25000.0,
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
        "comparisonStatus": "PREVIOUS_UNAVAILABLE",
    }
    me = _summary(modules)["marketEnvironment"]
    assert "暂无" in me
    # 非 COMPARABLE 分支允许"暂无"，此处仅校验 minChars/CJK
    assert len(me.strip()) >= 10
    assert _cjk_ratio(me.strip()) >= 0.5


def test_margin_pending_words():
    """margin PENDING：含待披露 / T+1 词（并展示参考余额）。"""
    modules = _base_modules()
    modules["margin"] = {
        "status": "PENDING",
        "latestPublishedReference": {
            "dataDate": "2026-08-19",
            "marginBalance": 26673.45,
        },
    }
    mseg = _summary(modules)["margin"]
    assert any(
        w in mseg
        for w in ["待披露", "待次日", "暂缺", "参考", "T+1"]
    )
    assert "2026-08-19" in mseg
    assert "26673.45" in mseg
    _assert_segment(mseg, "margin")


def test_margin_final_negative_change_word():
    """margin FINAL 且 marginBalanceChange<0：含下降方向词。"""
    modules = _base_modules()
    modules["margin"] = {
        "status": "FINAL",
        "marginBalance": 26000.0,
        "marginBalanceChange": -1046.4,
    }
    mseg = _summary(modules)["margin"]
    assert any(
        w in mseg
        for w in ["减少", "下降", "回落", "减仓", "净偿还"]
    )
    _assert_segment(mseg, "margin")


def test_margin_final_positive_change_word():
    """margin FINAL 且 marginBalanceChange>0：含上升方向词。"""
    mseg = _summary(_base_modules())["margin"]
    assert any(w in mseg for w in ["增加", "上升", "净买入"])
    _assert_segment(mseg, "margin")


def test_northbound_legacy_negative_netflow():
    """northbound legacy totalNetInflow<0：含"净流出"。"""
    modules = _base_modules()
    modules["northbound"] = {
        "status": "FINAL",
        "mode": "POST_20240819_LEGACY_IMPORTED",
        "legacyImportedFields": {
            "totalNetInflow": -156.32,
            "shanghaiNetInflow": -68.54,
            "shenzhenNetInflow": -87.78,
        },
    }
    nb = _summary(modules)["northbound"]
    assert "净流出" in nb
    assert "156.32" in nb
    _assert_segment(nb, "northbound")


def test_northbound_official_groups():
    """northbound OFFICIAL：组1(停发/不再)+组2(季度/时点)各命中一词，且无禁词。"""
    nb = _summary(_base_modules())["northbound"]

    assert any(w in nb for w in ["停发", "不再"])
    assert any(w in nb for w in ["季度", "point-in-time", "时点"])
    for w in ["官方日度净流入", "连续净流入", "今日北向净流入"]:
        assert w not in nb
    _assert_segment(nb, "northbound")


def test_track_conclusion_all_prefixes_and_decisions():
    """tracks FINAL 且 >=4 赛道：trackConclusion 含全部赛道前 2 字子串 + 判定词。"""
    modules = _base_modules()
    items = modules["tracks"]["items"]
    concl = _summary(modules)["trackConclusion"]

    for item in items:
        name = item["trackName"]
        core = name.split("（")[0].split("(")[0].strip()
        frag = core[:2] if len(core) >= 2 else core
        assert frag in concl, f"trackConclusion 缺赛道前缀 {frag!r}"

    decisions = {str(it["decision"]) for it in items if it.get("decision")}
    mentioned = sum(1 for d in decisions if d in concl)
    assert mentioned >= 2, f"trackConclusion 判定词不足: {concl!r}"
    _assert_segment(concl, "trackConclusion")


def test_track_conclusion_not_final_gap_words():
    """tracks 非 FINAL：trackConclusion 为缺口式文案，不生成貌似完整结论。"""
    modules = _base_modules()
    modules["tracks"] = {"status": "UNAVAILABLE", "items": []}
    concl = _summary(modules)["trackConclusion"]
    assert "缺失" in concl  # 非 FINAL 应采用缺口词，不生成貌似完整结论
    _assert_segment(concl, "trackConclusion")


def test_all_segments_minchars_cjk_and_risk_warning():
    """8 段全部 minChars>=10、CJK>=0.5、无 rejectedPlaceholders；riskWarning 含固定句。"""
    mod = _summary(_base_modules())

    for name in [
        "indexAndTurnover",
        "sentiment",
        "fundFlow",
        "trackConclusion",
        "marketEnvironment",
        "northbound",
        "margin",
        "riskWarning",
    ]:
        _assert_segment(mod[name], name)

    assert "不构成投资建议" in mod["riskWarning"]
    assert "股市有风险" in mod["riskWarning"]
    assert "投资需谨慎" in mod["riskWarning"]


def test_index_fundflow_sentiment_no_placeholder():
    """indexAndTurnover / fundFlow / sentiment 有效分支也不含 rejected 占位词。"""
    mod = _summary(_base_modules())
    _assert_segment(mod["indexAndTurnover"], "indexAndTurnover")
    _assert_segment(mod["fundFlow"], "fundFlow")
    _assert_segment(mod["sentiment"], "sentiment")


def test_risk_warning_excludes_summary_self_reference():
    """margin PENDING + summary 仍为占位 PENDING 时，待披露清单不含
    summary 自身（new_snapshot 播种占位导致速览条每晚误显示
    「待披露：margin、summary」，2026-08-28 修复回归）。"""
    modules = _base_modules()
    modules["margin"] = {
        "status": "PENDING",
        "latestPublishedReference": {
            "dataDate": "2026-08-19",
            "marginBalance": 26673.45,
        },
    }
    # 复现生产时序：generate_summary 运行时 summary 尚是播种的占位 PENDING
    modules["summary"] = {"status": "PENDING", "dataDate": None}

    rw = _summary(modules)["riskWarning"]

    assert "待披露：margin。" in rw
    assert "summary" not in rw
