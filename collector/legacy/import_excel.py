"""Legacy Excel 基线导入工具。

将《A股收盘全景》Excel 转换为 SMI 每日快照 JSON。
- 全文件标记 TONGDAXIN_LEGACY
- 北向字段放入 legacyImportedFields（POST_20240819_LEGACY_IMPORTED）
- 板块/资金 method=TONGDAXIN_LEGACY
- 禁止对缺失字段猜值
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pandas as pd

from collector.config import DAILY_DIR
from collector.schema import finalize_snapshot, new_snapshot
from collector.status import ModuleStatus

SHEET_NAMES = {
    "index": "1-宽基指数收盘数据",
    "turnover": "2-两市成交量",
    "sentiment": "3-市场情绪指标",
    "sectors": "4-板块行情表现",
    "fund_flow": "5-主力资金流向",
    "northbound": "6-北向资金数据",
    "margin": "7-两融数据",
    "tracks": "8-主赛道每日监测表",
    "summary": "9-综合总结",
}

INDEX_CODE_MAP = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    "科创50": "000688",
    "沪深300": "000300",
    "北证50": "899050",
    "国证1000": "399311",
    "国证2000": "399303",
}




def import_excel(
    path: str,
    trade_date: str | None = None,
) -> dict[str, Any]:
    xl = pd.ExcelFile(path)

    if trade_date is None:
        trade_date = _read_date(xl)

    snapshot = new_snapshot(
        trade_date,
        legacy=True,
    )

    snapshot["generationReason"] = (
        "LEGACY_EXCEL_IMPORT"
    )

    modules = snapshot["modules"]

    modules["marketIndex"] = _import_index(xl)
    modules["turnover"] = _import_turnover(xl)
    modules["sentiment"] = _import_sentiment(xl)
    modules["sectorPerformance"] = _import_sectors(xl)
    modules["fundFlow"] = _import_fund_flow(xl)
    modules["northbound"] = _import_northbound(xl)
    modules["margin"] = _import_margin(xl)
    modules["tracks"] = _import_tracks(xl)
    modules["summary"] = _import_summary(xl)

    for module in modules.values():
        module["dataDate"] = trade_date

    snapshot["validation"]["warnings"] = [
        "LEGACY_EXCEL_IMPORTED_WITHOUT_INDEPENDENT_MARKET_REVALIDATION"
    ]

    return finalize_snapshot(snapshot)

def _read_date(xl: pd.ExcelFile) -> str:
    sheet = xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    for _, row in df.iterrows():
        cell = str(row.iloc[0] or "")
        if "统计日期" in cell or "监测日期" in cell:
            raw = str(row.iloc[1] or "").strip()
            return _normalize_date(raw)
    raise ValueError("无法从 Excel 识别统计日期")


def _normalize_date(raw: str) -> str:
    raw = raw.strip()
    if "-" in raw:
        return raw[:10]
    if raw.count(".") == 2:
        parts = raw.split(".")
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return raw


def _kv(df, key: str) -> Any:
    for _, row in df.iterrows():
        k = str(row.iloc[0] or "")
        if key in k:
            return row.iloc[1]
    return None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    for suffix in ("%", "元", "亿元", "亿", "家", "只"):
        s = s.replace(suffix, "")
    if s in ("", "-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _import_index(
    xl: pd.ExcelFile,
) -> dict[str, Any]:
    df = xl.parse(
        SHEET_NAMES["index"],
        header=None,
    )

    items: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        name = str(
            row.iloc[0] or ""
        ).strip()

        if name not in INDEX_CODE_MAP:
            continue

        items.append(
            {
                "code": INDEX_CODE_MAP[name],
                "name": name,
                "close": _num(row.iloc[1]),
                "previousClose": None,
                "changePct": _num(row.iloc[2]),
                "source": "TONGDAXIN_LEGACY",
            }
        )

    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "source": ["TONGDAXIN_LEGACY"],
        "items": items,
    }

def _import_turnover(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["turnover"], header=None)
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "source": ["TONGDAXIN_LEGACY"],
        "unit": "亿元",
        "turnoverToday": _num(_kv(df, "当日两市合计成交额")),
        "turnoverPrevious": _num(_kv(df, "前一交易日成交额")),
        "turnoverDelta": _num(_kv(df, "成交额增减金额")),
        "turnoverChangePct": _num(_kv(df, "成交变化幅度")),
        "volumeState": _map_volume(_kv(df, "量能定性")),
    }


def _map_volume(v: Any) -> str:
    s = str(v or "")
    if "放" in s:
        return "EXPANSION"
    if "缩" in s:
        return "CONTRACTION"
    return "FLAT"


def _import_sentiment(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["sentiment"], header=None)
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "source": ["TONGDAXIN_LEGACY"],
        "riseCount": _num(_kv(df, "全市场上涨家数")),
        "fallCount": _num(_kv(df, "全市场下跌家数")),
        "flatCount": _num(_kv(df, "平盘家数")),
        "suspendedCount": None,
        "nonStLimitUpCount": _num(_kv(df, "非ST涨停数量")),
        "stLimitUpCount": _num(_kv(df, "ST涨停数量")),
        "nonStLimitDownCount": _num(_kv(df, "非ST跌停数量")),
        "stLimitDownCount": _num(_kv(df, "ST跌停数量")),
        "brokenLimitCount": _num(_kv(df, "炸板数量")),
    }


def _split_pairs(df) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析左右双栏表格（涨榜 | 跌榜）。"""
    left, right = [], []
    for _, row in df.iterrows():
        l_name, l_val = str(row.iloc[0] or "").strip(), row.iloc[1]
        r_name, r_val = str(row.iloc[2] or "").strip(), row.iloc[3] if len(row) >= 4 else None
        if l_name and "名称" not in l_name and "一、" not in l_name:
            left.append({"name": l_name, "changePct": _num(l_val)})
        if r_name and "名称" not in r_name and "二、" not in r_name:
            right.append({"name": r_name, "changePct": _num(r_val)})
    return left, right


