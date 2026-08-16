"""历史回补分支测试：push2his 板块历史主力资金流 → 历史交易日六类榜单。

用 monkeypatch 替换模块级 requests（假 Session）与 akshare（回退名单），
零联网。覆盖：
- clist 提供行业/概念各 12 个假 secid，逐板块 daykline 含 D 日行 →
  行业/概念 流入/流出排序正确、netInflowYi 换算正确（f52=12568000000 元 → 125.68 亿）；
- 个股两类榜单恒为空 + errors 含 STOCK_HISTORICAL_UNAVAILABLE；
- 板块清单接口抛异常 → fail-closed UNAVAILABLE + FUNDFLOW_HISTORICAL_FETCH_FAILED；
- clist 不可用 → 回退 akshare 板块名单接口仍可出 FINAL；
- 完整模块结果放入最小快照通过 collector.validators.schema.validate_snapshot 契约。
"""

from __future__ import annotations

from collector.modules import fund_flow as ff
from collector.modules.fund_flow import (
    EASTMONEY_HISTORICAL_METHOD,
    _f52_on_date,
    collect_fund_flow,
)

TRADE_DATE = "2026-08-13"


# ---------------------------------------------------------------------------
# 假 requests：可替换 fund_flow.requests，Session.get 按 URL/参数字分发假 JSON。
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.trust_env = True

    def get(self, url, params=None, timeout=None, headers=None):
        del timeout, headers
        return _FakeResponse(self.handler(url, params or {}))

    def close(self):
        pass


def _make_fake_requests(handler):
    class _FakeRequestsModule:
        def Session(self):
            return _FakeSession(handler)

    return _FakeRequestsModule()


# ---------------------------------------------------------------------------
# 假数据构造：clist 清单 + 每板块 daykline（D 日含 f52，单位：元）
# ---------------------------------------------------------------------------
# 行业 12 个（7 正 5 负）、概念 12 个（6 正 6 负），均满足"有效板块数 >= 10"。
_INDUSTRY_BOARDS = {
    # code: (name, f52 元)
    "BK1001": ("行业甲", 12568000000),   # +125.68
    "BK1002": ("行业乙", 8000000000),    # +80.0
    "BK1003": ("行业丙", 5000000000),    # +50.0
    "BK1004": ("行业丁", 3000000000),    # +30.0
    "BK1005": ("行业戊", 2000000000),    # +20.0
    "BK1006": ("行业己", 1500000000),    # +15.0
    "BK1007": ("行业庚", 1000000000),    # +10.0
    "BK1008": ("行业辛", -2000000000),   # -20.0
    "BK1009": ("行业壬", -4000000000),   # -40.0
    "BK1010": ("行业癸", -6000000000),   # -60.0
    "BK1011": ("行业子", -8000000000),   # -80.0
    "BK1012": ("行业丑", -10000000000),  # -100.0
}

_CONCEPT_BOARDS = {
    "BK2001": ("概念甲", 9000000000),    # +90.0
    "BK2002": ("概念乙", 6000000000),    # +60.0
    "BK2003": ("概念丙", 3500000000),    # +35.0
    "BK2004": ("概念丁", 2600000000),    # +26.0
    "BK2005": ("概念戊", 1900000000),    # +19.0
    "BK2006": ("概念己", 700000000),     # +7.0
    "BK2007": ("概念辛", -2500000000),   # -25.0
    "BK2008": ("概念壬", -4500000000),   # -45.0
    "BK2009": ("概念癸", -6500000000),   # -65.0
    "BK2010": ("概念子", -8500000000),   # -85.0
    "BK2011": ("概念丑", -10500000000),  # -105.0
    "BK2012": ("概念寅", -11500000000),  # -115.0
}


def _daykline_payload(secid, boards):
    code = secid.removeprefix("90.")
    _name, f52 = boards[code]
    # klines 升序：加一根更早日期行，D 日行含 f52
    return {
        "data": {
            "klines": [
                f"2026-08-12,{f52},0,0,0",
                f"{TRADE_DATE},{f52},0,0,0",
            ]
        }
    }


