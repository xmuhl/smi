"""模块 5：主力资金流向（统一换算为亿元，多源降级）。

R6：东财失败时降级同花顺（THS）资金流表，method 字段区分口径：
EASTMONEY_MAIN_FORCE / THS_MAIN_FORCE。THS 行业/概念净额已是亿元；
个股净额为带单位字符串（亿/万）。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from collector.adapters.sources import try_sources
from collector.schema import TZ_SHANGHAI
from collector.status import ModuleStatus

# ---------------------------------------------------------------------------
# 历史回补分支（P1）：push2his 板块历史主力资金流 → 任意历史交易日六类榜单
# ---------------------------------------------------------------------------
# 接口实测（2026-08；见 work/p1_research_fundflow.md）：
#   GET https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
#       ?lmt=20&klt=101&secid=90.BKxxxx&fields1=f1,f2,f3,f7
#       &fields2=f51,f52,f53,f54,f55
#   返回每日主力资金流日线（klines 按日期升序），字段 f51=日期、f52=主力净流入(元)、
#   f53=小单、f54=中单、f55=大单。
# 板块 secid 清单取自 push2his clist（m:90+t:2=行业、m:90+t:3=概念），若 clist
# 不可用则回退 akshare 板块名单接口（stock_board_*_name_em）。
# 诚实边界：历史免费源无可行的"个股六类榜单"批量接口，个股榜单恒为空并在 errors
# 标明 STOCK_HISTORICAL_UNAVAILABLE，绝不伪造。
# ---------------------------------------------------------------------------

EASTMONEY_HISTORICAL_METHOD = "EASTMONEY_PUSH2HIS_HISTORICAL"

# daykline lmt：约 40 根日K 覆盖 30 日历日窗口（跨节假日足够）
_HIST_KLINE_LMT = 40

# 有效板块数下限：任一侧有效板块 < 该值视为数据不完整 → fail-closed UNAVAILABLE
_HIST_MIN_BOARDS = 10

# 历史回补并发度：受控并发逐板块拉取（风格对齐 sectors._fetch_th_boards_concurrent），
# 6 线程为保守值防限流。
_FF_HIST_CONCURRENCY = 6

# 早失败熔断参数（push2his 被封时快速 fail-closed，不再 465×25s 串行超时）：
#   - 板块清单探测类请求 timeout=12；daykline 批量请求 timeout=10；
#   - 并发 as_completed 中连续失败达该阈值 → 取消剩余任务并 fail-closed；
#   - 全部完成后若有效条目为 0 且 skipped >= 板块总数 * 该比例 → 也 fail-closed。
_FF_HIST_CLIST_TIMEOUT = 12
_FF_HIST_KLINE_TIMEOUT = 10
_FF_HIST_CIRCUIT_FAIL_THRESHOLD = 12
_FF_HIST_CIRCUIT_SKIPPED_RATIO = 0.8

_PUSH2HIS_CLIST_URL = (
    "https://push2his.eastmoney.com/api/qt/clist/get"
)
_PUSH2HIS_DAYKLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
)

_EASTMONEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


def _em_http_get_json(
    url: str,
    params: dict[str, Any],
    *,
    timeout: float = 25,
) -> dict[str, Any]:
    """直连东财 push2his，不继承系统/环境代理（R9-P2-03 同款）。

    国内数据源必须直连：requests 在 Windows 上会继承系统代理（v2rayN 等），
    经代理访问东财主机会挂起/失败。trust_env=False 同时禁用环境变量代理与
    netrc。网络失败抛异常，由调用方 fail-closed。timeout 由调用方按用途指定
    （清单探测类 <= 板块回补 daykline 批量请求）。
    """
    session = requests.Session()
    session.trust_env = False

    try:
        response = session.get(
            url,
            params=params,
            timeout=timeout,
            headers=_EASTMONEY_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    finally:
        session.close()


def _em_clist_diff(market_bracket: int) -> list[dict[str, Any]]:
    """GET push2his clist，返回板块 diff 列表（f12=代码 f14=名称）。"""
    data = _em_http_get_json(
        _PUSH2HIS_CLIST_URL,
        {
            "pn": 1,
            "pz": 500,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"m:90+t:{market_bracket}",
            "fields": "f12,f14",
        },
        timeout=_FF_HIST_CLIST_TIMEOUT,
    )

    diff = (data.get("data") or {}).get("diff") or []

    if isinstance(diff, dict):
        diff = list(diff.values())

    return [item for item in diff if isinstance(item, dict)]


def _akshare_secid_list(
    board_type: str,
) -> list[tuple[str, str]]:
    """akshare 板块名单接口回退（clist 不可用时）。返回 [(代码, 名称)]。"""
    import akshare as ak

    if board_type == "industry":
        df = ak.stock_board_industry_name_em()
    elif board_type == "concept":
        df = ak.stock_board_concept_name_em()
    else:
        raise ValueError(
            f"unknown historical board type: {board_type}"
        )

    if df is None or df.empty:
        return []

    result: list[tuple[str, str]] = []

    for _, row in df.iterrows():
        code = str(row.get("板块代码", "") or "").strip()
        name = str(row.get("板块名称", "") or "").strip()

        if code and name:
            result.append((code, name))

    return result


def _fetch_secid_list(
    board_type: str,
) -> list[tuple[str, str]]:
    """获取某一侧板块 secid 清单：clist 为主，akshare 名单为回退。

    两路任一拿到有效清单（>=1）即返回；clist 返回的不足 _HIST_MIN_BOARDS 时
    回退 akshare。最终仍拿不到 → 抛出异常（调用方 fail-closed）。
    """
    market_bracket = 2 if board_type == "industry" else 3

    try:
        diff = _em_clist_diff(market_bracket)
        clist_result = [
            (str(item.get("f12", "")).strip(), str(item.get("f14", "")).strip())
            for item in diff
            if (item.get("f12") or "") and (item.get("f14") or "")
        ]

        if len(clist_result) >= _HIST_MIN_BOARDS:
            return clist_result

    except Exception:  # noqa: BLE001  clist 任何失败均回退 akshare
        pass

    return _akshare_secid_list(board_type)


def _em_ff_daykline(
    secid: str,
) -> list[str]:
    """拉取单板块历史主力资金流日线，返回 klines 原始行列表（升序）。"""
    data = _em_http_get_json(
        _PUSH2HIS_DAYKLINE_URL,
        {
            "lmt": _HIST_KLINE_LMT,
            "klt": 101,
            "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55",
        },
        timeout=_FF_HIST_KLINE_TIMEOUT,
    )

    return (data.get("data") or {}).get("klines") or []


def _f52_on_date(
    klines: list[str],
    trade_date: str,
) -> float | None:
    """从日线序列定位 trade_date 行的 f52（主力净流入，元）。"""
    for kline in klines:
        parts = str(kline).split(",")

        if len(parts) < 2:
            continue

        if parts[0].strip() != trade_date:
            continue

        try:
            value = float(parts[1])
        except (TypeError, ValueError):
            return None

        return value

    return None


def _historical_board_rank(
    board_type: str,
    trade_date: str,
) -> dict[str, Any]:
    """拉取某一侧全部板块在 D 日的主力净流入并排序。

    返回 dict：ok/reason/top10（净流入降序）/bottom10（净流出升序，最负在前）、
    warnings、skipped。侧级全失败（清单 < 下限或全部板块无有效 D 行）→ ok=False。
    """
    secids = _fetch_secid_list(board_type)

    if len(secids) < _HIST_MIN_BOARDS:
        return {
            "ok": False,
            "reason": (
                f"{board_type}: insufficient boards "
                f"{len(secids)} < {_HIST_MIN_BOARDS}"
            ),
            "top10": [],
            "bottom10": [],
            "warnings": [],
            "skipped": 0,
        }

    total = len(secids)

    from concurrent.futures import (
        ThreadPoolExecutor,
        as_completed,
    )

    def _fetch_one(
        item: tuple[str, str],
    ) -> tuple[str, tuple[str, Any]]:
        """单板块拉取。返回 (name, (status, payload)) 元组，主线程串行汇总。

        风格对齐 sectors._fetch_th_boards_concurrent：warnings/skipped 不透出
        线程内写，避免列表并发写竞态；结果收集顺序不依赖提交/完成顺序，排序
        在收集后统一进行。请求仍走模块级 requests（_em_http_get_json 内
        trust_env=False 直连），供测试 monkeypatch 同步假数据路径同样生效。
        """
        code, name = item
        secid = f"90.{code}"

        try:
            klines = _em_ff_daykline(secid)
        except Exception as exc:  # noqa: BLE001
            return (name, ("FETCH_FAILED", type(exc).__name__))

        f52 = _f52_on_date(klines, trade_date)

        if f52 is None:
            return (name, ("NO_DATE", None))

        return (name, ("OK", (code, f52)))

    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped = 0
    consecutive_failures = 0
    circuit_triggered = False

    executor = ThreadPoolExecutor(
        max_workers=_FF_HIST_CONCURRENCY
    )

    try:
        futures = [
            executor.submit(_fetch_one, (code, name))
            for code, name in secids
        ]

        for fut in as_completed(futures):
            if circuit_triggered:
                continue

            name, (status, payload) = fut.result()

            if status == "FETCH_FAILED":
                # push2his 被封/挂起：连续失败计数，达阈值即熔断
                consecutive_failures += 1
                skipped += 1
                warnings.append(
                    f"{board_type}:{name}:FETCH_FAILED:"
                    f"{payload}"
                )
            else:
                consecutive_failures = 0
                if status == "OK":
                    code, f52 = payload
                    entries.append(
                        {
                            "name": name,
                            "code": code,
                            "netInflowYi": round(
                                f52 / 1e8,
                                2,
                            ),
                        }
                    )
                else:  # NO_DATE：板块无 D 行也计 skipped
                    skipped += 1

            if (
                consecutive_failures
                >= _FF_HIST_CIRCUIT_FAIL_THRESHOLD
            ):
                # 前 N 个完成的任务全部失败 → 主机被封/挂起，取消剩余并 fail-closed
                cancelled = sum(
                    1
                    for f in futures
                    if f is not fut and not f.done()
                )
                skipped += cancelled
                warnings.append(
                    f"{board_type}:host_blocked_circuit_breaker:"
                    f"consecutive_failures={consecutive_failures}:"
                    f"cancelled={cancelled}"
                )
                circuit_triggered = True
                break
    finally:
        # 熔断后立即释放未启动任务；已在运行的线程自行超时收尾。
        executor.shutdown(
            wait=False,
            cancel_futures=True,
        )

    def _fail_closed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": reason,
            "top10": [],
            "bottom10": [],
            "warnings": warnings,
            "skipped": skipped,
        }

    if circuit_triggered:
        # 早失败：连续失败达阈值即熔断，不伪造剩余板块
        return _fail_closed(
            f"{board_type}:host_blocked_or_empty"
        )

    if not entries and (
        skipped * 5 >= total * 4
    ):
        # 有效条目为 0 且 skipped >= 板块总数 80% → 主机被封/整侧无有效数据
        return _fail_closed(
            f"{board_type}:host_blocked_or_empty"
        )

    if not entries:
        return _fail_closed(
            f"{board_type}: no valid boards for {trade_date}"
        )

    inflow, outflow = _sort_in_out(entries)

    warnings.append(f"{board_type}:skipped={skipped}")

    return {
        "ok": True,
        "reason": "OK",
        "top10": inflow[:10],
        "bottom10": outflow[:10],
        "warnings": warnings,
        "skipped": skipped,
    }


def _collect_fund_flow_historical(
    trade_date: str,
) -> dict[str, Any]:
    """历史回补入口：行业/概念各取净流入 TOP10 与净流出 TOP10。

    - 板块清单拉取失败或任一侧有效板块数 < _HIST_MIN_BOARDS → fail-closed：
      UNAVAILABLE + reason=FUNDFLOW_HISTORICAL_FETCH_FAILED + errors 摘要，
      不得半成品 FINAL；
    - 个股两类榜单：免费源无可行批量接口 → 恒为空，errors 写明
      STOCK_HISTORICAL_UNAVAILABLE（诚实缺口，不伪造）。
    """
    result: dict[str, Any] = {
        "status": ModuleStatus.UNAVAILABLE.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY_PUSH2HIS"],
        "method": EASTMONEY_HISTORICAL_METHOD,
        "unit": "亿元",
        "reason": None,
        "industryInflowTop10": [],
        "industryOutflowTop10": [],
        "conceptInflowTop10": [],
        "conceptOutflowTop10": [],
        "stockInflowTop10": [],
        "stockOutflowTop10": [],
        "errors": [],
        "sourceWarnings": [],
    }

    try:
        industry = _historical_board_rank(
            board_type="industry",
            trade_date=trade_date,
        )
        concept = _historical_board_rank(
            board_type="concept",
            trade_date=trade_date,
        )
    except Exception as exc:  # noqa: BLE001
        result["reason"] = "FUNDFLOW_HISTORICAL_FETCH_FAILED"
        result["errors"].append(
            "FUNDFLOW_HISTORICAL_FETCH_FAILED: "
            f"{type(exc).__name__}: {exc}"
        )
        return result

    # 任一侧数据不完整 → 整体 fail-closed，不伪造 FINAL
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

        result["reason"] = "FUNDFLOW_HISTORICAL_FETCH_FAILED"
        return result

    result["sourceWarnings"] = (
        industry.get("warnings", [])
        + concept.get("warnings", [])
    )
    result["industryInflowTop10"] = industry["top10"]
    result["industryOutflowTop10"] = industry["bottom10"]
    result["conceptInflowTop10"] = concept["top10"]
    result["conceptOutflowTop10"] = concept["bottom10"]

    # 个股历史榜单免费源不可行：诚实置空并标注缺口
    # P1-003：板块 4 类榜单（行业/概念 × 流入/流出）齐全但个股 2 类榜单（stockInflow/Outflow）
    # 为空——产品标准要求 minItems=10，而当前实现永远无法满足该最小值（无历史免费源）。
    # 继续标 FINAL 会与标准契约冲突，让下游误以为数据完整。改用 PARTIAL 真实反映：
    # "四榜单有数据但两榜单空"的部分状态（fail-closed）；reason 写明缺口类型，
    # sourceWarnings 列明。
    result["errors"].append("STOCK_HISTORICAL_UNAVAILABLE")
    result["status"] = ModuleStatus.PARTIAL.value
    result["reason"] = "STOCK_HISTORICAL_UNAVAILABLE"
    result["sourceWarnings"].append(
        "fundFlow_history: 个股资金流两榜单（stockInflowTop10/stockOutflowTop10）"
        "免费源不可行，与产品标准 minItems=10 冲突；模块以 PARTIAL 返回，"
        "下游需在 UI/summary 中显式标注部分数据缺口。"
    )
    return result


def _parse_yi_amount(
    value,
    *,\
    string_mode: bool = False,
) -> float | None:
    """解析 THS 资金流净额为亿元。

    string_mode=False（行业/概念）：列值已是亿元数字；
    string_mode=True（个股）：列值为带单位字符串，
    亿/万 后缀分别换算，无单位按元计（THS 小额净额格式）。
    超过 500 亿视为数据异常，返回 None 跳过。
    """
    if string_mode:
        text = str(value or "").strip().replace(",", "")
        match = re.match(r"^(-?[\d.]+)(亿|万)?$", text)
        if not match:
            return None
        try:
            number = float(match.group(1))
        except (TypeError, ValueError):
            return None
        unit = match.group(2)
        if unit == "万":
            number = number / 1e4
        elif not unit:
            number = number / 1e8
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    if pd.isna(number):
        return None
    if abs(number) > 500:
        return None
    return number


def _normalize_code(value) -> str | None:
    """A 股代码规范化：int/str → 标准 6 位字符串（R7-P2-02 修复）。

    拒绝 NaN/空/非纯数字/超过 6 位异常值。
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    if len(text) > 6:
        return None
    return text.zfill(6)

