"""模块 2：沪深两市成交额。

两市严格定义为上交所 A 股 + 深交所 A 股，不含北交所。

多源降级（R5-P2-01）：东财 spot 失败时降级到新浪全市场 spot，
新浪返回的代码带市场前缀（sh/sz/bj），求和时按口径过滤。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus


def _fetch_turnover_yuan(
    source: str,
) -> float:
    """按指定源返回两市总成交额（元）。"""
    import akshare as ak

    if source == "eastmoney":
        sh = ak.stock_sh_a_spot_em()
        sz = ak.stock_sz_a_spot_em()
        return _sum_amount(sh) + _sum_amount(sz)

    if source == "sina":
        spot = ak.stock_zh_a_spot()
        return _sum_amount_sh_sz(spot)

    raise ValueError(f"unknown spot source: {source}")


def _sum_amount_sh_sz(df) -> float:
    """新浪全市场 spot：仅统计沪/深 A 股（口径：不含北交所）。"""
    if df is None or df.empty:
        raise ValueError("empty market spot dataframe")

    code_col = _pick_col(
        df,
        ("代码", "code"),
    )

    if code_col is None:
        raise ValueError(
            f"code column missing: {list(df.columns)}"
        )

    if "成交额" not in df.columns:
        raise ValueError(
            f"成交额 column missing: {list(df.columns)}"
        )

    codes = df[code_col].astype(str)
    mask = codes.str.startswith(
        ("sh", "sz")
    )

    values = pd.to_numeric(
        df.loc[mask, "成交额"],
        errors="coerce",
    )

    if values.notna().sum() == 0:
        raise ValueError("all 成交额 values invalid")

    return float(
        values.fillna(0).sum()
    )


def collect_turnover(
    trade_date: str,
    market_rules: dict | None = None,
) -> dict[str, Any]:
    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": trade_date,
            "source": ["EASTMONEY", "SINA"],
            "unit": "亿元",
            "reason": "HISTORICAL_SPOT_NOT_SUPPORTED",
            "turnoverToday": None,
            "turnoverPrevious": None,
            "turnoverDelta": None,
            "turnoverChangePct": None,
            "volumeState": "UNKNOWN",
        }

    rules = market_rules or {}
    volume_rules = rules.get(
        "volume_state",
        {},
    )

    expand_pct = float(
        volume_rules.get(
            "expansion_threshold_pct",
            5,
        )
    )

    contract_pct = float(
        volume_rules.get(
            "contraction_threshold_pct",
            -5,
        )
    )

    total_yuan, used, source_errors = try_sources(
        "spot",
        ["eastmoney"],
        _fetch_turnover_yuan,
    )

    if total_yuan is None:
        return _error(
            trade_date,
            "; ".join(source_errors or ["unknown spot failure"]),
        )

    sources = [used.upper()] if used else ["EASTMONEY"]
    turnover_today_yi = round(
        total_yuan / 1e8,
        2,
    )

    from datetime import date

    from collector.calendar import previous_trading_day

    try:
        previous = previous_trading_day(
            date.fromisoformat(trade_date),
            fallback_weekday=True,
        )

        turnover_previous_yi = (
            _load_previous_turnover(
                previous.isoformat()
            )
        )
    except ValueError:
        turnover_previous_yi = None

    if turnover_previous_yi is not None:
        delta = round(
            turnover_today_yi
            - turnover_previous_yi,
            2,
        )

        if turnover_previous_yi > 0:
            change_pct = round(
                delta
                / turnover_previous_yi
                * 100,
                2,
            )
        else:
            change_pct = None
    else:
        delta = None
        change_pct = None

    volume_state = "UNKNOWN"

    if change_pct is not None:
        if change_pct >= expand_pct:
            volume_state = "EXPANSION"
        elif change_pct <= contract_pct:
            volume_state = "CONTRACTION"
        else:
            volume_state = "FLAT"

    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": sources,
        "unit": "亿元",
        "turnoverToday": turnover_today_yi,
        "turnoverPrevious": turnover_previous_yi,
        "turnoverDelta": delta,
        "turnoverChangePct": change_pct,
        "volumeState": volume_state,
    }


def _sum_amount(df) -> float:
    if df is None or df.empty:
        raise ValueError("empty market spot dataframe")

    if "成交额" not in df.columns:
        raise ValueError(
            f"成交额 column missing: {list(df.columns)}"
        )

    values = pd.to_numeric(
        df["成交额"],
        errors="coerce",
    )

    if values.notna().sum() == 0:
        raise ValueError("all 成交额 values invalid")

    return float(
        values.fillna(0).sum()
    )


def _load_previous_turnover(
    previous_date: str,
) -> float | None:
    from collector.config import daily_path

    path = daily_path(previous_date)

    if not path.exists():
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        value = (
            data["modules"]["turnover"]
            .get("turnoverToday")
        )

        return (
            float(value)
            if value is not None
            else None
        )

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return None


def _error(
    trade_date: str,
    message: str,
) -> dict[str, Any]:
    return {
        "status": ModuleStatus.ERROR.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY", "SINA"],
        "unit": "亿元",
        "errors": [message],
        "turnoverToday": None,
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    }


def _pick_col(
    df,
    candidates: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None
