"""模块 2：沪深两市成交额。

两市严格定义为上交所 A 股 + 深交所 A 股，不含北交所。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus

def collect_turnover(
    trade_date: str,
    market_rules: dict | None = None,
) -> dict[str, Any]:
    import akshare as ak

    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": trade_date,
            "source": ["EASTMONEY"],
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

    try:
        sh = ak.stock_sh_a_spot_em()
        sz = ak.stock_sz_a_spot_em()

        sh_total = _sum_amount(sh)
        sz_total = _sum_amount(sz)

        total_yuan = sh_total + sz_total

    except Exception as exc:  # noqa: BLE001
        return _error(
            trade_date,
            str(exc),
        )

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
        "source": ["EASTMONEY"],
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
        "source": ["EASTMONEY"],
        "unit": "亿元",
        "errors": [message],
        "turnoverToday": None,
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    }