def _fetch_fund_flow(
    source: str,
) -> dict[str, Any]:
    """按指定源返回六组 TOP10 资金流。"""
    import akshare as ak

    if source == "eastmoney":
        industry = ak.stock_sector_fund_flow_rank(
            indicator="今日",
            sector_type="行业资金流",
        )
        concept = ak.stock_sector_fund_flow_rank(
            indicator="今日",
            sector_type="概念资金流",
        )
        stock = ak.stock_individual_fund_flow_rank(
            indicator="今日",
        )
        return {
            "industryInflowTop10": _split_in_out(industry)[0][:10],
            "industryOutflowTop10": _split_in_out(industry)[1][:10],
            "conceptInflowTop10": _split_in_out(concept)[0][:10],
            "conceptOutflowTop10": _split_in_out(concept)[1][:10],
            "stockInflowTop10": _split_in_out(stock)[0][:10],
            "stockOutflowTop10": _split_in_out(stock)[1][:10],
        }

    if source == "ths":
        industry = ak.stock_fund_flow_industry(
            symbol="即时",
        )
        concept = ak.stock_fund_flow_concept(
            symbol="即时",
        )
        stock = ak.stock_fund_flow_individual(
            symbol="即时",
        )
        return {
            "industryInflowTop10": _split_ths(industry, "行业", "净额")[0][:10],
            "industryOutflowTop10": _split_ths(industry, "行业", "净额")[1][:10],
            "conceptInflowTop10": _split_ths(concept, "行业", "净额")[0][:10],
            "conceptOutflowTop10": _split_ths(concept, "行业", "净额")[1][:10],
            "stockInflowTop10": _split_ths(stock, "股票简称", "净额", code_col="股票代码")[0][:10],
            "stockOutflowTop10": _split_ths(stock, "股票简称", "净额", code_col="股票代码")[1][:10],
        }

    raise ValueError(f"unknown fundflow source: {source}")