def _import_sectors(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["sectors"], header=None)
    # 全表双栏解析：行业涨/跌 + 概念涨/跌
    rows = df.to_dict("records")
    industry_up, industry_down = [], []
    concept_up, concept_down = [], []
    mode = None
    for row in rows:
        vals = [str(v or "").strip() for v in list(row.values())]
        joined = "".join(vals)
        if "通达信行业板块" in joined:
            mode = "industry"
            continue
        if "通达信概念板块" in joined:
            mode = "concept"
            continue
        if mode == "industry":
            l, r = _pair(row)
            if l:
                industry_up.append(l)
            if r:
                industry_down.append(r)
        elif mode == "concept":
            l, r = _pair(row)
            if l:
                concept_up.append(l)
            if r:
                concept_down.append(r)
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "method": "TONGDAXIN_LEGACY",
        "industryTop5": industry_up[:5],
        "industryBottom5": industry_down[:5],
        "conceptTop5": concept_up[:5],
        "conceptBottom5": concept_down[:5],
    }


def _pair(row: dict) -> tuple[dict | None, dict | None]:
    vals = list(row.values())
    l_name = str(vals[0] or "").strip() if len(vals) > 0 else ""
    l_val = vals[1] if len(vals) > 1 else None
    r_name = str(vals[2] or "").strip() if len(vals) > 2 else ""
    r_val = vals[3] if len(vals) > 3 else None
    left = {"name": l_name, "changePct": _num(l_val)} if l_name and "名称" not in l_name else None
    right = {"name": r_name, "changePct": _num(r_val)} if r_name and "名称" not in r_name else None
    return left, right


def _import_fund_flow(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["fund_flow"], header=None)
    sections = {"industry_in": [], "industry_out": [], "concept_in": [], "concept_out": [], "stock_in": [], "stock_out": []}
    mode = None
    for row in df.to_dict("records"):
        vals = [str(v or "").strip() for v in list(row.values())]
        joined = "".join(vals)
        if "行业板块" in joined:
            mode = "industry"
            continue
        if "概念板块" in joined:
            mode = "concept"
            continue
        if "个股" in joined:
            mode = "stock"
            continue
        if mode is None:
            continue
        l_name = vals[0] if len(vals) > 0 else ""
        l_val = list(row.values())[1] if len(vals) > 1 else None
        r_name = vals[2] if len(vals) > 2 else ""
        r_val = list(row.values())[3] if len(vals) > 3 else None
        if l_name and "名称" not in l_name and "流入" not in l_name:
            sections[f"{mode}_in"].append({"name": l_name, "netInflowYi": _num(l_val)})
        if r_name and "名称" not in r_name and "流出" not in r_name:
            sections[f"{mode}_out"].append({"name": r_name, "netInflowYi": _num(r_val)})
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "method": "TONGDAXIN_LEGACY",
        "unit": "亿元",
        "industryInflowTop10": sections["industry_in"][:10],
        "industryOutflowTop10": sections["industry_out"][:10],
        "conceptInflowTop10": sections["concept_in"][:10],
        "conceptOutflowTop10": sections["concept_out"][:10],
        "stockInflowTop10": sections["stock_in"][:10],
        "stockOutflowTop10": sections["stock_out"][:10],
    }


