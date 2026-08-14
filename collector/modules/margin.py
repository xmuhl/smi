"""模块 7：沪深两融数据。

SSE 金额：元 → 亿元
SZSE 汇总金额：已经是亿元
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd

from collector.status import ModuleStatus

def collect_margin(
    trade_date: str,
    *,
    is_t1: bool = False,
) -> dict[str, Any]:
    import akshare as ak

    yyyymmdd = trade_date.replace("-", "")

    base: dict[str, Any] = {
        "status": ModuleStatus.PENDING.value,
        "dataDate": None,
        "source": ["SSE", "SZSE"],
        "unit": "亿元",
        "errors": [],
        "warnings": [],
    }

    try:
        sse = ak.stock_margin_sse(
            start_date=yyyymmdd,
            end_date=yyyymmdd,
        )

        szse = ak.stock_margin_szse(
            date=yyyymmdd
        )

    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": (
                ModuleStatus.ERROR.value
                if is_t1
                else ModuleStatus.PENDING.value
            ),
            "errors": [str(exc)],
        }

    sse_row = _last_row(sse)
    szse_row = _last_row(szse)

    if sse_row is None or szse_row is None:
        return {
            **base,
            "status": (
                ModuleStatus.STALE.value
                if is_t1
                else ModuleStatus.PENDING.value
            ),
            "errors": [
                "SSE/SZSE 两融汇总尚未同时取得"
            ],
        }

    sse_financing_balance = _yuan_to_yi(
        _pick_float(
            sse_row,
            "融资余额",
        )
    )

    sse_lending_balance = _yuan_to_yi(
        _pick_float(
            sse_row,
            "融券余量金额",
        )
    )

    sse_total_balance = _yuan_to_yi(
        _pick_float(
            sse_row,
            "融资融券余额",
        )
    )

    sse_financing_buy = _yuan_to_yi(
        _pick_float(
            sse_row,
            "融资买入额",
        )
    )

    szse_financing_balance = _pick_float(
        szse_row,
        "融资余额",
    )

    szse_lending_balance = _pick_float(
        szse_row,
        "融券余额",
    )

    szse_total_balance = _pick_float(
        szse_row,
        "融资融券余额",
    )

    szse_financing_buy = _pick_float(
        szse_row,
        "融资买入额",
    )

    required_values = [
        sse_financing_balance,
        sse_lending_balance,
        sse_total_balance,
        sse_financing_buy,
        szse_financing_balance,
        szse_lending_balance,
        szse_total_balance,
        szse_financing_buy,
    ]

    if any(value is None for value in required_values):
        return {
            **base,
            "status": ModuleStatus.ERROR.value,
            "errors": [
                "两融核心字段缺失，拒绝生成 FINAL"
            ],
        }

    financing_balance = (
        sse_financing_balance
        + szse_financing_balance
    )

    lending_balance = (
        sse_lending_balance
        + szse_lending_balance
    )

    total_balance = (
        sse_total_balance
        + szse_total_balance
    )

    financing_buy = (
        sse_financing_buy
        + szse_financing_buy
    )

    sse_financing_net: float | None = None
    sse_lending_net_volume: float | None = None

    try:
        detail_sse = ak.stock_margin_detail_sse(
            date=yyyymmdd
        )

        if (
            detail_sse is not None
            and not detail_sse.empty
        ):
            sse_financing_net = _yuan_to_yi(
                _sum_numeric_column(
                    detail_sse,
                    "融资买入额",
                )
                - _sum_numeric_column(
                    detail_sse,
                    "融资偿还额",
                )
            )

            sse_lending_net_volume = (
                (
                    _sum_numeric_column(
                        detail_sse,
                        "融券卖出量",
                    )
                    - _sum_numeric_column(
                        detail_sse,
                        "融券偿还量",
                    )
                )
                / 1e8
            )

    except Exception as exc:  # noqa: BLE001
        base["warnings"].append(
            f"SSE detail unavailable: {exc}"
        )

    szse_financing_net: float | None = None
    szse_lending_net_volume: float | None = None

    try:
        from collector.calendar import previous_trading_day

        previous = previous_trading_day(
            date.fromisoformat(trade_date),
            fallback_weekday=True,
        )

        previous_szse = ak.stock_margin_szse(
            date=previous.strftime("%Y%m%d")
        )

        previous_row = _last_row(
            previous_szse
        )

        if previous_row is not None:
            previous_financing = _pick_float(
                previous_row,
                "融资余额",
            )

            previous_lending_volume = (
                _pick_float(
                    previous_row,
                    "融券余量",
                )
            )

            current_lending_volume = (
                _pick_float(
                    szse_row,
                    "融券余量",
                )
            )

            if previous_financing is not None:
                szse_financing_net = (
                    szse_financing_balance
                    - previous_financing
                )

            if (
                previous_lending_volume is not None
                and current_lending_volume is not None
            ):
                szse_lending_net_volume = (
                    current_lending_volume
                    - previous_lending_volume
                )

    except Exception as exc:  # noqa: BLE001
        base["warnings"].append(
            f"SZSE previous-day derive unavailable: {exc}"
        )

    if (
        sse_financing_net is not None
        and szse_financing_net is not None
    ):
        financing_net = {
            "value": round(
                sse_financing_net
                + szse_financing_net,
                2,
            ),
            "quality": "DERIVED",
        }
    else:
        financing_net = {
            "value": None,
            "quality": "UNAVAILABLE",
        }

    if (
        sse_lending_net_volume is not None
        and szse_lending_net_volume is not None
    ):
        lending_net_volume = {
            "value": round(
                sse_lending_net_volume
                + szse_lending_net_volume,
                4,
            ),
            "unit": "亿股/亿份",
            "quality": "DERIVED",
        }
    else:
        lending_net_volume = {
            "value": None,
            "unit": "亿股/亿份",
            "quality": "UNAVAILABLE",
        }

    result = {
        **base,
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "financingBalance": round(
            financing_balance,
            2,
        ),
        "securitiesLendingBalance": round(
            lending_balance,
            2,
        ),
        "marginBalance": round(
            total_balance,
            2,
        ),
        "marginBalanceChange": None,
        "financingBuyAmount": round(
            financing_buy,
            2,
        ),
        "financingNetBuyAmount": financing_net,
        "securitiesLendingNetSellVolume": (
            lending_net_volume
        ),
        # 当前实现没有逐证券历史 VWAP 估算链，
        # 宁缺勿错，不再把融资买入额冒充“两融成交额”。
        "marginTradeAmount": {
            "value": None,
            "quality": "UNAVAILABLE",
        },
        "marginTradeSharePct": {
            "value": None,
            "quality": "UNAVAILABLE",
        },
    }

    _compute_balance_change(
        result,
        trade_date,
    )

    return result

def _compute_balance_change(
    result: dict[str, Any],
    trade_date: str,
) -> None:
    from collector.calendar import previous_trading_day
    from collector.config import daily_path

    try:
        previous = previous_trading_day(
            date.fromisoformat(trade_date),
            fallback_weekday=True,
        )
    except ValueError:
        return

    path = daily_path(
        previous.isoformat()
    )

    if not path.exists():
        return

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        previous_balance = (
            data["modules"]["margin"]
            .get("marginBalance")
        )

        current_balance = result.get(
            "marginBalance"
        )

        if (
            previous_balance is not None
            and current_balance is not None
        ):
            result["marginBalanceChange"] = round(
                float(current_balance)
                - float(previous_balance),
                2,
            )

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return

def _last_row(df):
    if df is None or df.empty:
        return None

    return df.iloc[-1]

def _pick_float(
    row,
    column: str,
) -> float | None:
    if row is None or column not in row:
        return None

    value = pd.to_numeric(
        row[column],
        errors="coerce",
    )

    if pd.isna(value):
        return None

    return float(value)

def _sum_numeric_column(
    df,
    column: str,
) -> float:
    if column not in df.columns:
        raise ValueError(
            f"column missing: {column}"
        )

    values = pd.to_numeric(
        df[column],
        errors="coerce",
    )

    return float(
        values.fillna(0).sum()
    )

def _yuan_to_yi(
    value: float | None,
) -> float | None:
    if value is None:
        return None

    return value / 1e8