def collect_fund_flow(
    trade_date: str,
) -> dict[str, Any]:
    today = datetime.now(
        TZ_SHANGHAI
    ).date().isoformat()

    if trade_date != today:
        # 历史回补分支：push2his 板块历史主力资金流 → D 日六类榜单。
        return _collect_fund_flow_historical(trade_date)

    result: dict[str, Any] = {
        "status": ModuleStatus.FINAL.value,
        "dataDate": trade_date,
        "source": ["EASTMONEY", "THS"],
        "method": "EASTMONEY_MAIN_FORCE",
        "unit": "亿元",
        "industryInflowTop10": [],
        "industryOutflowTop10": [],
        "conceptInflowTop10": [],
        "conceptOutflowTop10": [],
        "stockInflowTop10": [],
        "stockOutflowTop10": [],
        "errors": [],
    }

    try:
        flow, used, source_errors = try_sources(
            "fundflow",
            ["eastmoney"],
            _fetch_fund_flow,
        )

        if flow is None:
            raise ValueError(
                "all fundflow sources failed: "
                + "; ".join(source_errors or [])
            )

        result.update(flow)
        result["method"] = (
            "THS_MAIN_FORCE"
            if used == "ths"
            else "EASTMONEY_MAIN_FORCE"
        )

        if source_errors:
            # R9-P3-02：前序源失败只作运维观测，不影响 health
            result["sourceWarnings"] = source_errors

    except Exception as exc:  # noqa: BLE001
        result["errors"].append(str(exc))
        result["status"] = ModuleStatus.ERROR.value

    return result


