"""模块 3：市场情绪指标。

多源降级（R5-P2-01）：涨跌家数/暂停家数按 sources.yaml 的 spot 顺序
尝试 eastmoney / sina；涨停/跌停/炸板池为东财独有接口，失败如实记录。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus
from collector.netguard import net_guard


def is_st(
    name: str,
) -> bool:
    """ST 判定（统一谓词：raw_archive.is_st_stock_name，见设计文档 §39.5.5）。"""
    from collector.modules.raw_archive import is_st_stock_name

    return is_st_stock_name(name)


def _fetch_spot_counts(
    source: str,
    trade_date: str,
) -> dict[str, int]:
    """按指定源返回全市场涨跌统计。"""
    import akshare as ak

    if source == "eastmoney":
        spot = ak.stock_zh_a_spot_em()
    elif source == "sina":
        spot = ak.stock_zh_a_spot()
    else:
        raise ValueError(f"unknown spot source: {source}")

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

    return {
        "riseCount": int((values > 0).sum()),
        "fallCount": int((values < 0).sum()),
        "flatCount": int((values == 0).sum()),
        "suspendedCount": int(values.isna().sum()),
    }


def _fetch_historical_limit_pools(
    trade_date: str,
) -> dict[str, Any] | None:
    """历史交易日：东财涨停池（保留窗口内可用）。

    返回 None 表示该日无任何涨停池数据（超出东财保留窗口）；
    返回 dict 含涨停/跌停/炸板计数；跌停/炸板失败仅记入 errors，
    不吞掉已取得的涨停计数（宁缺勿错，不用 0 伪装缺失）。
    """
    import akshare as ak

    yyyymmdd = trade_date.replace("-", "")

    pool = ak.stock_zt_pool_em(
        date=yyyymmdd
    )

    if pool is None or pool.empty:
        return None

    non_st, st = _split_st_pool(pool)
    zt_total = non_st + st

    result: dict[str, Any] = {
        "nonStLimitUpCount": non_st,
        "stLimitUpCount": st,
        "nonStLimitDownCount": None,
        "stLimitDownCount": None,
        "brokenLimitCount": None,
        "limitSealRatePct": None,
        "maxLimitUpStreak": _max_limit_up_streak(pool),
        "errors": [],
        "warnings": [],
    }

    try:
        pool = ak.stock_zt_pool_dtgc_em(
            date=yyyymmdd
        )

        if pool is None or pool.empty:
            result["warnings"].append(
                "dt_pool: EMPTY_OR_UNAVAILABLE"
            )
        else:
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

        if pool is None or pool.empty:
            result["warnings"].append(
                "zbgc: EMPTY_OR_UNAVAILABLE"
            )
        else:
            broken = int(len(pool))
            result["brokenLimitCount"] = broken
            result["limitSealRatePct"] = _seal_rate(
                zt_total, broken
            )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"zbgc: {exc}"
        )

    return result


@net_guard(timeout=1200.0, retries=0)
def _collect_sentiment_historical(
    trade_date: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": ModuleStatus.UNAVAILABLE.value,
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
    }

    try:
        pools = _fetch_historical_limit_pools(
            trade_date
        )
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": ModuleStatus.ERROR.value,
            "errors": [str(exc)],
        }

    if pools is None:
        return {
            **base,
            "reason": (
                "HISTORICAL_LIMIT_POOL_UNAVAILABLE"
            ),
        }

    return {
        **base,
        "status": ModuleStatus.PARTIAL.value,
        "reason": "HISTORICAL_LIMIT_POOL_ONLY",
        "nonStLimitUpCount": (
            pools["nonStLimitUpCount"]
        ),
        "stLimitUpCount": pools[
            "stLimitUpCount"
        ],
        "nonStLimitDownCount": (
            pools["nonStLimitDownCount"]
        ),
        "stLimitDownCount": pools[
            "stLimitDownCount"
        ],
        "brokenLimitCount": pools[
            "brokenLimitCount"
        ],
        "limitSealRatePct": pools[
            "limitSealRatePct"
        ],
        "maxLimitUpStreak": pools[
            "maxLimitUpStreak"
        ],
        "errors": pools["errors"],
        "warnings": pools["warnings"],
    }


def collect_sentiment(
    trade_date: str,
) -> dict[str, Any]:
    # R12 复核修订 P3-15：dispatch 裸身（外层护栏会截断内层长时限），
    # 当日/历史分支各自装饰。
    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        return _collect_sentiment_historical(trade_date)

    return _collect_sentiment_today(trade_date)


@net_guard(timeout=240.0, retries=1)
def _collect_sentiment_today(
    trade_date: str,
) -> dict[str, Any]:
    yyyymmdd = trade_date.replace("-", "")

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY", "SINA"],
        "riseCount": None,
        "fallCount": None,
        "flatCount": None,
        "suspendedCount": None,
        "nonStLimitUpCount": None,
        "stLimitUpCount": None,
        "nonStLimitDownCount": None,
        "stLimitDownCount": None,
        "brokenLimitCount": None,
        "limitSealRatePct": None,
        "maxLimitUpStreak": None,
        "errors": [],
    }

    counts, used, source_errors = try_sources(
        "spot",
        ["eastmoney"],
        lambda source: _fetch_spot_counts(
            source,
            trade_date,
        ),
    )

    if counts is None:
        result["errors"].append(
            "spot: " + "; ".join(source_errors or ["unknown spot failure"])
        )
    else:
        result["riseCount"] = counts["riseCount"]
        result["fallCount"] = counts["fallCount"]
        result["flatCount"] = counts["flatCount"]
        result["suspendedCount"] = counts["suspendedCount"]
        result["spotSource"] = used.upper() if used else None

        if source_errors:
            result["sourceWarnings"] = source_errors

    import akshare as ak

    try:
        pool = ak.stock_zt_pool_em(
            date=yyyymmdd
        )

        non_st, st = _split_st_pool(pool)
        zt_total = non_st + st

        result["nonStLimitUpCount"] = non_st
        result["stLimitUpCount"] = st
        result["maxLimitUpStreak"] = (
            _max_limit_up_streak(pool)
        )

    except Exception as exc:  # noqa: BLE001
        zt_total = 0
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

        if pool is None or pool.empty:
            result["brokenLimitCount"] = 0
            result["limitSealRatePct"] = 100.0
        else:
            broken = int(len(pool))
            result["brokenLimitCount"] = broken
            result["limitSealRatePct"] = _seal_rate(
                zt_total, broken
            )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"zbgc: {exc}"
        )

    if result["errors"]:
        result["status"] = ModuleStatus.ERROR.value

    return result


def _seal_rate(zt_total: int, broken: int) -> float:
    """Limit-up seal rate = zt/(zt+broken)*100 (eastmoney), rounded to 2.
    0 broken -> 100.0 (no division by zero).
    """
    if broken <= 0:
        return 100.0
    return round(zt_total / (zt_total + broken) * 100.0, 2)


def _max_limit_up_streak(pool) -> str:
    """Max consecutive limit-up boards in zt pool (("连板数", "limit_up_count") col).
    No rows/col -> "0连板".
    """
    if pool is None or pool.empty:
        return "0连板"
    col = _pick_col(pool, ("连板数", "limit_up_count"))
    if col is None:
        return "0连板"
    values = pd.to_numeric(pool[col], errors="coerce").dropna()
    if values.empty:
        return "0连板"
    return f"{int(values.max())}连板"


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
