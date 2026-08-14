"""RPS60：60 个交易日收益率的横截面百分位。"""

from __future__ import annotations

import math

import pandas as pd

def compute_rps60(
    returns60: dict[str, float],
) -> dict[str, float]:
    """过滤非有限值后计算横截面百分位。"""
    clean = {
        str(key): float(value)
        for key, value in returns60.items()
        if value is not None
        and math.isfinite(float(value))
    }

    if not clean:
        return {}

    series = pd.Series(
        clean,
        dtype="float64",
    )

    rank = series.rank(
        pct=True,
        method="average",
    ) * 100

    return {
        str(key): round(
            float(value),
            1,
        )
        for key, value in rank.items()
    }

def compute_return60(
    closes: list[float],
) -> float | None:
    """严格取最后 61 个交易日收盘点计算 T-60 → T。"""
    if len(closes) < 61:
        return None

    window = closes[-61:]

    normalized: list[float] = []

    for value in window:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        normalized.append(number)

    start = normalized[0]
    end = normalized[-1]

    if start <= 0:
        return None

    return end / start - 1