def _clist_diff(fs, boards):
    return [
        {"f12": code, "f14": name}
        for code, (name, _f52) in boards.items()
    ]


def _handle(url, params, _boards):
    if "clist/get" in url:
        fs = params.get("fs")
        if fs == "m:90+t:2":
            return {"data": {"diff": _clist_diff(fs, _INDUSTRY_BOARDS)}}
        if fs == "m:90+t:3":
            return {"data": {"diff": _clist_diff(fs, _CONCEPT_BOARDS)}}
        raise AssertionError(f"unexpected clist fs: {fs}")
    if "fflow/daykline/get" in url:
        secid = params.get("secid")
        code = secid.removeprefix("90.")
        if code in _INDUSTRY_BOARDS:
            return _daykline_payload(secid, _INDUSTRY_BOARDS)
        if code in _CONCEPT_BOARDS:
            return _daykline_payload(secid, _CONCEPT_BOARDS)
        raise AssertionError(f"unexpected secid: {secid}")
    raise AssertionError(f"unexpected url: {url}")


def _patch_clist(monkeypatch):
    """用 clist 主路铺路（requests 假实现，行业/概念各返回 12 板块）。"""
    monkeypatch.setattr(
        ff,
        "requests",
        _make_fake_requests(lambda url, params: _handle(url, params, None)),
    )
    # 兜底：即使误走 akshare 也暴露，不静默联网
    monkeypatch.setattr(
        ff,
        "_akshare_secid_list",
        lambda board_type: (_ for _ in ()).throw(
            AssertionError(f"unexpected akshare fallback: {board_type}")
        ),
    )


def test_historical_industry_concept_rankings(monkeypatch):
    """行业/概念各 12 板块：排序正确、netInflowYi 换算正确、条目结构正确。"""
    _patch_clist(monkeypatch)

    result = collect_fund_flow(TRADE_DATE)

    assert result["status"] == "FINAL"
    assert result["dataDate"] == TRADE_DATE
    assert result["method"] == EASTMONEY_HISTORICAL_METHOD
    assert result["source"] == ["EASTMONEY_PUSH2HIS"]
    assert result["unit"] == "亿元"

    # 行业净流入降序：甲(125.68) > 乙(80) > 丙(50) > 丁(30) > 戊(20) > 己(15) > 庚(10)
    ind_in = [e["name"] for e in result["industryInflowTop10"]]
    assert ind_in == [
        "行业甲", "行业乙", "行业丙", "行业丁", "行业戊", "行业己", "行业庚",
    ]
    # f52=12568000000 元 → 125.68 亿（round 2）
    assert result["industryInflowTop10"][0]["netInflowYi"] == 125.68
    assert result["industryInflowTop10"][0]["name"] == "行业甲"
    assert result["industryInflowTop10"][0]["code"] == "BK1001"

    # 行业净流出升序（最负在前）：丑(-100) < 子(-80) < 癸(-60) < 壬(-40) < 辛(-20)
    ind_out = [e["name"] for e in result["industryOutflowTop10"]]
    assert ind_out == ["行业丑", "行业子", "行业癸", "行业壬", "行业辛"]
    assert result["industryOutflowTop10"][0]["netInflowYi"] == -100.0

    # 概念净流入：甲(90) > 乙(60) > 丙(35) > 丁(26) > 戊(19) > 己(7)
    con_in = [e["name"] for e in result["conceptInflowTop10"]]
    assert con_in == ["概念甲", "概念乙", "概念丙", "概念丁", "概念戊", "概念己"]
    # 概念净流出：寅(-115) < 丑(-105) < 子(-85) < 癸(-65) < 壬(-45) < 辛(-25)
    con_out = [e["name"] for e in result["conceptOutflowTop10"]]
    assert con_out == [
        "概念寅", "概念丑", "概念子", "概念癸", "概念壬", "概念辛",
    ]
    assert result["conceptOutflowTop10"][0]["netInflowYi"] == -115.0

    # 条目结构：name / code / netInflowYi
    for entry in (
        result["industryInflowTop10"]
        + result["industryOutflowTop10"]
        + result["conceptInflowTop10"]
        + result["conceptOutflowTop10"]
    ):
        assert "name" in entry
        assert "code" in entry
        assert "netInflowYi" in entry