def _import_northbound(
    xl: pd.ExcelFile,
) -> dict[str, Any]:
    df = xl.parse(
        SHEET_NAMES["northbound"],
        header=None,
    )

    total = _num(
        _kv(
            df,
            "北向资金合计净流入",
        )
    )
    sh = _num(
        _kv(
            df,
            "沪股通净流入",
        )
    )
    sz = _num(
        _kv(
            df,
            "深股通净流入",
        )
    )

    buy_top10: list[dict] = []
    sell_top10: list[dict] = []
    in_names: list[str] = []
    out_names: list[str] = []

    mode = None

    for row in df.to_dict("records"):
        values = list(row.values())
        texts = [
            str(value or "").strip()
            for value in values
        ]

        joined = "".join(texts)

        if (
            "净买入TOP10" in joined
            and "净卖出TOP10" in joined
        ):
            mode = "buy_sell"
            continue

        if "净买入TOP10" in joined:
            mode = "buy"
            continue

        if "净卖出TOP10" in joined:
            mode = "sell"
            continue

        if "同步流入" in joined:
            value = (
                texts[1]
                if len(texts) > 1
                else ""
            )

            in_names = [
                name.strip()
                for name in value.split("、")
                if name.strip()
            ]
            continue

        if "同步流出" in joined:
            value = (
                texts[1]
                if len(texts) > 1
                else ""
            )

            out_names = [
                name.strip()
                for name in value.split("、")
                if name.strip()
            ]
            continue

        if "重合" in joined:
            mode = "overlap"
            continue

        if mode in {"buy", "buy_sell"}:
            left, right = _pair(row)

            if left:
                buy_top10.append(
                    {
                        "name": left["name"],
                        "netInflowYi": (
                            left["changePct"]
                        ),
                    }
                )

            if right:
                sell_top10.append(
                    {
                        "name": right["name"],
                        "netInflowYi": (
                            right["changePct"]
                        ),
                    }
                )

        elif mode == "sell":
            _, right = _pair(row)

            if right:
                sell_top10.append(
                    {
                        "name": right["name"],
                        "netInflowYi": (
                            right["changePct"]
                        ),
                    }
                )

    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "source": ["TONGDAXIN_LEGACY"],
        "mode": (
            "POST_20240819_LEGACY_IMPORTED"
        ),
        "sourceSystem": (
            "TONGDAXIN_LEGACY"
        ),
        "officialDisclosureCompatible": False,
        "dailyTurnover": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "value": None,
            "reason": "LEGACY_IMPORT",
        },
        "activeSecurities": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "items": [],
            "reason": "LEGACY_IMPORT",
        },
        "legacyNetFlow": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "reason": "DISCLOSURE_RULE_CHANGED",
        },
        "overlap": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "items": [],
        },
        "quarterlyHolding": {
            "status": ModuleStatus.UNAVAILABLE.value,
            "asOf": None,
            "items": [],
        },
        "legacyImportedFields": {
            "status": ModuleStatus.FINAL.value,
            "totalNetInflow": total,
            "shanghaiNetInflow": sh,
            "shenzhenNetInflow": sz,
            "netBuyTop10": buy_top10[:10],
            "netSellTop10": sell_top10[:10],
            "sameDirectionIn": in_names,
            "sameDirectionOut": out_names,
            "excludeFromOfficialTimeSeries": True,
            "excludeFromTrackScoring": True,
        },
    }

def _import_margin(
    xl: pd.ExcelFile,
) -> dict[str, Any]:
    df = xl.parse(
        SHEET_NAMES["margin"],
        header=None,
    )

    legacy_lending_net_sell = _num(
        _kv(
            df,
            "融券净卖出",
        )
    )

    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "source": ["TONGDAXIN_LEGACY"],
        "unit": "亿元",
        "financingBalance": _num(
            _kv(df, "融资余额")
        ),
        "securitiesLendingBalance": _num(
            _kv(df, "融券余额")
        ),
        "marginBalance": _num(
            _kv(df, "两融总余额")
        ),
        "marginBalanceChange": _num(
            _kv(
                df,
                "较前一交易日余额变动",
            )
        ),
        "financingBuyAmount": None,
        "financingNetBuyAmount": {
            "value": _num(
                _kv(df, "融资净买入")
            ),
            "quality": "LEGACY",
        },
        # 原表没有可确认的“亿股/亿份”口径，
        # 因此不再塞入 Volume 字段。
        "securitiesLendingNetSellVolume": {
            "value": None,
            "unit": "亿股/亿份",
            "quality": "UNAVAILABLE",
        },
        "legacySecuritiesLendingNetSellAmount": {
            "value": legacy_lending_net_sell,
            "unit": "亿元",
            "quality": "LEGACY",
        },
        "marginTradeAmount": {
            "value": _num(
                _kv(df, "两融成交额")
            ),
            "quality": "LEGACY",
        },
        "marginTradeSharePct": {
            "value": _num(
                _kv(
                    df,
                    "两融成交占两市总成交比",
                )
            ),
            "quality": "LEGACY",
        },
    }

