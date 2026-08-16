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


# ---------------------------------------------------------------------------
# 历史回补分支（P1b）：THS 板块历史指数 → 任意历史交易日行业/概念 TOP5/BOTTOM5
# ---------------------------------------------------------------------------
#
# 接口实测（2026-08；akshare 1.18.88）：
#   ak.stock_board_industry_name_ths()  -> DataFrame[name, code]（约 90 行）
#   ak.stock_board_concept_name_ths()   -> DataFrame[name, code]（约 375 行）
#   ak.stock_board_industry_index_ths(symbol=<板块名>, start_date, end_date)
#       -> DataFrame[日期,开盘价,最高价,最低价,收盘价,成交量,成交额]
#   ak.stock_board_concept_index_ths(...)  同上（概念板块）
# 注意：两个指数接口的 symbol 必须为单个板块精确名，symbol="全部行业" 会抛
# KeyError；因此须先取板块名全量，再逐只拉取其历史指数序列（start_date 取
# D-40 日历日以覆盖 D-1 前日，akshare 内部按年切片请求）。D-1 即该板块历史
# 序列中紧邻 D 的上一交易日行。
# ---------------------------------------------------------------------------

# 历史回补口径名（页面按 method 标注）
THS_HISTORICAL_METHOD = "THS_HISTORICAL_INDEX"

# 指数回看窗口（日历日）：需覆盖 D-1 前日，40 天对跨假期已足够
_THS_HISTORY_WINDOW_DAYS = 40

# 逐板块历史拉取的受控并发度：6 线程为保守值，防触发 THS 限流；
# 串行 465 请求/天实测 20+ 分钟，受控并发显著缩短回补耗时。
_THS_HIST_CONCURRENCY = 6


def _board_close_change_pct(
    index_df,
    trade_date: str,
) -> float | None:
    """板块指数历史序列 → D 日相对 D-1（该序列前一交易日）涨跌幅(%)。

    计算口径：
        changePct(D) = (close(D) / close(D-1) - 1) * 100，round(2)。
    任一前置不满足（无 D 行 / 无前一行 / 收盘缺失或为 0 / NaN）→ 返回 None，
    由调用方跳过该板块。
    """
    if (
        index_df is None
        or index_df.empty
        or "日期" not in index_df.columns
        or "收盘价" not in index_df.columns
    ):
        return None

    rows: list[tuple[str, float]] = []

    for _, row in index_df.iterrows():
        try:
            date_s = str(row["日期"]).strip()
            close = float(row["收盘价"])
        except (TypeError, ValueError):
            continue

        if not date_s or close != close:
            continue

        rows.append((date_s, close))

    # 按日期升序；紧邻 D 的上一行即该板块的前一交易日
    rows.sort(key=lambda item: item[0])

    dates = [item[0] for item in rows]
    closes = [item[1] for item in rows]

    idx: int | None = None

    for i, date_s in enumerate(dates):
        if date_s == trade_date:
            idx = i

    if idx is None:
        return None

    if idx < 1:
        return None

    prev_close = closes[idx - 1]
    close_d = closes[idx]

    if (
        prev_close == 0
        or prev_close != prev_close
        or close_d != close_d
    ):
        return None

    return round((close_d / prev_close - 1) * 100, 2)