def test_historical_stock_boards_empty_and_noted(monkeypatch):
    """个股两类榜单恒为空 + errors 含 STOCK_HISTORICAL_UNAVAILABLE。"""
    _patch_clist(monkeypatch)

    result = collect_fund_flow(TRADE_DATE)

    assert result["status"] == "FINAL"
    assert result["stockInflowTop10"] == []
    assert result["stockOutflowTop10"] == []
    assert any(
        "STOCK_HISTORICAL_UNAVAILABLE" in (err or "")
        for err in result["errors"]
    )


def test_historical_board_list_fetch_fails_closed(monkeypatch):
    """板块清单接口抛异常（模拟 push2his 被封）→ UNAVAILABLE + FUNDFLOW_HISTORICAL_FETCH_FAILED。"""

    def boom(url, params):
        del url, params
        raise ConnectionError("push2his clist unreachable")

    monkeypatch.setattr(ff, "requests", _make_fake_requests(boom))
    # akshare 回退也失败，整体 fail-closed
    monkeypatch.setattr(
        ff,
        "_akshare_secid_list",
        lambda board_type: (_ for _ in ()).throw(
            RuntimeError(f"{board_type}: akshare list failed")
        ),
    )

    result = collect_fund_flow(TRADE_DATE)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "FUNDFLOW_HISTORICAL_FETCH_FAILED"
    assert result["industryInflowTop10"] == []
    assert result["conceptInflowTop10"] == []
    assert result["stockInflowTop10"] == []
    assert any(
        "FUNDFLOW_HISTORICAL_FETCH_FAILED" in (err or "")
        for err in result["errors"]
    )


def test_historical_fallback_to_akshare_secid_list(monkeypatch):
    """clist 不可用 → 回退 akshare 板块名单接口，仍出 FINAL。"""
    # 用混合 handler：clist 抛异常、daykline 正常响应
    def handler(url, params):
        if "clist/get" in url:
            raise ConnectionError("clist down")
        if "fflow/daykline/get" in url:
            return _handle(url, params, None)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(ff, "requests", _make_fake_requests(handler))
    monkeypatch.setattr(
        ff,
        "_akshare_secid_list",
        lambda board_type: (
            [(code, name) for code, (name, _f) in _INDUSTRY_BOARDS.items()]
            if board_type == "industry"
            else [(code, name) for code, (name, _f) in _CONCEPT_BOARDS.items()]
        ),
    )

    result = collect_fund_flow(TRADE_DATE)

    assert result["status"] == "FINAL"
    assert result["industryInflowTop10"][0]["name"] == "行业甲"
    assert result["conceptInflowTop10"][0]["name"] == "概念甲"


def test_f52_on_date_direct():
    klines = [
        "2026-08-12,100.0,0,0,0",
        f"{TRADE_DATE},12568000000.0,0,0,0",
    ]
    assert _f52_on_date(klines, TRADE_DATE) == 12568000000.0
    # 缺 D 日
    assert _f52_on_date(klines, "2026-08-14") is None
    # 空 / 非法行
    assert _f52_on_date([], TRADE_DATE) is None
    assert _f52_on_date(["garbage"], TRADE_DATE) is None


def test_historical_result_validates_against_schema(monkeypatch):
    """完整模块结果放入最小快照，须通过 validate_snapshot 的 fundFlow 契约。"""
    from collector.schema import finalize_snapshot, new_snapshot
    from collector.validators.schema import validate_snapshot

    _patch_clist(monkeypatch)

    module = collect_fund_flow(TRADE_DATE)
    assert module["status"] == "FINAL"

    snapshot = new_snapshot(TRADE_DATE)
    for name, mod in snapshot["modules"].items():
        mod["status"] = "UNAVAILABLE"
        mod["dataDate"] = TRADE_DATE

    snapshot["modules"]["fundFlow"] = module
    finalize_snapshot(snapshot)

    # 契约校验：FINAL fundFlow dataDate==tradeDate，个股榜单为空不违反代码契约
    validate_snapshot(snapshot)
