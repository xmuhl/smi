"""模块 4：板块行情表现（行业/概念板块 TOP5，多源降级）。

R6：东财失败时降级同花顺（THS）资金流表——其含板块涨跌幅/净额/领涨股，
口径以 method 字段区分（EASTMONEY / THS），不混装历史序列。
"""

from __future__ import annotations

from typing import Any

from collector.adapters.sources import try_sources
from collector.status import ModuleStatus


def _to_entries(df, name_col: str, pct_col: str, code_col: str | None) -> list[dict[str, Any]]:
    entries = []
    for _, row in df.iterrows():
        try:
            pct = float(row[pct_col])
        except (TypeError, ValueError):
            continue
        if pct != pct:  # NaN
            continue
        entries.append(
            {
                "code": str(row.get(code_col, "") or "") if code_col else "",
                "name": str(row[name_col]),
                "changePct": round(pct, 2),
                "turnoverRate": _safe_float(row, "换手率"),
                "riseCount": _safe_int(row, "上涨家数"),
                "fallCount": _safe_int(row, "下跌家数"),
                "leader": str(row.get("领涨股票", "") or ""),
            }
        )
    return entries


def _ths_summary_entries(df) -> list[dict[str, Any]]:
    """同花顺行业摘要 → 板块条目（含真实上涨/下跌家数，R7-P2-01 修复）。"""
    entries = []
    for _, row in df.iterrows():
        try:
            pct = float(row["涨跌幅"])
        except (TypeError, ValueError):
            continue
        if pct != pct:  # NaN
            continue
        entries.append(
            {
                "code": "",
                "name": str(row["板块"]),
                "changePct": round(pct, 2),
                "turnoverRate": None,
                "riseCount": _safe_int(row, "上涨家数"),
                "fallCount": _safe_int(row, "下跌家数"),
                "leader": str(row.get("领涨股", "") or ""),
            }
        )
    return entries


def _ths_flow_entries(df, name_col: str, pct_col: str) -> list[dict[str, Any]]:
    """同花顺概念资金流表 → 板块条目（无真实涨跌家数，置 None 而非公司家数）。"""
    entries = []
    for _, row in df.iterrows():
        try:
            pct = float(row[pct_col])
        except (TypeError, ValueError):
            continue
        if pct != pct:  # NaN
            continue
        entries.append(
            {
                "code": "",
                "name": str(row[name_col]),
                "changePct": round(pct, 2),
                "turnoverRate": None,
                "riseCount": None,
                "fallCount": None,
                "leader": str(row.get("领涨股", "") or ""),
            }
        )
    return entries


def _rank_from_em(
    industry,
    concept,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    if industry is None or industry.empty:
        raise ValueError("empty industry board data")

    name_col = _pick_col(
        industry,
        ("板块名称", "name"),
    )
    pct_col = _pick_col(
        industry,
        ("涨跌幅", "change_pct"),
    )
    code_col = _pick_col(
        industry,
        ("板块代码", "code"),
    )

    if name_col is None or pct_col is None:
        raise ValueError(
            "industry required columns missing"
        )

    entries = _to_entries(
        industry,
        name_col,
        pct_col,
        code_col,
    )

    result["industryTop5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
        reverse=True,
    )[:5]

    result["industryBottom5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
    )[:5]

    if concept is None or concept.empty:
        raise ValueError("empty concept board data")

    name_col = _pick_col(
        concept,
        ("板块名称", "name"),
    )
    pct_col = _pick_col(
        concept,
        ("涨跌幅", "change_pct"),
    )
    code_col = _pick_col(
        concept,
        ("板块代码", "code"),
    )

    if name_col is None or pct_col is None:
        raise ValueError(
            "concept required columns missing"
        )

    entries = _to_entries(
        concept,
        name_col,
        pct_col,
        code_col,
    )

    result["conceptTop5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
        reverse=True,
    )[:5]

    result["conceptBottom5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
    )[:5]

    return result


def _rank_from_ths(
    industry,
    concept,
) -> dict[str, Any]:
    if industry is None or industry.empty:
        raise ValueError("empty ths industry data")

    entries = _ths_summary_entries(
        industry,
    )

    if not entries:
        raise ValueError("no valid ths industry rows")

    result: dict[str, Any] = {}

    result["industryTop5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
        reverse=True,
    )[:5]

    result["industryBottom5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
    )[:5]

    if concept is None or concept.empty:
        raise ValueError("empty ths concept data")

    entries = _ths_flow_entries(
        concept,
        "行业",
        "行业-涨跌幅",
    )

    if not entries:
        raise ValueError("no valid ths concept rows")

    result["conceptTop5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
        reverse=True,
    )[:5]

    result["conceptBottom5"] = sorted(
        entries,
        key=lambda item: item["changePct"],
    )[:5]

    return result


def _fetch_board_rank(
    source: str,
) -> dict[str, Any]:
    """按指定源返回板块 TOP5/BOTTOM5。"""
    import akshare as ak

    if source == "eastmoney":
        return _rank_from_em(
            ak.stock_board_industry_name_em(),
            ak.stock_board_concept_name_em(),
        )

    if source == "ths":
        return _rank_from_ths(
            ak.stock_board_industry_summary_ths(),
            ak.stock_fund_flow_concept(symbol="即时"),
        )

    raise ValueError(f"unknown sector source: {source}")


def collect_sectors(
    trade_date: str,
) -> dict[str, Any]:
    from datetime import datetime

    from collector.schema import TZ_SHANGHAI

    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        return {
            "status": ModuleStatus.UNAVAILABLE.value,
            "dataDate": trade_date,
            "method": "EASTMONEY",
            "reason": "HISTORICAL_BOARD_RANK_NOT_SUPPORTED",
            "industryTop5": [],
            "industryBottom5": [],
            "conceptTop5": [],
            "conceptBottom5": [],
        }

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "method": "EASTMONEY",
        "industryTop5": [],
        "industryBottom5": [],
        "conceptTop5": [],
        "conceptBottom5": [],
        "errors": [],
    }

    try:
        rank, used, source_errors = try_sources(
            "sector",
            ["eastmoney"],
            _fetch_board_rank,
        )

        if rank is None:
            raise ValueError(
                "all sector sources failed: "
                + "; ".join(source_errors or [])
            )

        result.update(rank)
        result["method"] = (
            "THS" if used == "ths" else "EASTMONEY"
        )

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(str(exc))
        result["status"] = ModuleStatus.ERROR.value

    return result


def _safe_float(row, name: str) -> float | None:
    if name not in row:
        return None
    try:
        v = float(row[name])
        return round(v, 2) if v == v else None
    except (TypeError, ValueError):
        return None


def _safe_int(row, name: str) -> int | None:
    if name not in row:
        return None
    try:
        v = int(row[name])
        return v
    except (TypeError, ValueError):
        return None


def _pick_col(df, candidates: tuple[str, ...]):
    for cand in candidates:
        if cand in df.columns:
            return cand
    return None