def _fetch_th_boards_concurrent(
    *,
    board_type: str,
    names: list[str],
    start_date: str,
    end_date: str,
    trade_date: str,
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    """受控并发拉取全部板块历史指数并计算 D 日涨跌幅。

    用 ThreadPoolExecutor 以 _THS_HIST_CONCURRENCY=6 并发调度，替代逐板块
    串行请求，显著缩短回补耗时（串行 465 请求/天实测 20+ 分钟）。6 线程为
    保守值防限流。板块名清单已在调用方串行取得（1 次请求），此处仅并发拉
    取各家历史序列。

    - akshare 线程安全未知 → 每个工作函数内独立 import akshare，不共享状态；
    - 线程内仍 try/except fail-closed：单个板块拉取失败/无有效 D 数据计入
      skipped，不中断整侧；
    - warnings/skipped 由线程返回 (name, outcome) 元组，主线程串行汇总，
      避免列表并发写竞态；
    - 结果收集顺序不依赖提交/完成顺序：主线程按 name 重建 dict，排序在
      top5/bottom5 阶段统一进行。

    返回 (entry_by_name, warnings, skipped)。
    """

    def _fetch_one(name: str) -> tuple[str, tuple[str, Any]]:
        # 独立 import akshare：并发安全保守，且沿用现有函数内 import 风格。
        import akshare as ak

        fn = (
            ak.stock_board_industry_index_ths
            if board_type == "industry"
            else ak.stock_board_concept_index_ths
        )
        try:
            index_df = fn(
                symbol=name,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:  # noqa: BLE001
            return (name, ("FETCH_FAILED", type(exc).__name__))
        return (name, ("OK", index_df))

    from concurrent.futures import ThreadPoolExecutor

    entry_by_name: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    skipped = 0

    with ThreadPoolExecutor(max_workers=_THS_HIST_CONCURRENCY) as executor:
        for name, (status, payload) in executor.map(_fetch_one, names):
            if status == "FETCH_FAILED":
                skipped += 1
                warnings.append(
                    f"{board_type}:{name}:FETCH_FAILED:{payload}"
                )
                continue

            pct = _board_close_change_pct(payload, trade_date)

            if pct is None:
                skipped += 1
                continue

            entry_by_name[name] = {
                "name": name,
                "code": "",
                "changePct": pct,
            }

    return entry_by_name, warnings, skipped


def _ths_historical_board_rank(
    board_type: str,
    trade_date: str,
) -> dict[str, Any]:
    """拉取某一侧（industry/concept）全部板块在 D 日的涨跌幅并排序。

    返回 dict：
        ok/True|False、reason、top5/bottom5（entries，含 name/changePct）、
        warnings、skipped（无法定位 D 或前一交易日的板块计数）。
    侧级全失败（板块名单为空或全部板块无有效 D 数据）→ ok=False，调用方据此
    保持该侧 UNAVAILABLE 语义，绝不伪造。
    """
    from datetime import datetime, timedelta

    import akshare as ak

    day = datetime.strptime(trade_date, "%Y-%m-%d").date()
    start_date = (day - timedelta(days=_THS_HISTORY_WINDOW_DAYS)).strftime("%Y%m%d")
    end_date = trade_date.replace("-", "")

    if board_type == "industry":
        name_df = ak.stock_board_industry_name_ths()
    elif board_type == "concept":
        name_df = ak.stock_board_concept_name_ths()
    else:
        raise ValueError(f"unknown historical board type: {board_type}")

    if name_df is None or name_df.empty or "name" not in name_df.columns:
        return {
            "ok": False,
            "reason": f"{board_type}: empty THS name list",
            "top5": [],
            "bottom5": [],
            "warnings": [],
            "skipped": 0,
        }

    names = [str(value) for value in name_df["name"]]

    entry_by_name, warnings, skipped = _fetch_th_boards_concurrent(
        board_type=board_type,
        names=names,
        start_date=start_date,
        end_date=end_date,
        trade_date=trade_date,
    )

    entries = list(entry_by_name.values())

    if not entries:
        return {
            "ok": False,
            "reason": f"{board_type}: no valid board rows for {trade_date}",
            "top5": [],
            "bottom5": [],
            "warnings": warnings,
            "skipped": skipped,
        }

    warnings.append(f"{board_type}:skipped={skipped}")

    return {
        "ok": True,
        "reason": "OK",
        "top5": sorted(
            entries,
            key=lambda item: item["changePct"],
            reverse=True,
        )[:5],
        "bottom5": sorted(
            entries,
            key=lambda item: item["changePct"],
        )[:5],
        "warnings": warnings,
        "skipped": skipped,
    }


def _collect_sectors_historical(
    trade_date: str,
) -> dict[str, Any]:
    """历史回补入口：行业/概念各取全部板块 D 日涨跌幅前5/跌幅前5。

    - 拉取抛异常（网络/封锁）→ fail-closed：UNAVAILABLE +
      reason=THS_HISTORICAL_FETCH_FAILED + errors 摘要，不得半成品 FINAL；
    - 行业或概念任一侧全部拉取失败 → 该侧保持 UNAVAILABLE 语义，整体不伪造
      FINAL，原因记入 errors/sourceWarnings。
    """
    result: dict[str, Any] = {
        "status": ModuleStatus.UNAVAILABLE.value,
        "dataDate": trade_date,
        "source": ["THS"],
        "method": THS_HISTORICAL_METHOD,
        "reason": None,
        "industryTop5": [],
        "industryBottom5": [],
        "conceptTop5": [],
        "conceptBottom5": [],
        "errors": [],
        "sourceWarnings": [],
    }

    try:
        industry = _ths_historical_board_rank(
            board_type="industry",
            trade_date=trade_date,
        )
        concept = _ths_historical_board_rank(
            board_type="concept",
            trade_date=trade_date,
        )
    except Exception as exc:  # noqa: BLE001
        result["reason"] = "THS_HISTORICAL_FETCH_FAILED"
        result["errors"].append(
            "THS_HISTORICAL_FETCH_FAILED: "
            f"{type(exc).__name__}: {exc}"
        )
        return result

    # 任一侧拿不到 D 全量 → 该侧 UNAVAILABLE，整体不伪造 FINAL
    if not industry["ok"] or not concept["ok"]:
        for key, side in (
            ("industry", industry),
            ("concept", concept),
        ):
            if not side["ok"]:
                result["errors"].append(
                    f"{key}: {side['reason']}"
                )
                result["sourceWarnings"].extend(
                    side.get("warnings", [])
                )

        result["reason"] = "THS_HISTORICAL_UNAVAILABLE"
        return result

    result["sourceWarnings"] = (
        industry.get("warnings", [])
        + concept.get("warnings", [])
    )
    result["industryTop5"] = industry["top5"]
    result["industryBottom5"] = industry["bottom5"]
    result["conceptTop5"] = concept["top5"]
    result["conceptBottom5"] = concept["bottom5"]
    result["status"] = ModuleStatus.FINAL.value
    result["reason"] = None
    return result


def collect_sectors(
    trade_date: str,
) -> dict[str, Any]:
    from datetime import datetime

    from collector.schema import TZ_SHANGHAI

    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        # 历史回补分支：THS 板块历史指数 → D 日行业/概念 TOP5/BOTTOM5。
        return _collect_sectors_historical(trade_date)

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY", "THS"],
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

        if source_errors:
            # R9-P3-02：前序源失败只作运维观测，不影响 health
            result["sourceWarnings"] = source_errors

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
