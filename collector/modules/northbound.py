"""模块 6：北向资金。

V1 自动化仅可靠采集 HKEX 最近一期季度持仓。
2024-08-19 后旧式日度净流入字段保持 UNAVAILABLE。

北向持仓披露采用 OFFICIAL_REPLACEMENT 口径：
- HKEX 每季度结束后第 5 个沪深港通交易日披露上季末持仓；
- publishedAt 用 collector.calendar 交易日历计算（离线，不依赖网络）；
- 未到披露日则 fail-closed（NOT_YET_PUBLISHED_AT_TARGET_DATE），不伪造。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

from collector import calendar as _cal
from collector.config import load_yaml
from collector.status import ModuleStatus

DISCLOSURE_CHANGE_DATE = date(2024, 8, 19)

# HKEX 官方规则：季度结束后第 5 个沪深港通交易日披露上季末持仓。
DISCLOSURE_LAG_TRADING_DAYS = 5

# 最多向后搜索的日历天数（含节假日），防死循环。
_MAX_SEARCH_DAYS = 800


def _fifth_trading_day_after(as_of: date) -> date | None:
    """返回 asOf 之后第 DISCLOSURE_LAG_TRADING_DAYS 个交易日（严格晚于 asOf）。"""
    cursor = as_of
    remaining = DISCLOSURE_LAG_TRADING_DAYS

    for _ in range(_MAX_SEARCH_DAYS):
        cursor = cursor + timedelta(days=1)

        if _cal.is_trading_day(
            cursor,
            fallback_weekday=True,
        ):
            remaining -= 1

            if remaining <= 0:
                return cursor

    return None


def collect_northbound(
    trade_date: str,
) -> dict[str, Any]:
    target = date.fromisoformat(trade_date)

    if target < DISCLOSURE_CHANGE_DATE:
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": trade_date,
            "mode": "PRE_20240819_NOT_IMPLEMENTED",
            "sourceSystem": "HKEX",
            "source": ["HKEX"],
            "reason": "PRE_20240819_NET_FLOW_HISTORY_NOT_IMPLEMENTED",
            "dailyTurnover": {
                "status": ModuleStatus.UNAVAILABLE.value,
                "value": None,
            },
            "activeSecurities": {
                "status": ModuleStatus.UNAVAILABLE.value,
                "items": [],
            },
            "legacyNetFlow": {
                "status": ModuleStatus.UNAVAILABLE.value,
                "reason": "HISTORICAL_ADAPTER_NOT_IMPLEMENTED",
            },
            "overlap": {
                "status": ModuleStatus.UNAVAILABLE.value,
                "items": [],
            },
            "quarterlyHolding": {
                "status": ModuleStatus.UNAVAILABLE.value,
                "asOf": None,
                "publishedAt": None,
                "items": [],
            },
        }

    rules = load_yaml("market-rules.yaml")
    north_cfg = rules.get("northbound", {})

    urls = {
        "sh": north_cfg["sh_url"],
        "sz": north_cfg["sz_url"],
    }

    result: dict[str, Any] = {
        "status": ModuleStatus.PENDING.value,
        "dataDate": trade_date,
        "mode": "POST_20240819_OFFICIAL_REPLACEMENT",
        "sourceSystem": "HKEX",
        "source": ["HKEX"],
        "dailyTurnover": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "value": None,
            "reason": "V1_NO_STABLE_AUTOMATION",
        },
        "activeSecurities": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "items": [],
            "reason": "V1_NO_STABLE_AUTOMATION",
        },
        "legacyNetFlow": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "reason": "DISCLOSURE_RULE_CHANGED",
        },
        "overlap": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "items": [],
            "reason": "DEPENDENCY_UNAVAILABLE",
        },
        "quarterlyHolding": {
            "status": ModuleStatus.PENDING.value,
            "asOf": None,
            "publishedAt": None,
            "items": [],
        },
        "errors": [],
    }

    all_items: list[dict[str, Any]] = []
    dates: dict[str, str | None] = {}

    for market, url in urls.items():
        try:
            items, share_date = _fetch_quarterly_holding(url)

            if not items:
                raise ValueError(
                    "HKEX holding table parsed as empty"
                )

            dates[market] = share_date

            all_items.extend(
                {
                    **item,
                    "market": market,
                }
                for item in items
            )

        except Exception as exc:  # noqa: BLE001
            result["errors"].append(
                f"{market}: {exc}"
            )

    if result["errors"]:
        result["status"] = ModuleStatus.ERROR.value
        result["quarterlyHolding"] = {
            "status": ModuleStatus.ERROR.value,
            "asOf": None,
            "publishedAt": None,
            "items": [],
        }
        return result

    unique_dates = {
        value
        for value in dates.values()
        if value is not None
    }

    if len(unique_dates) != 1:
        result["status"] = ModuleStatus.ERROR.value
        result["errors"].append(
            f"HKEX_SH_SZ_DATE_MISMATCH:{dates}"
        )
        result["quarterlyHolding"] = {
            "status": ModuleStatus.ERROR.value,
            "asOf": None,
            "publishedAt": None,
            "items": [],
        }
        return result

    as_of = next(iter(unique_dates))

    if as_of > trade_date:
        result["status"] = ModuleStatus.UNAVAILABLE.value
        result["quarterlyHolding"] = {
            "status": ModuleStatus.UNAVAILABLE.value,
            "asOf": None,
            "publishedAt": None,
            "items": [],
            "reason": "LATEST_QUARTER_IS_AFTER_TARGET_DATE",
        }
        return result

    try:
        as_of_date = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        result["status"] = ModuleStatus.UNAVAILABLE.value
        result["quarterlyHolding"] = {
            "status": ModuleStatus.UNAVAILABLE.value,
            "asOf": as_of,
            "publishedAt": None,
            "items": [],
            "reason": "UNPARSABLE_AS_OF_DATE",
        }
        result["errors"].append(
            f"UNPARSABLE_AS_OF_DATE:{as_of}"
        )
        return result

    published_at = _fifth_trading_day_after(as_of_date)

    if published_at is None:
        result["status"] = ModuleStatus.UNAVAILABLE.value
        result["quarterlyHolding"] = {
            "status": ModuleStatus.UNAVAILABLE.value,
            "asOf": as_of,
            "publishedAt": None,
            "items": [],
            "reason": "PUBLICATION_DATE_UNRESOLVABLE",
        }
        result["errors"].append(
            f"PUBLICATION_DATE_UNRESOLVABLE:{as_of}"
        )
        return result

    published_at_iso = published_at.isoformat()

    if trade_date < published_at_iso:
        result["status"] = ModuleStatus.UNAVAILABLE.value
        result["quarterlyHolding"] = {
            "status": ModuleStatus.UNAVAILABLE.value,
            "asOf": as_of,
            "publishedAt": published_at_iso,
            "items": [],
            "reason": "NOT_YET_PUBLISHED_AT_TARGET_DATE",
        }
        return result

    result["status"] = ModuleStatus.FINAL.value
    result["quarterlyHolding"] = {
        "status": ModuleStatus.FINAL.value,
        "asOf": as_of,
        "publishedAt": published_at_iso,
        "items": all_items,
    }

    return result


def _fetch_quarterly_holding(
    url: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """直接 GET HKEX 页面并解析当前季度持仓。"""
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; SMI/1.0)"
            )
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "lxml",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    match = re.search(
        r"Shareholding Date\s*[:：]?\s*"
        r"("
        r"\d{4}/\d{2}/\d{2}"
        r"|"
        r"\d{2}/\d{2}/\d{4}"
        r")",
        text,
        flags=re.IGNORECASE,
    )

    share_date = (
        _convert_hk_date(match.group(1))
        if match
        else None
    )

    target_table = None

    for table in soup.find_all("table"):
        table_text = table.get_text(
            " ",
            strip=True,
        )

        if (
            "Stock Code" in table_text
            and "Shareholding in CCASS"
            in table_text
        ):
            target_table = table
            break

    if target_table is None:
        raise ValueError(
            "HKEX shareholding table not found"
        )

    rows: list[dict[str, Any]] = []

    for tr in target_table.find_all("tr"):
        cells = [
            td.get_text(
                " ",
                strip=True,
            )
            for td in tr.find_all("td")
        ]

        if len(cells) < 4:
            continue

        hkex_code = _remove_label(
            cells[0],
            "Stock Code",
        )

        raw_name = _remove_label(
            cells[1],
            "Name",
        )

        shareholding = _remove_label(
            cells[2],
            "Shareholding in CCASS",
        )

        pct_text = cells[3]

        pct_match = re.search(
            r"(-?\d+(?:\.\d+)?)%",
            pct_text,
        )

        pct = (
            f"{pct_match.group(1)}%"
            if pct_match
            else None
        )

        a_code_match = re.search(
            r"\(\s*A\s*#\s*(\d{6})\s*\)",
            raw_name,
            flags=re.IGNORECASE,
        )

        a_code = (
            a_code_match.group(1)
            if a_code_match
            else hkex_code
        )

        clean_name = re.sub(
            r"\s*\(\s*A\s*#\s*\d{6}\s*\)\s*$",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()

        rows.append(
            {
                "code": a_code,
                "hkexStockCode": hkex_code,
                "name": clean_name,
                "shareholding": shareholding,
                "pctOfIssued": pct,
            }
        )

    return rows, share_date


def _remove_label(
    value: str,
    label: str,
) -> str:
    return re.sub(
        rf"^\s*{re.escape(label)}\s*[:：]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


def _convert_hk_date(
    hk_date: str,
) -> str | None:
    value = hk_date.strip()

    match = re.fullmatch(
        r"(\d{4})/(\d{2})/(\d{2})",
        value,
    )

    if match:
        return (
            f"{match.group(1)}-"
            f"{match.group(2)}-"
            f"{match.group(3)}"
        )

    match = re.fullmatch(
        r"(\d{2})/(\d{2})/(\d{4})",
        value,
    )

    if match:
        return (
            f"{match.group(3)}-"
            f"{match.group(2)}-"
            f"{match.group(1)}"
        )

    return None
