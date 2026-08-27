"""SMI 每日快照最低限度运行时结构校验。"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any

from collector.status import ModuleStatus

EXPECTED_MODULES = {
    "marketIndex",
    "turnover",
    "sentiment",
    "sectorPerformance",
    "fundFlow",
    "northbound",
    "margin",
    "tracks",
    "summary",
}

LIVE_INDEX_CODES = {
    "000001",
    "399001",
    "399006",
    "000688",
    "000300",
    "899050",
    "399311",
    "399303",
}

VALID_STATUSES = {
    item.value
    for item in ModuleStatus
}

def validate_snapshot(
    snapshot: dict[str, Any],
) -> None:
    errors: list[str] = []

    if snapshot.get("schemaVersion") != "1.1":
        errors.append(
            "unsupported schemaVersion: "
            f"{snapshot.get('schemaVersion')}"
        )

    try:
        trade_date = date.fromisoformat(
            str(snapshot["tradeDate"])
        ).isoformat()
    except (KeyError, ValueError):
        errors.append("invalid tradeDate")
        trade_date = ""

    revision = snapshot.get("revision")

    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
    ):
        errors.append(
            "revision must be integer >= 1"
        )

    modules = snapshot.get("modules")

    _validate_stock_codes(modules)

    if not isinstance(modules, dict):
        errors.append("modules must be object")
        modules = {}

    module_names = set(modules.keys())

    if module_names != EXPECTED_MODULES:
        errors.append(
            "module set mismatch: "
            f"{sorted(module_names)}"
        )

    statuses: list[str] = []

    for name, module in modules.items():
        if not isinstance(module, dict):
            errors.append(
                f"{name}: module not object"
            )
            continue

        status = module.get("status")
        statuses.append(str(status))

        if status not in VALID_STATUSES:
            errors.append(
                f"{name}: invalid status {status}"
            )
            continue

        if status == ModuleStatus.PARTIAL.value:
            _validate_partial_module(
                name,
                module,
                trade_date,
                errors,
            )

        data_date = module.get("dataDate")

        if (
            status == ModuleStatus.FINAL.value
            and data_date != trade_date
        ):
            errors.append(
                f"{name}: FINAL dataDate "
                f"{data_date} != tradeDate "
                f"{trade_date}"
            )

    market_index = modules.get(
        "marketIndex",
        {},
    )

    if (
        market_index.get("status")
        == ModuleStatus.FINAL.value
        and not snapshot.get(
            "meta",
            {},
        ).get("legacy", False)
    ):
        items = market_index.get("items")

        if not isinstance(items, list):
            errors.append(
                "marketIndex.items must be list"
            )
        else:
            codes = {
                str(item.get("code"))
                for item in items
                if isinstance(item, dict)
            }

            if codes != LIVE_INDEX_CODES:
                errors.append(
                    "marketIndex code set mismatch"
                )

    turnover = modules.get(
        "turnover",
        {},
    )

    if (
        turnover.get("status")
        == ModuleStatus.FINAL.value
    ):
        if turnover.get("unit") != "亿元":
            errors.append(
                "turnover.unit must be 亿元"
            )

        turnover_today = turnover.get(
            "turnoverToday"
        )

        if (
            not _is_finite_number(
                turnover_today
            )
            or float(turnover_today) <= 0
        ):
            errors.append(
                "turnover.turnoverToday "
                "must be finite number > 0"
            )

        legacy = snapshot.get(
            "meta",
            {},
        ).get(
            "legacy",
            False,
        )

        # R9.2：非 Legacy 的 FINAL turnover 必须满足口径血缘深度契约
        if not legacy:
            _validate_turnover_lineage(
                turnover,
                errors,
            )

    northbound = modules.get(
        "northbound",
        {},
    )
    mode = northbound.get("mode")

    if (
        mode
        == "POST_20240819_QUARTERLY_ONLY"
    ):
        holding = northbound.get(
            "quarterlyHolding"
        )

        if not isinstance(
            holding,
            dict,
        ):
            errors.append(
                "northbound.quarterlyHolding "
                "missing"
            )

    if (
        mode
        == "POST_20240819_LEGACY_IMPORTED"
    ):
        if not isinstance(
            northbound.get(
                "legacyImportedFields"
            ),
            dict,
        ):
            errors.append(
                "northbound."
                "legacyImportedFields missing"
            )

    margin = modules.get(
        "margin",
        {},
    )

    if (
        margin.get("status")
        == ModuleStatus.FINAL.value
    ):
        if margin.get("unit") != "亿元":
            errors.append(
                "margin.unit must be 亿元"
            )

        for field in (
            "financingBalance",
            "securitiesLendingBalance",
            "marginBalance",
        ):
            value = margin.get(field)

            if not _is_finite_number(value):
                errors.append(
                    f"margin.{field} "
                    "must be finite number"
                )
                continue

            if float(value) < 0:
                errors.append(
                    f"margin.{field} "
                    "must be >= 0"
                )

        financing = margin.get(
            "financingBalance"
        )
        lending = margin.get(
            "securitiesLendingBalance"
        )
        total = margin.get(
            "marginBalance"
        )

        if all(
            _is_finite_number(value)
            for value in (
                financing,
                lending,
                total,
            )
        ):
            # 两融余额一致性采用固定绝对容差 0.05 亿元。
            # 用 Decimal 做业务口径比较，避免二进制 float
            # 对"恰好 0.05"的十进制差值产生误判（R5-P3-01）。
            expected = (
                Decimal(str(financing))
                + Decimal(str(lending))
            )
            actual = Decimal(str(total))
            tolerance = Decimal("0.05")

            if abs(
                actual - expected
            ) > tolerance:
                errors.append(
                    "margin.marginBalance "
                    "!= financingBalance + "
                    "securitiesLendingBalance "
                    f"(actual={actual}, "
                    f"expected={expected})"
                )

    margin_reference = margin.get(
        "latestPublishedReference"
    )

    if (
        margin_reference is not None
        and margin.get("status")
        != ModuleStatus.FINAL.value
    ):
        _validate_margin_reference(
            margin_reference,
            trade_date,
            errors,
        )
    elif (
        margin_reference is not None
        and margin.get("status")
        == ModuleStatus.FINAL.value
    ):
        errors.append(
            "margin: FINAL must not carry "
            "latestPublishedReference"
        )

    summary = modules.get(
        "summary",
        {},
    )

    if (
        summary.get("status")
        == ModuleStatus.FINAL.value
    ):
        for field in (
            "indexAndTurnover",
            "sentiment",
            "fundFlow",
            "margin",
            "trackConclusion",
            "marketEnvironment",
            "northbound",
            "riskWarning",
        ):
            if not isinstance(
                summary.get(field),
                str,
            ):
                errors.append(
                    f"summary.{field} "
                    "missing/invalid"
                )

    expected_overall = (
        _expected_overall_status(
            statuses
        )
    )

    if (
        snapshot.get("overallStatus")
        != expected_overall
    ):
        errors.append(
            "overallStatus mismatch: "
            f"actual="
            f"{snapshot.get('overallStatus')} "
            f"expected={expected_overall}"
        )

    _validate_finite(
        snapshot,
        "$",
        errors,
    )

    if errors:
        raise ValueError(
            "snapshot validation failed: "
            + "; ".join(errors)
        )

def _is_nonnegative_int(
    value: Any,
) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _validate_partial_module(
    name: str,
    module: dict[str, Any],
    trade_date: str,
    errors: list[str],
) -> None:
    """V1 PARTIAL：历史 sentiment（R8-P2-01）；R10 起允许受约束 tracks sufficient；
    P1-003 起允许受约束 fundFlow（历史个股两榜单免费源不可行 → PARTIAL）。"""
    if name == "tracks":
        if module.get("dataDate") != trade_date:
            errors.append(
                "tracks: PARTIAL dataDate "
                f"{module.get('dataDate')} != tradeDate {trade_date}"
            )

        # R13-P2-02：三态 coverage 门禁——TRACKS_SUFFICIENT(READY) 要求
        # coverage>=target；TRACKS_DEGRADED 允许 [floor, target) 区间。
        # 阈值以 config/track-scoring.yaml 为单一真源。
        from collector.config import load_yaml

        _dcfg = load_yaml("track-scoring.yaml").get("decision", {}) or {}
        _target = float(_dcfg.get("coverage_target_pct", 80.0))
        _floor = float(_dcfg.get("coverage_hard_floor_pct", 65.0))

        decision = module.get("decision")
        if decision not in ("TRACKS_SUFFICIENT", "TRACKS_DEGRADED"):
            errors.append(
                "tracks: PARTIAL decision must be TRACKS_SUFFICIENT "
                "or TRACKS_DEGRADED"
            )

        coverage = module.get("coveragePct")

        if (
            not _is_finite_number(coverage)
            or float(coverage) < _floor
            or float(coverage) > 100.0
        ):
            errors.append(
                f"tracks: PARTIAL coveragePct must be finite within "
                f"[{_floor}, 100]"
            )
        elif decision == "TRACKS_SUFFICIENT" and float(coverage) < _target:
            errors.append(
                f"tracks: TRACKS_SUFFICIENT requires coveragePct >= {_target}"
            )
        elif decision == "TRACKS_DEGRADED" and float(coverage) >= _target:
            errors.append(
                f"tracks: TRACKS_DEGRADED requires coveragePct < {_target}"
            )

        return

    if name == "fundFlow":
        # P1-003：历史回补个股两榜单无免费源 → PARTIAL。
        # dataDate==tradeDate 且 reason=STOCK_HISTORICAL_UNAVAILABLE 约束。
        if module.get("dataDate") != trade_date:
            errors.append(
                "fundFlow: PARTIAL dataDate "
                f"{module.get('dataDate')} != tradeDate {trade_date}"
            )

        if (
            module.get("reason")
            != "STOCK_HISTORICAL_UNAVAILABLE"
        ):
            errors.append(
                "fundFlow: PARTIAL reason must be "
                "STOCK_HISTORICAL_UNAVAILABLE"
            )

        return

    if name != "sentiment":
        errors.append(
            f"{name}: PARTIAL is not supported"
        )
        return

    if module.get("dataDate") != trade_date:
        errors.append(
            "sentiment: PARTIAL dataDate "
            f"{module.get('dataDate')} != tradeDate "
            f"{trade_date}"
        )

    # 历史窗口日两种互斥 PARTIAL 形态：LIMIT_POOL_ONLY=涨停池可得
    # （R8-P2-01 原契约；涨跌家数原强制 null，2026-08-24 gildata 回补
    # 后允许共存，按可选字段校验）；LIMIT_POOL_UNAVAILABLE=仅涨跌家数
    # （gildata 回补引入，如 07-20~07-24 五日），涨停池派生字段全缺。
    # 域外 reason 一律拒绝。
    reason = module.get("reason")
    breadth_fields = ("riseCount", "fallCount", "flatCount")
    pool_fields = (
        "nonStLimitUpCount",
        "stLimitUpCount",
        "nonStLimitDownCount",
        "stLimitDownCount",
        "brokenLimitCount",
    )

    if reason == "HISTORICAL_LIMIT_POOL_ONLY":
        up_values = (
            module.get("nonStLimitUpCount"),
            module.get("stLimitUpCount"),
        )

        if not all(
            _is_nonnegative_int(value)
            for value in up_values
        ):
            errors.append(
                "sentiment: PARTIAL limit-up counts "
                "must be non-negative integers"
            )
        elif sum(up_values) <= 0:
            errors.append(
                "sentiment: PARTIAL must contain "
                "at least one limit-up record"
            )

        for field in breadth_fields + ("suspendedCount",):
            value = module.get(field)

            if (
                value is not None
                and not _is_nonnegative_int(value)
            ):
                errors.append(
                    f"sentiment.{field} must be "
                    "null or non-negative integer"
                )
    elif reason == "HISTORICAL_LIMIT_POOL_UNAVAILABLE":
        breadth_values = [
            module.get(field) for field in breadth_fields
        ]

        if not all(
            _is_nonnegative_int(value)
            for value in breadth_values
        ):
            errors.append(
                "sentiment: PARTIAL breadth counts "
                "must be non-negative integers"
            )
        elif sum(breadth_values) <= 0:
            errors.append(
                "sentiment: PARTIAL must contain "
                "at least one breadth record"
            )

        suspended = module.get("suspendedCount")

        if (
            suspended is not None
            and not _is_nonnegative_int(suspended)
        ):
            errors.append(
                "sentiment.suspendedCount must be "
                "null or non-negative integer"
            )

        for field in pool_fields:
            if module.get(field) is not None:
                errors.append(
                    f"sentiment.{field} must be null "
                    "for HISTORICAL_LIMIT_POOL_UNAVAILABLE"
                )
    else:
        errors.append(
            "sentiment: invalid PARTIAL reason"
        )

    for field in pool_fields:
        value = module.get(field)

        if (
            value is not None
            and not _is_nonnegative_int(value)
        ):
            errors.append(
                f"sentiment.{field} must be "
                "null or non-negative integer"
            )


def _validate_margin_reference(
    reference: dict[str, Any],
    trade_date: str,
    errors: list[str],
) -> None:
    """D0 两融参考值深度契约（R7-P1 / R6-P1-04）。

    状态机契约（与 modules/margin._latest_published_reference 严格配对）：
    - 仅允许在 margin.status != FINAL 时出现（FINAL 本身即 T 日真实值）；
    - dataDate 必须是严格早于 tradeDate 的合法规范 ISO 日期；
    - 三项余额必须是有限数值（排除 bool）且 >= 0；
    - marginBalance ≈ financingBalance + securitiesLendingBalance
      （绝对容差 0.05 亿元，与 collector 端同口径，R10.2-N04）。

    边界说明：本函数保持纯函数、不读磁盘。参考值与所属快照的身份
    一致性（dataDate 确实取自该日已落盘 FINAL margin）由采集端
    _latest_published_reference 的"只读已落盘 FINAL 快照、倒序首个命中、
    找不到即 None"查找保证（fail-closed），validator 不重复校验。
    """
    if not isinstance(reference, dict):
        errors.append(
            "margin.latestPublishedReference "
            "must be object"
        )
        return

    data_date = reference.get("dataDate")

    try:
        parsed = date.fromisoformat(
            str(data_date)
        ).isoformat()
    except (KeyError, ValueError, TypeError):
        errors.append(
            "margin reference: invalid dataDate"
        )
        return

    if data_date != parsed:
        errors.append(
            "margin reference: non-canonical dataDate"
        )
        return

    try:
        trade = date.fromisoformat(
            str(trade_date)
        )
    except ValueError:
        trade = None

    if (
        trade is not None
        and date.fromisoformat(data_date) >= trade
    ):
        errors.append(
            "margin reference dataDate must be "
            "strictly before tradeDate"
        )
        return

    for field in (
        "financingBalance",
        "securitiesLendingBalance",
        "marginBalance",
    ):
        value = reference.get(field)

        if (
            isinstance(value, bool)
            or not _is_finite_number(value)
        ):
            errors.append(
                f"margin reference.{field} "
                "must be finite number"
            )
            continue

        if float(value) < 0:
            errors.append(
                f"margin reference.{field} "
                "must be >= 0"
            )

    financing = reference.get(
        "financingBalance"
    )
    lending = reference.get(
        "securitiesLendingBalance"
    )
    total = reference.get("marginBalance")

    if (
        _is_finite_number(financing)
        and not isinstance(financing, bool)
        and _is_finite_number(lending)
        and not isinstance(lending, bool)
        and _is_finite_number(total)
        and not isinstance(total, bool)
    ):
        expected = Decimal(str(financing)) + Decimal(str(lending))
        actual = Decimal(str(total))

        if abs(actual - expected) > Decimal("0.05"):
            errors.append(
                "margin reference: marginBalance must "
                "equal financingBalance + "
                "securitiesLendingBalance "
                "(tolerance 0.05)"
            )


def _validate_turnover_lineage(
    turnover: dict[str, Any],
    errors: list[str],
) -> None:
    """非 Legacy FINAL turnover 的口径与比较状态深度一致性（R9.2-N4）。

    状态机契约（与 turnover._turnover_comparison 严格配对）：
    - COMPARABLE: method 与 previousMethod 均为 V1，
      环比三字段有限且 previous>0，volumeState 为三态之一；
    - PREVIOUS_UNAVAILABLE: previousMethod 为 null，
      环比字段全 null，volumeState=UNKNOWN；
    - PREVIOUS_METHOD_MISMATCH: previousMethod 非 null 且 != V1，
      环比字段全 null，volumeState=UNKNOWN。
    """
    method = turnover.get("method")

    if method != "SH_SZ_A_NO_B_NO_BJ_V1":
        errors.append(
            "turnover.method must be "
            "SH_SZ_A_NO_B_NO_BJ_V1"
        )
        return

    comparison_status = turnover.get("comparisonStatus")

    if comparison_status not in {
        "COMPARABLE",
        "PREVIOUS_METHOD_MISMATCH",
        "PREVIOUS_UNAVAILABLE",
    }:
        errors.append(
            "turnover.comparisonStatus "
            f"invalid: {comparison_status}"
        )
        return

    previous_method = turnover.get("previousMethod")
    previous = turnover.get("turnoverPrevious")
    delta = turnover.get("turnoverDelta")
    change_pct = turnover.get("turnoverChangePct")
    volume_state = turnover.get("volumeState")

    if comparison_status == "COMPARABLE":
        if previous_method != "SH_SZ_A_NO_B_NO_BJ_V1":
            errors.append(
                "turnover COMPARABLE requires "
                "previousMethod SH_SZ_A_NO_B_NO_BJ_V1"
            )

        if (
            not _is_finite_number(previous)
            or float(previous) <= 0
        ):
            errors.append(
                "turnoverPrevious must be finite > 0 "
                "when COMPARABLE"
            )

        if not _is_finite_number(delta):
            errors.append(
                "turnoverDelta must be finite "
                "when COMPARABLE"
            )

        if not _is_finite_number(change_pct):
            errors.append(
                "turnoverChangePct must be finite "
                "when COMPARABLE"
            )

        if volume_state not in {
            "EXPANSION",
            "CONTRACTION",
            "FLAT",
        }:
            errors.append(
                "turnover.volumeState invalid "
                "when COMPARABLE"
            )

        return

    if (
        previous is not None
        or delta is not None
        or change_pct is not None
    ):
        errors.append(
            "non-COMPARABLE turnover must not "
            "expose comparison numbers"
        )

    if volume_state != "UNKNOWN":
        errors.append(
            "non-COMPARABLE turnover volumeState "
            "must be UNKNOWN"
        )

    if (
        comparison_status
        == "PREVIOUS_UNAVAILABLE"
        and previous_method is not None
    ):
        errors.append(
            "PREVIOUS_UNAVAILABLE requires "
            "previousMethod null"
        )

    if comparison_status == "PREVIOUS_METHOD_MISMATCH":
        if (
            previous_method is None
            or previous_method == method
        ):
            errors.append(
                "PREVIOUS_METHOD_MISMATCH requires "
                "different previousMethod"
            )


def _validate_finite(
    value: Any,
    path: str,
    errors: list[str],
) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            errors.append(
                f"{path}: non-finite number"
            )
        return

    if isinstance(value, dict):
        for key, child in value.items():
            _validate_finite(
                child,
                f"{path}.{key}",
                errors,
            )
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_finite(
                child,
                f"{path}[{index}]",
                errors,
            )

def _expected_overall_status(
    statuses: list[str],
) -> str:
    if any(
        status == ModuleStatus.ERROR.value
        for status in statuses
    ):
        return "PARTIAL_ERROR"

    if any(
        status == ModuleStatus.PENDING.value
        for status in statuses
    ):
        return "PARTIAL_PENDING"

    if statuses and all(
        status == ModuleStatus.FINAL.value
        for status in statuses
    ):
        return ModuleStatus.FINAL.value

    return "PARTIAL"

def _is_finite_number(
    value: Any,
) -> bool:
    if isinstance(value, bool):
        return False

    if not isinstance(
        value,
        (int, float),
    ):
        return False

    return math.isfinite(
        float(value)
    )


def _validate_stock_codes(modules) -> None:
    """R7-P2-02：fundFlow 个股代码必须是标准 6 位数字。"""
    if not isinstance(modules, dict):
        return

    import re

    flow = modules.get("fundFlow", {})
    if not isinstance(flow, dict):
        return

    bad: list[str] = []

    for group in (
        "stockInflowTop10",
        "stockOutflowTop10",
    ):
        for item in flow.get(group, []) or []:
            code = item.get("code") if isinstance(item, dict) else None
            if code is None or code == "":
                continue
            if not re.fullmatch(r"\d{6}", str(code)):
                bad.append(f"{group}:{code}")

    if bad:
        raise ValueError(
            "invalid fundFlow stock codes: " + ", ".join(bad[:5])
        )