"""Historical/current-session enhancement tests for the sentiment module.

Monkeypatches akshare (no network). Covers:
- Current-day FINAL branch: limitSealRatePct (seal rate) + maxLimitUpStreak (top streak);
- Historical in-window day: PARTIAL = HISTORICAL_LIMIT_POOL_ONLY with seal rate + streak;
- Historical pre-window day (pool empty): UNAVAILABLE = HISTORICAL_LIMIT_POOL_UNAVAILABLE;
- Limit-up pool ST/non-ST split by name prefix.
"""

from __future__ import annotations

import datetime as _dt

import akshare
import pandas as pd

import collector.modules.sentiment as sentiment


def _today(monkeypatch, date_str="2026-08-13"):
    """Pin sentiment.datetime.now to a fixed date to hit the current-day FINAL branch."""
    year, month, day = (int(p) for p in date_str.split("-"))

    class _FakeDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(year, month, day, 15, 0, tzinfo=tz)

    monkeypatch.setattr(sentiment, "datetime", _FakeDatetime)


def _patch_pools(monkeypatch, *, zt=None, dt=None, zbgc=None, spot=None):
    def _get(df):
        return pd.DataFrame() if df is None else df

    monkeypatch.setattr(akshare, "stock_zt_pool_em", lambda date: _get(zt))
    monkeypatch.setattr(akshare, "stock_zt_pool_dtgc_em", lambda date: _get(dt))
    monkeypatch.setattr(akshare, "stock_zt_pool_zbgc_em", lambda date: _get(zbgc))
    if spot is not None:
        monkeypatch.setattr(akshare, "stock_zh_a_spot_em", lambda: spot)


def test_daily_final_appends_seal_rate_and_streak(monkeypatch):
    """Current day FINAL: zt=3 rows (streaks 1/2/3) + zbgc=2 -> seal 60.0, streak "3连板"."""
    _today(monkeypatch)
    zt = pd.DataFrame({
        "名称": ["甲股份", "乙股份", "丙股份"],
        "连板数": [1, 2, 3],
    })
    zbgc = pd.DataFrame({"名称": ["丁股份", "戊股份"]})
    spot = pd.DataFrame({"涨跌幅": [1.0, -1.0, 0.5]})
    _patch_pools(monkeypatch, zt=zt, dt=None, zbgc=zbgc, spot=spot)

    result = sentiment.collect_sentiment("2026-08-13")

    assert result["status"] == "FINAL"
    assert result["limitSealRatePct"] == 60.0
    assert result["maxLimitUpStreak"] == "3连板"
    assert result["nonStLimitUpCount"] == 3
    assert result["stLimitUpCount"] == 0
    assert result["brokenLimitCount"] == 2


def test_historical_partial_seal_rate_and_streak(monkeypatch):
    """2026-08-13 (in-window): zt=2 rows (streaks 1/5) + zbgc=2 -> seal 50.0, streak "5连板"."""
    zt = pd.DataFrame({
        "名称": ["甲股份", "乙股份"],
        "连板数": [1, 5],
    })
    zbgc = pd.DataFrame({"名称": ["丙股份", "丁股份"]})
    _patch_pools(monkeypatch, zt=zt, dt=None, zbgc=zbgc)

    result = sentiment.collect_sentiment("2026-08-13")

    assert result["status"] == "PARTIAL"
    assert result["reason"] == "HISTORICAL_LIMIT_POOL_ONLY"
    assert result["limitSealRatePct"] == 50.0
    assert result["maxLimitUpStreak"] == "5连板"
    assert result["nonStLimitUpCount"] == 2
    assert result["brokenLimitCount"] == 2


def test_historical_before_window_unavailable(monkeypatch):
    """2026-07-20 (pre-window): pool returns empty -> UNAVAILABLE / HISTORICAL_LIMIT_POOL_UNAVAILABLE."""
    _patch_pools(monkeypatch, zt=None, dt=None, zbgc=None)

    result = sentiment.collect_sentiment("2026-07-20")

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_LIMIT_POOL_UNAVAILABLE"
    assert result["nonStLimitUpCount"] is None


def test_historical_st_pool_split(monkeypatch):
    """ST-prefixed rows go to stLimitUpCount, the rest to nonStLimitUpCount."""
    zt = pd.DataFrame({
        "名称": ["甲股份", "*ST 乙股份", "ST 丙股份", "丁股份", "*ST 戊股份"],
    })
    zbgc = pd.DataFrame({"名称": ["己股份"]})
    _patch_pools(monkeypatch, zt=zt, dt=None, zbgc=zbgc)

    result = sentiment.collect_sentiment("2026-08-13")

    assert result["status"] == "PARTIAL"
    assert result["nonStLimitUpCount"] == 2  # 甲股份, 丁股份
    assert result["stLimitUpCount"] == 3     # *ST 乙股份, ST 丙股份, *ST 戊股份
