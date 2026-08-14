"""模块 4：板块行情表现（东方财富行业/概念板块 TOP5）。"""

from __future__ import annotations

from typing import Any

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


def collect_sectors(
    trade_date: str,
) -> dict[str, Any]:
    from datetime import datetime

    import akshare as ak

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
        industry = (
            ak.stock_board_industry_name_em()
        )

        if (
            industry is None
            or industry.empty
        ):
            raise ValueError(
                "empty industry board data"
            )

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
            key=lambda item: item[
                "changePct"
            ],
            reverse=True,
        )[:5]

        result["industryBottom5"] = sorted(
            entries,
            key=lambda item: item[
                "changePct"
            ],
        )[:5]

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"industry: {exc}"
        )

    try:
        concept = (
            ak.stock_board_concept_name_em()
        )

        if (
            concept is None
            or concept.empty
        ):
            raise ValueError(
                "empty concept board data"
            )

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
            key=lambda item: item[
                "changePct"
            ],
            reverse=True,
        )[:5]

        result["conceptBottom5"] = sorted(
            entries,
            key=lambda item: item[
                "changePct"
            ],
        )[:5]

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(
            f"concept: {exc}"
        )

    if result["errors"]:
        result["status"] = (
            ModuleStatus.ERROR.value
        )

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
