"""东财延迟行情主机（push2delay.eastmoney.com）适配器（R9）。

背景（2026-08-15 实测）：东财 push2his / 编号 push2 主机对部分出口 IP 做主机级封禁
（连接被断），但 push2delay 主机与 push2ex 未封。延迟约 15 分钟，对 16:23 收盘采集
而言即当日最终数据，因此可用于当日指数与全市场 spot。

约束：该主机不提供历史 kline / 历史 spot，非当日调用直接失败（由调用方降级链兜底）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from collector.schema import TZ_SHANGHAI

DELAY_HOST = "https://push2delay.eastmoney.com"
UT = "bd1d9ddb04089700f9c27d4d04e0e0cc"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}

# symbol_em 前缀 → push2 secid 前缀（sh=1. 沪市, sz=0. 深市, bj=0. 北证）
SECID_PREFIX = {
    "sh": "1.",
    "sz": "0.",
    "bj": "0.",
}

INDEX_NAMES = {
    "1.000001": "上证指数",
    "0.399001": "深证成指",
    "0.399006": "创业板指",
    "1.000688": "科创50",
    "1.000300": "沪深300",
    "0.899050": "北证50",
    "0.399311": "国证1000",
    "0.399303": "国证2000",
}


def _get_json(url: str) -> dict[str, Any]:
    # 国内数据源必须直连：requests 在 Windows 上会继承系统代理
    # （v2rayN 等），经代理访问东财主机会挂起/失败（2026-08-15 实测）。
    response = requests.get(
        url,
        timeout=15,
        headers=HEADERS,
        proxies={"http": None, "https": None},
    )
    response.raise_for_status()
    data = response.json()
    if data.get("rc") != 0:
        raise ValueError(
            f"eastmoney_delay rc={data.get('rc')}"
        )
    return data


def secid_from_symbol(symbol_em: str) -> str:
    """sh000001 → 1.000001；sz399001 → 0.399001；bj899050 → 0.899050。"""
    for prefix, secid_prefix in SECID_PREFIX.items():
        if symbol_em.startswith(prefix):
            return secid_prefix + symbol_em[len(prefix):]
    raise ValueError(
        f"unknown symbol_em: {symbol_em}"
    )


def is_today(trade_date: str) -> bool:
    return (
        trade_date
        == datetime.now(TZ_SHANGHAI).date().isoformat()
    )


def fetch_index_quotes(
    trade_date: str,
) -> dict[str, tuple[float, float]]:
    """返回 {secid: (close, previous_close)}；非当日直接失败。

    close 取延迟主机最新价（收盘采集=当日最终值）；
    previous_close 由涨跌幅反推：close / (1 + pct/100)。
    """
    if not is_today(trade_date):
        raise ValueError(
            "eastmoney_delay has no history; "
            f"target {trade_date} != today"
        )

    url = (
        f"{DELAY_HOST}/api/qt/ulist.np/get"
        "?secids=1.000001,0.399001,0.399006,1.000688,"
        "1.000300,0.899050,0.399311,0.399303"
        "&fields=f2,f3,f4,f6,f12,f14&fltt=2&invt=2"
        f"&ut={UT}"
    )
    data = _get_json(url)
    diff = (data.get("data") or {}).get("diff") or []

    result: dict[str, tuple[float, float]] = {}
    for row in diff:
        code = str(row.get("f12") or "")
        close = row.get("f2")
        pct = row.get("f3")

        if (
            code not in INDEX_NAMES
            or not isinstance(close, (int, float))
            or not isinstance(pct, (int, float))
        ):
            continue

        close = float(close)
        pct = float(pct)

        if close <= 0 or pct <= -100:
            continue

        result[code] = (
            close,
            close / (1 + pct / 100),
        )

    if len(result) < 8:
        raise ValueError(
            "eastmoney_delay index quotes incomplete: "
            f"{sorted(result)}"
        )

    return result
