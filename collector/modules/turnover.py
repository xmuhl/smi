"""模块 2：沪深两市成交额。

两市严格定义为上交所 A 股 + 深交所 A 股，不含北交所。

多源降级（R5-P2-01）：东财 spot 失败时降级到新浪全市场 spot，
新浪返回的代码带市场前缀（sh/sz/bj），求和时按口径过滤。

R9：新增 exchange 官方源（SSE 单日概况 + SZSE 市场总貌）。
Exchange 历史成交额有效范围：受 SSE 官方 stock_sse_deal_daily 接口
共同可用范围约束（文档化起始日期 2021-12-27），V1 不承诺该日期之前的
Exchange 回补；超出有效范围时接口返回空 → fail-closed，按降级链继续，
无真实历史源则模块 UNAVAILABLE/ERROR，不得用当日 spot 倒灌历史。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from collector.adapters.sources import try_sources
from collector.status import ModuleStatus


def _is_today(trade_date: str) -> bool:
    from datetime import datetime

    from collector.schema import TZ_SHANGHAI

    return (
        trade_date
        == datetime.now(TZ_SHANGHAI).date().isoformat()
    )


def _fetch_turnover_yuan(
    source: str,
    trade_date: str,
) -> float:
    """按指定源返回两市总成交额（元）。

    spot 类源（eastmoney/eastmoney_delay/sina）仅支持当日；
    exchange 源为交易所官方口径（沪：主板A+科创板；深：主板A股+创业板A股），
    支持历史日期（R9）。
    """
    import akshare as ak

    if source == "eastmoney":
        if not _is_today(trade_date):
            raise ValueError(
                "eastmoney spot has no history"
            )
        sh = ak.stock_sh_a_spot_em()
        sz = ak.stock_sz_a_spot_em()
        return _sum_amount(sh) + _sum_amount(sz)

    if source == "exchange":
        return _turnover_yuan_from_exchange(
            trade_date
        )

    if source == "sina":
        if not _is_today(trade_date):
            raise ValueError(
                "sina spot has no history"
            )
        spot = ak.stock_zh_a_spot()
        return _sum_amount_sh_sz(spot)

    raise ValueError(f"unknown spot source: {source}")


def _turnover_yuan_from_exchange(
    trade_date: str,
) -> float:
    """交易所官方口径两市 A 股成交额（元）（R9-P1-01 fail-closed）。

    沪市：SSE 主板A + 科创板（SSE 返回单位：亿元）；
    深市：SZSE 主板A股 + 创业板A股（SZSE 返回单位：元）。

    任一必需分类缺失、重复、非有限或为负时必须失败，
    不能把部分市场金额当作完整 FINAL。
    交易所官网文件支持历史日期回查（有效范围见模块 docstring）。
    """
    import math

    import akshare as ak

    # R9.2-N5：SSE stock_sse_deal_daily 文档化仅支持 2021-12-27（含）之后。
    # 更早日期直接失败，不依赖远端接口对越界日期的未定义行为，
    # fail-closed 并按降级链继续。
    if trade_date < "2021-12-27":
        raise ValueError(
            "exchange history not supported before "
            f"2021-12-27: {trade_date}"
        )

    yyyymmdd = trade_date.replace("-", "")

    sse = ak.stock_sse_deal_daily(
        date=yyyymmdd
    )

    if sse is None or sse.empty:
        raise ValueError("empty SSE deal daily")

    required_sse_columns = {
        "单日情况",
        "主板A",
        "科创板",
    }

    if not required_sse_columns.issubset(
        set(sse.columns)
    ):
        raise ValueError(
            "SSE required columns missing: "
            f"{sorted(required_sse_columns - set(sse.columns))}"
        )

    sse_rows = sse[
        sse["单日情况"] == "成交金额"
    ]

    if len(sse_rows) != 1:
        raise ValueError(
            f"SSE 成交金额 row count invalid: {len(sse_rows)}"
        )

    def _finite_nonnegative(
        value,
        label: str,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label} invalid: {value!r}"
            ) from exc

        if not math.isfinite(number) or number < 0:
            raise ValueError(
                f"{label} invalid: {number}"
            )

        return number

    sse_row = sse_rows.iloc[0]

    sh_main_yi = _finite_nonnegative(
        sse_row["主板A"],
        "SSE 主板A",
    )
    sh_star_yi = _finite_nonnegative(
        sse_row["科创板"],
        "SSE 科创板",
    )

    szse = ak.stock_szse_summary(
        date=yyyymmdd
    )

    if szse is None or szse.empty:
        raise ValueError("empty SZSE summary")

    required_szse_columns = {
        "证券类别",
        "成交金额",
    }

    if not required_szse_columns.issubset(
        set(szse.columns)
    ):
        raise ValueError(
            "SZSE required columns missing: "
            f"{sorted(required_szse_columns - set(szse.columns))}"
        )

    sz_a_yuan = 0.0

    for category in ("主板A股", "创业板A股"):
        rows = szse[
            szse["证券类别"] == category
        ]

        if len(rows) != 1:
            raise ValueError(
                f"SZSE category row count invalid: {category}={len(rows)}"
            )

        sz_a_yuan += _finite_nonnegative(
            rows.iloc[0]["成交金额"],
            f"SZSE {category}",
        )

    total_yuan = (
        (sh_main_yi + sh_star_yi) * 1e8
        + sz_a_yuan
    )

    if not math.isfinite(total_yuan) or total_yuan <= 0:
        raise ValueError(
            f"exchange turnover total invalid: {total_yuan}"
        )

    return total_yuan


def _sum_amount_sh_sz(df) -> float:
    """新浪全市场 spot：仅统计沪/深 A 股（口径：不含北交所）。"""
    if df is None or df.empty:
        raise ValueError("empty market spot dataframe")

    code_col = _pick_col(
        df,
        ("代码", "code"),
    )

    if code_col is None:
        raise ValueError(
            f"code column missing: {list(df.columns)}"
        )

    if "成交额" not in df.columns:
        raise ValueError(
            f"成交额 column missing: {list(df.columns)}"
        )

    codes = df[code_col].astype(str)
    mask = codes.str.startswith(
        ("sh", "sz")
    )

    values = pd.to_numeric(
        df.loc[mask, "成交额"],
        errors="coerce",
    )

    if values.notna().sum() == 0:
        raise ValueError("all 成交额 values invalid")

    return float(
        values.fillna(0).sum()
    )


def collect_turnover(
    trade_date: str,
    market_rules: dict | None = None,
) -> dict[str, Any]:
    total_yuan, used, source_errors = try_sources(
        "turnover",
        ["eastmoney"],
        lambda source: _fetch_turnover_yuan(
            source,
            trade_date,
        ),
    )

    if total_yuan is None:
        return _error(
            trade_date,
            "; ".join(source_errors or ["unknown spot failure"]),
        )

    sources = [used.upper()] if used else ["EASTMONEY"]
    turnover_today_yi = round(
        total_yuan / 1e8,
        2,
    )

    comparison = _turnover_comparison(
        turnover_today_yi,
        _load_previous_turnover_for_date(
            trade_date
        ),
        market_rules,
    )

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": sources,
        "unit": "亿元",
        "method": TURNOVER_METHOD,
        "turnoverToday": turnover_today_yi,
        "turnoverPrevious": comparison[
            "turnoverPrevious"
        ],
        "turnoverDelta": comparison[
            "turnoverDelta"
        ],
        "turnoverChangePct": comparison[
            "turnoverChangePct"
        ],
        "volumeState": comparison[
            "volumeState"
        ],
        "previousMethod": comparison[
            "previousMethod"
        ],
        "comparisonStatus": comparison[
            "comparisonStatus"
        ],
    }

    if source_errors:
        # R9-P3-02：前序源失败只作运维观测，不影响 health
        result["sourceWarnings"] = source_errors

    return result


def _sum_amount(df) -> float:
    if df is None or df.empty:
        raise ValueError("empty market spot dataframe")

    if "成交额" not in df.columns:
        raise ValueError(
            f"成交额 column missing: {list(df.columns)}"
        )

    values = pd.to_numeric(
        df["成交额"],
        errors="coerce",
    )

    if values.notna().sum() == 0:
        raise ValueError("all 成交额 values invalid")

    return float(
        values.fillna(0).sum()
    )


TURNOVER_METHOD = (
    "SH_SZ_A_NO_B_NO_BJ_V1"
)


def _turnover_comparison(
    turnover_today_yi: float,
    previous_info: dict[str, Any] | None,
    market_rules: dict | None = None,
) -> dict[str, Any]:
    """统一生成成交额跨日比较字段（R9-P2-01 / R9.2-N3 收敛）。

    collect 与 reconcile 唯一共用实现。turnover_today_yi 必须已 round(,2)。
    仅当前日与上一交易日口径均可证明为 SH_SZ_A_NO_B_NO_BJ_V1、
    且前值有限为正时才允许比较。状态机（与 validator 契约严格配对）：
    - previous_info 缺失 / 前值无效 / 前日口径不可证明
        -> PREVIOUS_UNAVAILABLE, previousMethod=None
    - previous_method 非 None 且 != V1
        -> PREVIOUS_METHOD_MISMATCH, previousMethod=原值
    - 其余 -> COMPARABLE
    """
    import math

    rules = market_rules or {}
    volume_rules = rules.get("volume_state", {})

    expand_pct = float(
        volume_rules.get("expansion_threshold_pct", 5)
    )
    contract_pct = float(
        volume_rules.get("contraction_threshold_pct", -5)
    )

    unavailable = {
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    }

    if previous_info is None:
        return {
            **unavailable,
            "previousMethod": None,
            "comparisonStatus": "PREVIOUS_UNAVAILABLE",
        }

    previous_method = previous_info.get("method")

    if previous_method is None:
        # 前日文件存在但口径不可证明：不可比，且不得误标 MISMATCH
        return {
            **unavailable,
            "previousMethod": None,
            "comparisonStatus": "PREVIOUS_UNAVAILABLE",
        }

    if previous_method != TURNOVER_METHOD:
        return {
            **unavailable,
            "previousMethod": previous_method,
            "comparisonStatus": "PREVIOUS_METHOD_MISMATCH",
        }

    try:
        previous_value = float(previous_info["value"])
    except (KeyError, TypeError, ValueError):
        previous_value = float("nan")

    if not math.isfinite(previous_value) or previous_value <= 0:
        # 前值无效：previousMethod 置空，与 UNAVAILABLE->null 契约一致
        return {
            **unavailable,
            "previousMethod": None,
            "comparisonStatus": "PREVIOUS_UNAVAILABLE",
        }

    previous_value = round(previous_value, 2)
    delta = round(turnover_today_yi - previous_value, 2)
    change_pct = round(delta / previous_value * 100, 2)

    if change_pct >= expand_pct:
        volume_state = "EXPANSION"
    elif change_pct <= contract_pct:
        volume_state = "CONTRACTION"
    else:
        volume_state = "FLAT"

    return {
        "turnoverPrevious": previous_value,
        "turnoverDelta": delta,
        "turnoverChangePct": change_pct,
        "volumeState": volume_state,
        "previousMethod": previous_method,
        "comparisonStatus": "COMPARABLE",
    }


def _infer_turnover_method(
    module: dict[str, Any],
) -> str | None:
    """从显式 method 或已知 source 推断成交额统计口径（R9-P2-01）。"""
    explicit = module.get("method")

    if isinstance(explicit, str) and explicit:
        return explicit

    sources = {
        str(item).upper()
        for item in module.get(
            "source",
            [],
        )
    }

    if "TONGDAXIN_LEGACY" in sources:
        return "LEGACY_UNKNOWN"

    if sources & {
        "EASTMONEY",
        "SINA",
        "EXCHANGE",
    }:
        return TURNOVER_METHOD

    return None


def _load_previous_turnover_for_date(
    trade_date: str,
) -> dict[str, Any] | None:
    """定位真实上一交易日并读取其成交额血缘（R9-P2-01）。"""
    from datetime import date

    from collector.calendar import previous_trading_day

    try:
        previous = previous_trading_day(
            date.fromisoformat(trade_date),
            fallback_weekday=True,
        )
    except ValueError:
        return None

    return _load_previous_turnover(previous.isoformat())


def _load_previous_turnover(
    previous_date: str,
) -> dict[str, Any] | None:
    """读取上一交易日成交额及其口径血缘（R9-P2-01 / R9.2 防御收紧）。

    返回 {value, method, source}；文件缺失/损坏/tradeDate 与文件名
    不符/非 FINAL/无成交额/数值非有限时返回 None，
    调用方不得直接做环比。
    """
    import math

    from collector.config import daily_path

    path = daily_path(previous_date)

    if not path.exists():
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if data.get("tradeDate") != previous_date:
            return None

        module = data["modules"]["turnover"]

        if module.get("status") != ModuleStatus.FINAL.value:
            return None

        value = module.get("turnoverToday")

        if value is None:
            return None

        value_f = float(value)

        if not math.isfinite(value_f):
            return None

        return {
            "value": value_f,
            "method": _infer_turnover_method(
                module
            ),
            "source": list(
                module.get(
                    "source",
                    [],
                )
                or []
            ),
        }

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return None


def _error(
    trade_date: str,
    message: str,
) -> dict[str, Any]:
    return {
        "status": ModuleStatus.ERROR.value,
        "dataDate": trade_date,
        "source": [
            "EASTMONEY",
            "EXCHANGE",
            "SINA",
        ],
        "unit": "亿元",
        "errors": [message],
        "turnoverToday": None,
        "turnoverPrevious": None,
        "turnoverDelta": None,
        "turnoverChangePct": None,
        "volumeState": "UNKNOWN",
    }


def _pick_col(
    df,
    candidates: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None