def _split_in_out(
    df,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """东财口径：净额原始金额 → 亿元。"""
    if df is None or df.empty:
        raise ValueError("empty fund-flow dataframe")

    name_col = _pick_col(
        df,
        (
            "名称",
            "name",
            "股票名称",
        ),
    )

    code_col = _pick_col(
        df,
        (
            "代码",
            "code",
        ),
    )

    main_col = _pick_col(
        df,
        (
            "今日主力净流入-净额",
            "主力净流入-净额",
            "主力净流入",
            "主力净额",
        ),
    )

    if name_col is None:
        raise ValueError(
            f"name column missing: {list(df.columns)}"
        )

    if main_col is None:
        raise ValueError(
            f"main-flow column missing: {list(df.columns)}"
        )

    rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        raw_value = pd.to_numeric(
            row.get(main_col),
            errors="coerce",
        )

        if pd.isna(raw_value):
            continue

        value_yi = float(raw_value) / 1e8

        rows.append(
            {
                "code": (
                    str(row.get(code_col, "") or "")
                    if code_col
                    else ""
                ),
                "name": str(
                    row.get(name_col, "") or ""
                ),
                "netInflowYi": round(
                    value_yi,
                    4,
                ),
            }
        )

    if not rows:
        raise ValueError(
            "no valid fund-flow rows"
        )

    return _sort_in_out(rows)


def _split_ths(
    df,
    name_col: str,
    net_col: str,
    *,
    code_col: str | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """同花顺口径：净额已是亿元（个股为带单位字符串）。"""
    if df is None or df.empty:
        raise ValueError("empty ths fund-flow dataframe")

    rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        value_yi = _parse_yi_amount(
            row.get(net_col),
            string_mode=code_col is not None,
        )

        if value_yi is None:
            continue

        rows.append(
            {
                "code": (
                    _normalize_code(row.get(code_col))
                    if code_col
                    else ""
                ),
                "name": str(
                    row.get(name_col, "") or ""
                ),
                "netInflowYi": round(
                    value_yi,
                    4,
                ),
            }
        )

    if not rows:
        raise ValueError(
            "no valid ths fund-flow rows"
        )

    return _sort_in_out(rows)


def _sort_in_out(
    rows: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    inflow = sorted(
        (
            row
            for row in rows
            if row["netInflowYi"] > 0
        ),
        key=lambda row: row["netInflowYi"],
        reverse=True,
    )

    outflow = sorted(
        (
            row
            for row in rows
            if row["netInflowYi"] < 0
        ),
        key=lambda row: row["netInflowYi"],
    )

    return inflow, outflow


def _pick_col(
    df,
    candidates: tuple[str, ...],
):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None
