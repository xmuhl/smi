"""交易日历：年度本地快照优先，官方休市配置作为安全回退。"""

from __future__ import annotations

import json
from datetime import date, timedelta

from collector.config import CALENDAR_DIR, load_yaml
from collector.schema import now_iso


def _calendar_file(year: int):
    return CALENDAR_DIR / f"{year}.json"


def load_calendar(year: int) -> list[str]:
    path = _calendar_file(year)

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        dates = data.get("dates", [])
        return sorted(str(value) for value in dates)

    except (OSError, ValueError, TypeError):
        return []


def save_calendar(
    year: int,
    dates: list[str],
    source: list[str] | None = None,
) -> None:
    path = _calendar_file(year)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "year": year,
        "source": source or ["LOCAL_VERIFICATION"],
        "updatedAt": now_iso(),
        "dates": sorted(set(dates)),
    }

    tmp = path.with_suffix(".tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    tmp.replace(path)


def _configured_closed_dates(year: int) -> set[str]:
    """读取经人工核对的交易所年度休市日期。"""
    rules = load_yaml("market-rules.yaml")
    calendar_cfg = rules.get("calendar", {})

    values = calendar_cfg.get("closed_dates", [])

    return {
        str(value)
        for value in values
        if str(value).startswith(f"{year}-")
    }


def _fallback_is_trading_day(day: date) -> bool:
    """没有年度快照时，仅使用周末 + 已配置官方休市日。"""
    if day.weekday() >= 5:
        return False

    return day.isoformat() not in _configured_closed_dates(day.year)


def is_trading_day(
    day: date,
    fallback_weekday: bool = True,
) -> bool:
    """判断交易日。

    1. 年度本地快照存在：以快照为唯一真源；
    2. 快照不存在：若允许 fallback，则使用周末 + 官方休市日配置；
    3. close-snapshot 仍需通过市场事实二次校验。
    """
    dates = load_calendar(day.year)

    if dates:
        return day.isoformat() in set(dates)

    if fallback_weekday:
        return _fallback_is_trading_day(day)

    return False


def previous_trading_day(
    day: date,
    fallback_weekday: bool = True,
) -> date:
    """返回 day 之前最近交易日，支持跨年。"""
    cursor = day - timedelta(days=1)

    for _ in range(370):
        if is_trading_day(
            cursor,
            fallback_weekday=fallback_weekday,
        ):
            return cursor

        cursor -= timedelta(days=1)

    raise ValueError(
        f"cannot resolve previous trading day before {day}"
    )


def next_trading_day(
    day: date,
    fallback_weekday: bool = True,
) -> date:
    """返回 day 之后最近交易日，支持跨年。"""
    cursor = day + timedelta(days=1)

    for _ in range(370):
        if is_trading_day(
            cursor,
            fallback_weekday=fallback_weekday,
        ):
            return cursor

        cursor += timedelta(days=1)

    raise ValueError(
        f"cannot resolve next trading day after {day}"
    )


def build_calendar_from_rules(year: int) -> list[str]:
    """根据周末 + 已核对交易所休市日生成年度交易日快照。"""
    cursor = date(year, 1, 1)
    end = date(year, 12, 31)
    closed = _configured_closed_dates(year)
    dates: list[str] = []

    while cursor <= end:
        if (
            cursor.weekday() < 5
            and cursor.isoformat() not in closed
        ):
            dates.append(cursor.isoformat())

        cursor += timedelta(days=1)

    return dates
