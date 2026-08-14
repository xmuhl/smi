"""两融派生指标。

禁止用“融券余额金额变化”伪装成“融券净卖出量”。
复杂派生值由 modules.margin 在源数据单位已明确时计算。
"""

from __future__ import annotations

from typing import Any

def compute_margin_derived(
    raw: dict[str, Any],
    prev_raw: dict[str, Any] | None,
) -> dict[str, Any]:
    """仅计算可以无歧义获得的余额变动。"""
    out = dict(raw)

    if prev_raw is not None:
        previous_balance = prev_raw.get(
            "marginBalance"
        )
        current_balance = raw.get(
            "marginBalance"
        )

        if (
            previous_balance is not None
            and current_balance is not None
        ):
            out["marginBalanceChange"] = round(
                float(current_balance)
                - float(previous_balance),
                2,
            )

    out.setdefault(
        "financingNetBuyAmount",
        {
            "value": None,
            "quality": "UNAVAILABLE",
        },
    )

    out.setdefault(
        "securitiesLendingNetSellVolume",
        {
            "value": None,
            "unit": "亿股/亿份",
            "quality": "UNAVAILABLE",
        },
    )

    out.setdefault(
        "marginTradeAmount",
        {
            "value": None,
            "quality": "UNAVAILABLE",
        },
    )

    out.setdefault(
        "marginTradeSharePct",
        {
            "value": None,
            "quality": "UNAVAILABLE",
        },
    )

    return out
