"""模块 3：市场情绪指标。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus

def is_st(
    name: str,
) -> bool:
    value = str(name or "").strip().upper()

    return bool(
        re.match(
            r"^(?:\*ST|ST|S\*ST)",
            value,
        )
    )

def collect_sentiment(
    trade_date: str,
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
            "reason": "HISTORICAL_FULL_SENTIMENT_NOT_SUPPORTED",
            "riseCount": None,
            "fallCount": None,
            "flatCount": None,
            "suspendedCount": None,
            "nonStLimitUpCount": None,
            "stLimitUpCount": None,
            "nonStLimitDownCount": None,
            "stLimitDownCount": None,
            "brokenLimitCount": None,
        }

    yyyymmdd = trade_date.replace("-", "")

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY"],
        "riseCount": None,
        "fallCount": None,
        "flatCount": None,
        "suspendedCount": None,
        "nonStLimitUpCount": None,
        "stLimitUpCount": None,
        "nonStLimitDownCount": None,
        "stLimitDownCount": None,
        "brokenLimitCount": None,
        "errors": [],
    }

    try:
        spot = ak.stock_zh_a_spot_em()

        if spot is None or spot.empty:
            raise ValueError("empty stock spot")

        pct_col = _pick_col(
            spot,
            (
                "涨跌幅",
                "change_pct",
                "pct_chg",
            ),
        )

        if pct_col is None:
            raise ValueError(
                "涨跌幅 column missing"
            )

        values = pd.to_numeric(
            spot[pct_col],
            errors="coerce",
        )

        result["riseCount"] = int(
            (values > 0).sum()
        )
        result["fallCount"] = int(
            (values < 0).sum()
        )
        result["flatCount"] = int(
            (values == 0).sum()
        )
        result["suspendedCount"] = int(
            values.isna().sum()
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"spot: {exc}"
        )

    try:
        pool = ak.stock_zt_pool_em(
            date=yyyymmdd
        )

        non_st, st = _split_st_pool(pool)

        result["nonStLimitUpCount"] = non_st
        result["stLimitUpCount"] = st

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"zt_pool: {exc}"
        )

    try:
        pool = ak.stock_zt_pool_dtgc_em(
            date=yyyymmdd
        )

        non_st, st = _split_st_pool(pool)

        result["nonStLimitDownCount"] = non_st
        result["stLimitDownCount"] = st

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"dt_pool: {exc}"
        )

    try:
        pool = ak.stock_zt_pool_zbgc_em(
            date=yyyymmdd
        )

        result["brokenLimitCount"] = (
            0
            if pool is None or pool.empty
            else int(len(pool))
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"zbgc: {exc}"
        )

    if result["errors"]:
        result["status"] = ModuleStatus.ERROR.value

    return result

def _split_st_pool(
    df,
) -> tuple[int, int]:
    if df is None or df.empty:
        return 0, 0

    name_col = _pick_col(
        df,
        (
            "名称",
            "name",
        ),
    )

    if name_col is None:
        raise ValueError(
            "pool name column missing"
        )

    names = df[name_col].astype(str)

    st_count = sum(
        1
        for name in names
        if is_st(name)
    )

    return len(names) - st_count, st_count

def _pick_col(
    df,
    candidates: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None