def _import_tracks(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["tracks"], header=None)
    header = None
    items = []
    for _, row in df.iterrows():
        vals = [v for v in row.tolist()]
        first = str(vals[0] or "")
        if "监测日期" in first and "板块名称" in "".join(str(v) for v in vals):
            header = vals
            continue
        if header is None:
            continue
        if not first or "核心阈值" in first or "维度" in first or first == "nan":
            continue
        try:
            d = str(vals[0] or "").strip()
            if not d or d == "nan":
                continue
        except Exception:  # noqa: BLE001
            continue
        decision = str(vals[15] or "") if len(vals) > 15 else ""
        if not decision or decision == "nan":
            continue
        items.append(
            {
                "date": d,
                "trackId": _slug(str(vals[1] or "")),
                "trackName": str(vals[1] or ""),
                "positioning": str(vals[2] or "") if len(vals) > 2 else "",
                "turnoverRank": _num(vals[3]) if len(vals) > 3 else None,
                "mainNetInflow": _num(vals[4]) if len(vals) > 4 else None,
                "continuousInflowDays": _num(vals[5]) if len(vals) > 5 else None,
                "maAlignment": str(vals[6] or "") if len(vals) > 6 else "",
                "rps60": _num(vals[7]) if len(vals) > 7 else None,
                "excessReturn20d": str(vals[8] or "") if len(vals) > 8 else "",
                "limitUpCount": _num(vals[9]) if len(vals) > 9 else None,
                "ladderCompleteness": str(vals[10] or "") if len(vals) > 10 else "",
                "redStockRatio": str(vals[11] or "") if len(vals) > 11 else "",
                "coreCatalyst": str(vals[12] or "") if len(vals) > 12 else "",
                "earningsRealization": str(vals[13] or "") if len(vals) > 13 else "",
                "score": _num(vals[14]) if len(vals) > 14 else None,
                "coveragePct": None,
                "decision": decision,
            }
        )
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "configVersion": "legacy",
        "sourceSystem": "TONGDAXIN_LEGACY",
        "items": items,
    }


def _slug(name: str) -> str:
    import re

    s = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", name).strip("_")
    return s or "unknown"


def _import_summary(xl: pd.ExcelFile) -> dict[str, Any]:
    df = xl.parse(SHEET_NAMES["summary"], header=None)
    kv = {}
    for _, row in df.iterrows():
        k = str(row.iloc[0] or "").strip()
        v = str(row.iloc[1] or "").strip()
        if k and v and "统计日期" not in k:
            kv[k] = v
    return {
        "status": ModuleStatus.FINAL.value,
        "dataDate": None,
        "generator": "LEGACY_EXCEL",
        "indexAndTurnover": kv.get("一、指数与量能总结", ""),
        "sentiment": kv.get("二、市场情绪总结", ""),
        "fundFlow": kv.get("三、资金流向总结", ""),
        "trackConclusion": kv.get("四、赛道监测结论", ""),
        "marketEnvironment": kv.get("五、操作建议", ""),
        "northbound": "",
        "margin": "",
        "riskWarning": kv.get("风险提示", ""),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SMI legacy excel import")
    parser.add_argument("--excel", required=True, help="Excel 文件路径")
    parser.add_argument("--date", default=None, help="交易日 YYYY-MM-DD（缺省自动识别）")
    parser.add_argument("--out", default=None, help="输出 JSON 路径（缺省 web/public/data/daily/YYYY/YYYY-MM-DD.json）")
    args = parser.parse_args()

    snapshot = import_excel(args.excel, args.date)
    if args.out:
        out_path = args.out
    else:
        year = snapshot["tradeDate"][:4]
        out_path = str(DAILY_DIR / year / f"{snapshot['tradeDate']}.json")

    import os

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"IMPORTED {snapshot['tradeDate']} -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
