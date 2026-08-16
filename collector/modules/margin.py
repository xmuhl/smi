"""模块 7：沪深两融数据。

SSE 金额：元 → 亿元
SZSE 汇总金额：已经是亿元
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
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

    # D0 参考值（R7-P1）：D0 时 margin=PENDING，前端需要展示
    # "最近已披露"的 T-1 官方值，而不是空白或伪装的 T 日 FINAL。
    # 仅在结果非 FINAL 时附加；FINAL 本身就是 T 日真实值，无需参考。
    _latest_reference = _latest_published_reference(
        trade_date
    )

    def _attach_reference(
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if _latest_reference is not None:
            result["latestPublishedReference"] = _latest_reference
        return result

    def _unpublished(
        exchange: str,
        *,
        exc: Exception | None = None,
    ) -> dict[str, Any]:
        """交易所尚未披露（T+1 发布 / 周末顺延）时的降级结果。

        - D0（is_t1=False）保持 PENDING，前端照常展示最近已披露参考值；
          原始异常类型写入 warnings，绝不把难懂的 pandas 报错混进 errors。
        - t1（is_t1=True）置 STALE，保留后续 t1-reconcile 可重试语义。
        """
        if is_t1:
            return _attach_reference(
                {
                    **base,
                    "status": ModuleStatus.STALE.value,
                    "errors": [
                        f"{exchange}_NOT_YET_PUBLISHED:{trade_date}"
                    ],
                }
            )

        warnings = list(base.get("warnings", []))
        if exc is not None:
            warnings.append(type(exc).__name__)

        return _attach_reference(
            {
                **base,
                "status": ModuleStatus.PENDING.value,
                "errors": [
                    f"{exchange} margin not published "
                    f"for {trade_date} (T+1 disclosure)"
                ],
                "warnings": warnings,
            }
        )

    try:
        sse = ak.stock_margin_sse(
            start_date=yyyymmdd,
            end_date=yyyymmdd,
        )

    except Exception as exc:  # noqa: BLE001
        return _attach_reference(
            {
                **base,
                "status": (
                    ModuleStatus.ERROR.value
                    if is_t1
                    else ModuleStatus.PENDING.value
                ),
                "errors": [str(exc)],
            }
        )

    # SSE 侧：返回空表（未披露）也按“未披露”处理，避免 _last_row 之后静默缺数。
    if sse is None or sse.empty:
        return _unpublished("SSE")

    try:
        szse = ak.stock_margin_szse(
            date=yyyymmdd
        )

    except Exception as exc:  # noqa: BLE001
        # SZSE 对未披露日返回空表，akshare 内部赋 6 列导致
        # ValueError("Length mismatch: Expected axis has 0 elements...")。
        # 命中即视为“尚未披露”，而非一般性抓取失败。
        if (
            isinstance(exc, ValueError)
            and "Length mismatch" in str(exc)
            and "0 elements" in str(exc)
        ):
            return _unpublished("SZSE", exc=exc)

        # 未命中的其它异常仍走通用 except 分支（保持现有行为）。
        return _attach_reference(
            {
                **base,
                "status": (
                    ModuleStatus.ERROR.value
                    if is_t1
                    else ModuleStatus.PENDING.value
                ),
                "errors": [str(exc)],
            }
        )

    sse_row = _last_row(sse)
    szse_row = _last_row(szse)

    if sse_row is None or szse_row is None:
        return _attach_reference(
            {
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
        )

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
        return _attach_reference(
            {
                **base,
                "status": ModuleStatus.ERROR.value,
                "errors": [
                    "两融核心字段缺失，拒绝生成 FINAL"
                ],
            }
        )

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

def _latest_published_reference(
    trade_date: str,
) -> dict[str, Any] | None:
    """最近已披露两融参考值；文件名、snapshot.tradeDate、margin.dataDate 三者必须同日。

    从 trade_date 之前的交易日倒序查找第一个满足身份一致且 margin=FINAL 的
    快照，返回其三项余额作为"最近已披露"参考；找不到则返回 None（fail-closed）。

    约束（R10-P2-01 强化）：
    - 只读已落盘快照，不重新抓网络（与 _compute_balance_change 同源）；
    - 文件名日期、snapshot.tradeDate、margin.dataDate 必须三者一致，
      任何错位一律跳过（防错名/被改文件把 T-n 内容标成 T-1）；
    - 参考值必须是 FINAL 快照的核心余额字段，避免把 PENDING/ERROR 当参考；
    - 三项余额必须是有限数值（bool/NaN/Inf 一律跳过并继续回退）且 >= 0，
      并满足 marginBalance == financingBalance + securitiesLendingBalance
      （绝对容差 0.05 亿元，与 validator 同口径）；
    - 回退上限为 30 个交易日（约 6 周），防止异常日历死循环；
    - 返回结构固定：dataDate + 三项余额（亿元），供 validator 深度契约。
    """
    from math import isfinite

    from collector.calendar import previous_trading_day
    from collector.config import daily_path

    cursor = date.fromisoformat(trade_date)

    for _ in range(30):
        try:
            previous = previous_trading_day(
                cursor,
                fallback_weekday=True,
            )
        except ValueError:
            return None

        if previous >= cursor:
            return None

        expected_date = previous.isoformat()
        path = daily_path(expected_date)

        if not path.exists():
            cursor = previous
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            cursor = previous
            continue

        if (
            not isinstance(data, dict)
            or data.get("tradeDate") != expected_date
        ):
            cursor = previous
            continue

        modules = data.get("modules")

        if not isinstance(modules, dict):
            cursor = previous
            continue

        margin = modules.get("margin")

        if not isinstance(margin, dict):
            cursor = previous
            continue

        if (
            margin.get("status") != ModuleStatus.FINAL.value
            or margin.get("dataDate") != expected_date
        ):
            cursor = previous
            continue

        financing = margin.get("financingBalance")
        lending = margin.get("securitiesLendingBalance")
        total = margin.get("marginBalance")

        values = (financing, lending, total)

        if not all(
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and isfinite(v)
            and float(v) >= 0
            for v in values
        ):
            cursor = previous
            continue

        expected = Decimal(str(financing)) + Decimal(str(lending))
        actual = Decimal(str(total))

        if abs(actual - expected) > Decimal("0.05"):
            cursor = previous
            continue

        return {
            "dataDate": expected_date,
            "financingBalance": financing,
            "securitiesLendingBalance": lending,
            "marginBalance": total,
        }

    return None


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
