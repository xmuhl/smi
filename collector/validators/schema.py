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