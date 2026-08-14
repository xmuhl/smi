"""主赛道评分与最终判定。

评分器只消费已经采集完成的指标；
缺失指标必须剔除权重，绝不能用 0 代替 UNKNOWN。
"""

from __future__ import annotations

from typing import Any

from collector.config import load_yaml

def score_tracks(
    tracks_input: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cfg = load_yaml("track-scoring.yaml")
    decision_cfg = cfg["decision"]

    results: list[dict[str, Any]] = []

    for track in tracks_input:
        score, coverage = _score_one(
            track,
            cfg,
        )

        if (
            score is None
            or coverage
            < float(
                decision_cfg["coverage_warn_pct"]
            )
        ):
            decision = "INSUFFICIENT"
        else:
            decision = _decide(
                score,
                decision_cfg,
            )

        results.append(
            {
                **track,
                "score": (
                    round(score, 1)
                    if score is not None
                    else None
                ),
                "coveragePct": round(
                    coverage,
                    1,
                ),
                "decision": decision,
            }
        )

    return results

def _score_one(
    track: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[float | None, float]:
    scoring = cfg["scoring"]
    weights = cfg["weights"]

    parts: list[
        tuple[float | None, float]
    ] = []

    parts.append(
        (
            _score_turnover(
                scoring["turnover_rank"],
                track,
            ),
            float(weights["turnover_rank"]),
        )
    )

    parts.append(
        (
            _score_inflow(
                scoring["main_net_inflow"],
                track,
            ),
            float(weights["main_net_inflow"]),
        )
    )

    parts.append(
        (
            _score_days(
                scoring[
                    "continuous_inflow_days"
                ],
                track.get(
                    "continuousInflowDays"
                ),
            ),
            float(
                weights[
                    "continuous_inflow_days"
                ]
            ),
        )
    )

    parts.append(
        (
            _score_ma(
                scoring["ma_alignment"],
                track.get("maAlignment"),
            ),
            float(weights["ma_alignment"]),
        )
    )

    rps = _to_float(
        track.get("rps60")
    )

    parts.append(
        (
            (
                max(0.0, min(100.0, rps))
                if rps is not None
                else None
            ),
            float(weights["rps60"]),
        )
    )

    parts.append(
        (
            _score_excess(
                scoring["excess_return_20d"],
                track.get(
                    "excessReturn20d"
                ),
            ),
            float(
                weights[
                    "excess_return_20d"
                ]
            ),
        )
    )

    parts.append(
        (
            _score_limit_up_rate(
                scoring["limit_up_rate"],
                track.get("limitUpRate"),
            ),
            float(weights["limit_up"]),
        )
    )

    parts.append(
        (
            _score_ladder(
                scoring[
                    "ladder_completeness"
                ],
                track.get(
                    "ladderCompleteness"
                ),
            ),
            float(
                weights[
                    "ladder_completeness"
                ]
            ),
        )
    )

    parts.append(
        (
            _score_red_ratio(
                scoring["red_stock_ratio"],
                track.get(
                    "redStockRatio"
                ),
            ),
            float(
                weights[
                    "red_stock_ratio"
                ]
            ),
        )
    )

    catalyst = track.get(
        "coreCatalyst"
    )

    parts.append(
        (
            _score_state(
                scoring["core_catalyst"],
                (
                    catalyst.get("state")
                    if isinstance(
                        catalyst,
                        dict,
                    )
                    else catalyst
                ),
            ),
            float(weights["core_catalyst"]),
        )
    )

    earnings = track.get(
        "earningsRealization"
    )

    parts.append(
        (
            _score_state(
                scoring[
                    "earnings_realization"
                ],
                (
                    earnings.get("state")
                    if isinstance(
                        earnings,
                        dict,
                    )
                    else earnings
                ),
            ),
            float(
                weights[
                    "earnings_realization"
                ]
            ),
        )
    )

    valid_weight = sum(
        weight
        for score, weight in parts
        if score is not None
    )

    configured_total = float(
        weights.get(
            "total",
            sum(
                weight
                for _, weight in parts
            ),
        )
    )

    coverage = (
        valid_weight
        / configured_total
        * 100
        if configured_total > 0
        else 0.0
    )

    if valid_weight <= 0:
        return None, coverage

    weighted_total = sum(
        float(score) * weight
        for score, weight in parts
        if score is not None
    )

    return (
        weighted_total / valid_weight,
        coverage,
    )

def _score_turnover(
    table: dict[str, Any],
    track: dict[str, Any],
) -> float | None:
    percentile = _to_float(
        track.get("turnoverPercentile")
    )

    if percentile is None:
        rank = _to_float(
            track.get("turnoverRank")
        )

        universe = _to_float(
            track.get(
                "turnoverUniverseSize"
            )
        )

        if (
            rank is not None
            and universe is not None
            and universe > 0
            and 1 <= rank <= universe
        ):
            percentile = (
                universe - rank + 1
            ) / universe * 100

    if percentile is None:
        return None

    return _percentile_bucket(
        table,
        percentile,
    )

def _score_inflow(
    table: dict[str, Any],
    track: dict[str, Any],
) -> float | None:
    value = _to_float(
        track.get("mainNetInflow")
    )

    if value is None:
        return None

    if abs(value) < 1e-12:
        return _table_score(
            table,
            "near_zero",
        )

    if value < 0:
        return _table_score(
            table,
            "outflow",
        )

    percentile = _to_float(
        track.get(
            "mainNetInflowPercentile"
        )
    )

    if percentile is not None:
        if percentile >= 80:
            return _table_score(
                table,
                "inflow_top20",
            )

        if percentile >= 50:
            return _table_score(
                table,
                "inflow_top20_50",
            )

    return _table_score(
        table,
        "inflow_rest",
    )

def _score_days(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    number = _to_float(value)

    if number is None:
        return None

    days = int(number)

    if days >= 5:
        key = ">=5"
    elif days >= 3:
        key = "3~4"
    elif days == 2:
        key = "2"
    elif days == 1:
        key = "1"
    else:
        key = "0"

    return _table_score(
        table,
        key,
    )

def _score_ma(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    if not isinstance(value, dict):
        return None

    close = _to_float(
        value.get("close")
    )
    ma5 = _to_float(
        value.get("ma5")
    )
    ma10 = _to_float(
        value.get("ma10")
    )
    ma20 = _to_float(
        value.get("ma20")
    )

    if all(
        item is not None
        for item in (
            close,
            ma5,
            ma10,
            ma20,
        )
    ):
        assert close is not None
        assert ma5 is not None
        assert ma10 is not None
        assert ma20 is not None

        if (
            close > ma5
            and ma5 > ma10
            and ma10 > ma20
        ):
            key = "close_gt_ma5_10_20"

        elif (
            close > ma5
            and close > ma10
            and close > ma20
        ):
            key = "close_gt_ma_all"

        elif sum(
            (
                close > ma5,
                close > ma10,
                close > ma20,
            )
        ) >= 2:
            key = "close_gt_two_ma"

        else:
            key = "other"

        return _table_score(
            table,
            key,
        )

    if value.get("bullish") is True:
        return _table_score(
            table,
            "close_gt_ma5_10_20",
        )

    return None

def _score_excess(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    number = _to_float(value)

    if number is None:
        return None

    if number >= 5:
        key = ">=+5%"
    elif number >= 2:
        key = "+2%~+5%"
    elif number >= 0:
        key = "0~+2%"
    elif number >= -2:
        key = "-2%~0"
    else:
        key = "<-2%"

    return _table_score(
        table,
        key,
    )

def _score_limit_up_rate(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    number = _to_float(value)

    if number is None:
        return None

    if number >= 3:
        key = ">=3%"
    elif number >= 1.5:
        key = "1.5%~3%"
    elif number >= 0.5:
        key = "0.5%~1.5%"
    elif number > 0:
        key = ">0"
    else:
        key = "0"

    return _table_score(
        table,
        key,
    )

def _score_ladder(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    if not isinstance(value, dict):
        return None

    first = _to_float(
        value.get("firstBoardCount")
    )
    second = _to_float(
        value.get("twoBoardCount")
    )
    third_plus = _to_float(
        value.get("threePlusCount")
    )

    if all(
        item is None
        for item in (
            first,
            second,
            third_plus,
        )
    ):
        return None

    first = first or 0
    second = second or 0
    third_plus = third_plus or 0

    if (
        third_plus >= 1
        and second >= 1
        and first >= 1
    ):
        key = "3板以上有梯队"
    elif second >= 1 and first >= 1:
        key = "2板+首板"
    elif first >= 1:
        key = "仅首板"
    else:
        key = "无涨停"

    return _table_score(
        table,
        key,
    )

def _score_red_ratio(
    table: dict[str, Any],
    value: Any,
) -> float | None:
    number = _to_float(value)

    if number is None:
        return None

    if number >= 70:
        key = ">=70%"
    elif number >= 60:
        key = "60%~70%"
    elif number >= 50:
        key = "50%~60%"
    elif number >= 40:
        key = "40%~50%"
    else:
        key = "<40%"

    return _table_score(
        table,
        key,
    )

def _score_state(
    table: dict[str, Any],
    state: Any,
) -> float | None:
    if state is None:
        return None

    key = str(state)

    if key == "UNKNOWN":
        return None

    value = table.get(key)

    if value is None:
        return None

    return float(value)

def _percentile_bucket(
    table: dict[str, Any],
    percentile: float,
) -> float:
    percentile = max(
        0.0,
        min(100.0, percentile),
    )

    if percentile >= 80:
        key = "top20pct"
    elif percentile >= 60:
        key = "pct20_40"
    elif percentile >= 40:
        key = "pct40_60"
    elif percentile >= 20:
        key = "pct60_80"
    else:
        key = "bottom20pct"

    return _table_score(
        table,
        key,
    )

def _table_score(
    table: dict[str, Any],
    key: str,
) -> float:
    value = table.get(key)

    if value is None:
        raise ValueError(
            f"scoring key missing: {key}"
        )

    return float(value)

def _to_float(
    value: Any,
) -> float | None:
    import math

    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _decide(
    score: float,
    decision: dict[str, Any],
) -> str:
    if score >= float(
        decision["pass_min"]
    ):
        return "PASS"

    if score >= float(
        decision["watch_min"]
    ):
        return "WATCH"

    return "AVOID"
