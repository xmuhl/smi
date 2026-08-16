"""北向 OFFICIAL_REPLACEMENT 口径 PIT 测试（离线零联网）。

monkeypatch 假 HKEX 页面 + 日历，覆盖：
- 季度持仓成功路径：mode=POST_20240819_OFFICIAL_REPLACEMENT、
  sourceSystem=HKEX、quarterlyHolding.status=FINAL、
  publishedAt = asOf 后第 5 个交易日（用 collector.calendar 独立计算断言一致）、
  publishedAt<=2026-08-14（防 look-ahead）；
- asOf 不可解析：publishedAt=None 且模块 fail-closed（非 FINAL、errors 记录），不伪造；
- 完整模块结果放入最小快照，通过 validate_snapshot 的 northbound 契约校验。
"""

from __future__ import annotations

from datetime import date, timedelta

from collector import calendar as _cal
from collector.modules.northbound import (
    DISCLOSURE_LAG_TRADING_DAYS,
    collect_northbound,
)


def _fake_is_trading_day(day, fallback_weekday=True):
    """离线确定性日历：周一至周五为交易日（与 asOf 落在工作日一致）。"""
    del fallback_weekday
    return day.weekday() < 5


def _fake_responses():
    """伪造 requests.Response：.text 返回 HKEX 风格页面，.raise_for_status() 无副作用。"""
    page = """<html><body>
        <p>Shareholding Date: 2026/06/30</p>
        <table>
          <tr>
            <th>Stock Code</th><th>Name</th>
            <th>Shareholding in CCASS</th><th>% of issued shares</th>
          </tr>
          <tr>
            <td>Stock Code: 00700</td>
            <td>Name: TENCENT HOLDINGS LTD (A #00700)</td>
            <td>Shareholding in CCASS: 1,234,567,890</td>
            <td>12.34%</td>
          </tr>
          <tr>
            <td>Stock Code: 600519</td>
            <td>Name: KWEICHOW MOUTAI LTD (A #600519)</td>
            <td>Shareholding in CCASS: 98,765,432</td>
            <td>-5.67%</td>
          </tr>
        </table>
      </body></html>"""

    class _FakeResponse:
        text = page
        def raise_for_status(self):
            return None

    return _FakeResponse()


def _patch_hkex(monkeypatch):
    monkeypatch.setattr(
        "collector.modules.northbound.requests.get",
        lambda url, timeout=30, headers=None: _fake_responses(),
    )
    monkeypatch.setattr(
        _cal,
        "is_trading_day",
        _fake_is_trading_day,
    )


def _expected_publication_date(as_of_str: str) -> str:
    """用 collector.calendar 独立计算：asOf 后第 5 个交易日（严格晚于 asOf）。"""
    as_of = date.fromisoformat(as_of_str)
    cursor = as_of
    for _ in range(DISCLOSURE_LAG_TRADING_DAYS):
        # next_trading_day 也是用被 monkeypatch 的 is_trading_day，与模块同一日历源。
        cursor = _cal.next_trading_day(cursor, fallback_weekday=True)
    return cursor.isoformat()


def test_quarterly_holding_success_pit(monkeypatch):
    """季度持仓成功路径：OFFICIAL_REPLACEMENT + HKEX + FINAL + publishedAt 一致。"""
    _patch_hkex(monkeypatch)

    result = collect_northbound("2026-08-14")

    # 口径枚举与来源
    assert result["status"] == "FINAL"
    assert result["mode"] == "POST_20240819_OFFICIAL_REPLACEMENT"
    assert result["sourceSystem"] == "HKEX"
    assert result["dataDate"] == "2026-08-14"

    qh = result["quarterlyHolding"]
    assert qh["status"] == "FINAL"
    assert qh["asOf"] == "2026-06-30"
    assert isinstance(qh["items"], list) and len(qh["items"]) > 0

    # 逐项 typed schema
    for item in qh["items"]:
        for field in (
            "code",
            "hkexStockCode",
            "name",
            "shareholding",
            "pctOfIssued",
            "market",
        ):
            assert field in item
        assert item["market"] in ("sh", "sz")
        assert isinstance(item["pctOfIssued"], str)
        assert item["pctOfIssued"].endswith("%")

    # publishedAt = asOf 后第 5 个交易日（独立计算断言一致），且防 look-ahead
    expected = _expected_publication_date(qh["asOf"])
    assert qh["publishedAt"] == expected
    assert expected == "2026-07-07"
    assert qh["publishedAt"] <= "2026-08-14"


def test_unparsable_as_of_fails_closed(monkeypatch):
    """HKEX 返回不可解析 asOf → publishedAt=None、模块非 FINAL、errors 记录。"""
    page = """<html><body>
        <p>Shareholding Date: 2026/02/31</p>
        <table>
          <tr>
            <th>Stock Code</th><th>Name</th>
            <th>Shareholding in CCASS</th><th>% of issued shares</th>
          </tr>
          <tr>
            <td>Stock Code: 00700</td>
            <td>Name: TENCENT HOLDINGS LTD (A #00700)</td>
            <td>Shareholding in CCASS: 1,234,567,890</td>
            <td>12.34%</td>
          </tr>
        </table>
      </body></html>"""

    class _FakeResponse:
        text = page
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "collector.modules.northbound.requests.get",
        lambda url, timeout=30, headers=None: _FakeResponse(),
    )
    monkeypatch.setattr(_cal, "is_trading_day", _fake_is_trading_day)

    result = collect_northbound("2026-08-14")

    # fail-closed：不伪造 FINAL，publishedAt 为 None
    assert result["status"] == "UNAVAILABLE"
    qh = result["quarterlyHolding"]
    assert qh["status"] == "UNAVAILABLE"
    assert qh["publishedAt"] is None
    assert qh["items"] == []
    # 错误已记录
    assert any(
        "UNPARSABLE_AS_OF_DATE" in (err or "")
        for err in result.get("errors") or []
    )


def test_validate_snapshot_contract(monkeypatch):
    """完整模块结果放入最小快照，通过 validate_snapshot 的 northbound 契约。"""
    from collector.schema import finalize_snapshot, new_snapshot
    from collector.validators.schema import validate_snapshot

    _patch_hkex(monkeypatch)

    module = collect_northbound("2026-08-14")
    assert module["status"] == "FINAL"

    snapshot = new_snapshot("2026-08-14")
    for name, mod in snapshot["modules"].items():
        mod["status"] = "UNAVAILABLE"
        mod["dataDate"] = "2026-08-14"

    snapshot["modules"]["northbound"] = module
    finalize_snapshot(snapshot)

    # 契约校验：FINAL northbound（OFFICIAL_REPLACEMENT）不应抛异常。
    # 注：validator 对 mode 仅保留旧枚举分支（QUARTERLY_ONLY/LEGACY_IMPORTED），
    #     未知新值不会额外拒绝；若未来收紧枚举，此处仅报告、不改 validator。
    validate_snapshot(snapshot)
