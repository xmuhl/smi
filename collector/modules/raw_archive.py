"""⑧ raw archive 采集器：把免费数据源归一化为 JSONL 行（R7 第四优先级）。

数据源（全部实测 2026-08-16）：
- THS 板块指数历史：stock_board_industry_index_ths / stock_board_concept_index_ths
  （symbol 用 tracks.yaml 的 index_name_ths 精确名；支持历史日）
- THS 当日资金流：stock_fund_flow_industry / stock_fund_flow_concept
  （即时，仅当日；条目名缺省取 index_name_ths，可用 fund_name_ths 显式覆盖）
- 东财涨停池：stock_zt_pool_em(date)（含连板数/炸板/封板；历史窗口内可用）
- 东财板块成分：stock_board_industry_cons_em(BK 代码)（仅当日快照；
  概念成分接口实测被封 → 显式 CONCEPT_CONS_DISABLED 短路：不请求、
  不伪造；接口恢复后移除该短路即可）

失败语义（fail-closed）：
- 一切上游异常（网络/接口变更/列名变更）由 @_fail_closed 包装为
  ok=False + FETCH_FAILED:*，绝不向上抛、绝不把空/错数据写成合法行；
- 单项失败只 SKIP 该项，不影响其余项；
- 历史日调用仅当日接口 → HISTORICAL_*_UNSUPPORTED。
"""

from __future__ import annotations

import functools
from datetime import datetime
from typing import Any, Callable

from collector.config import load_yaml
from collector.schema import TZ_SHANGHAI

METHOD_INDEX_THS = "THS_INDEX_V1"
METHOD_FLOW_THS = "THS_FLOW_V1"
METHOD_ZT_POOL_EM = "EM_ZT_POOL_V1"
METHOD_MEMBERSHIP_EM = "EM_BOARD_CONS_V1"

# THS 历史指数请求起点（项目纪元；早于该日无回补意义）
ARCHIVE_HISTORY_START = "20260101"

# ST 类名称前缀（"退市"整理期前缀不计入，口径见设计文档 §39.5.5）
_ST_NAME_PREFIXES = ("*ST", "S*ST", "SST", "ST")


def is_st_stock_name(name: Any) -> bool:
    """ST 识别（名称前缀，大小写不敏感）。③ tracks / sentiment 须复用同一谓词。"""
    normalized = str(name if name is not None else "").strip().upper()
    return normalized.startswith(_ST_NAME_PREFIXES)


def _fail_closed(func: Callable) -> Callable:
    """把采集函数的一切未预期异常包装为可解释失败（不向上抛）。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "reason": f"FETCH_FAILED:{type(exc).__name__}:{str(exc)[:120]}",
                "record": None,
            }

    return wrapper


def _is_today(trade_date: str) -> bool:
    return trade_date == datetime.now(TZ_SHANGHAI).date().isoformat()


def _clean_stock_code(value: Any) -> str | None:
    """归一化 6 位数字股票代码；空/非数字/000000/非法长度返回 None。"""
    text = str(
        value if value is not None else ""
    ).strip()

    if not text or not text.isdigit():
        return None

    text = text.zfill(6)

    if len(text) != 6 or text == "000000":
        return None

    return text


def _expanded_tracks() -> list[dict[str, Any]]:
    """把 tracks.yaml 展开为「单一 board 行」列表（composite 拆成子板块）。"""
    cfg = load_yaml("tracks.yaml")
    tracks = cfg.get("tracks", [])

    expanded: list[dict[str, Any]] = []

    for track in tracks:
        if not track.get("enabled", True):
            continue

        composite = track.get("composite")

        if composite:
            for sub in composite:
                expanded.append(
                    {
                        "trackId": track["id"],
                        "trackName": track.get("name", ""),
                        "positioning": track.get("positioning", ""),
                        "boardType": sub.get("board_type", "concept"),
                        "boardCode": sub["code"],
                        "boardName": sub.get("name", ""),
                        "indexNameThs": sub.get("index_name_ths"),
                        "fundNameThs": sub.get("fund_name_ths"),
                        "weight": sub.get("weight"),
                    }
                )
            continue

        expanded.append(
            {
                "trackId": track["id"],
                "trackName": track.get("name", ""),
                "positioning": track.get("positioning", ""),
                "boardType": track.get("board_type", ""),
                "boardCode": track.get("board_code", ""),
                "boardName": track.get("expected_name", ""),
                "indexNameThs": track.get("index_name_ths"),
                "fundNameThs": track.get("fund_name_ths"),
                "weight": None,
            }
        )

    return expanded


@_fail_closed
def collect_board_close(
    trade_date: str,
    track: dict[str, Any],
) -> dict[str, Any]:
    """THS 板块指数当日 OHLCV（支持历史日）。"""
    import akshare as ak

    symbol = track.get("indexNameThs")

    if not symbol:
        return {"ok": False, "reason": "INDEX_NAME_THS_MISSING", "record": None}

    board_type = track.get("boardType")

    if board_type == "concept":
        df = ak.stock_board_concept_index_ths(
            symbol=symbol,
            start_date=ARCHIVE_HISTORY_START,
            end_date=trade_date.replace("-", ""),
        )
    elif board_type == "industry":
        df = ak.stock_board_industry_index_ths(
            symbol=symbol,
            start_date=ARCHIVE_HISTORY_START,
            end_date=trade_date.replace("-", ""),
        )
    else:
        return {
            "ok": False,
            "reason": f"UNKNOWN_BOARD_TYPE:{board_type}",
            "record": None,
        }

    if df is None or df.empty:
        return {"ok": False, "reason": "EMPTY", "record": None}

    df["日期"] = df["日期"].astype(str)

    row = df[df["日期"] == trade_date]

    if row.empty:
        return {"ok": False, "reason": "DATE_NOT_FOUND", "record": None}

    row = row.iloc[-1]

    def num(key: str):
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            return None
        return value if value == value else None

    record = {
        "tradeDate": trade_date,
        "trackId": track["trackId"],
        "trackName": track.get("trackName", ""),
        "boardType": board_type,
        "boardCode": track.get("boardCode", ""),
        "boardName": track.get("boardName", ""),
        "source": METHOD_INDEX_THS,
        "symbolThs": symbol,
        "open": num("开盘价"),
        "high": num("最高价"),
        "low": num("最低价"),
        "close": num("收盘价"),
        "volume": num("成交量"),
        "amount": num("成交额"),
    }

    if record["close"] is None:
        return {"ok": False, "reason": "CLOSE_MISSING", "record": None}

    return {"ok": True, "reason": "OK", "record": record}


@_fail_closed
def collect_board_flow(
    trade_date: str,
    track: dict[str, Any],
) -> dict[str, Any]:
    """THS 当日资金流净额（仅当日，无免费历史）。"""
    import akshare as ak

    if not _is_today(trade_date):
        return {
            "ok": False,
            "reason": "HISTORICAL_FLOW_UNSUPPORTED",
            "record": None,
        }

    symbol = track.get("fundNameThs") or track.get("indexNameThs")

    if not symbol:
        return {"ok": False, "reason": "INDEX_NAME_THS_MISSING", "record": None}

    board_type = track.get("boardType")
    name_col = "行业"

    if board_type == "concept":
        df = ak.stock_fund_flow_concept(symbol="即时")
    elif board_type == "industry":
        df = ak.stock_fund_flow_industry(symbol="即时")
    else:
        return {
            "ok": False,
            "reason": f"UNKNOWN_BOARD_TYPE:{board_type}",
            "record": None,
        }

    if df is None or df.empty:
        return {"ok": False, "reason": "EMPTY", "record": None}

    rows = df[df[name_col].astype(str) == symbol]

    if rows.empty:
        return {"ok": False, "reason": f"BOARD_NOT_FOUND:{symbol}", "record": None}

    row = rows.iloc[0]

    try:
        net = float(row["净额"])
    except (KeyError, TypeError, ValueError):
        net = None

    if net is None or net != net:
        return {"ok": False, "reason": "NET_MISSING", "record": None}

    record = {
        "tradeDate": trade_date,
        "trackId": track["trackId"],
        "trackName": track.get("trackName", ""),
        "boardType": board_type,
        "boardCode": track.get("boardCode", ""),
        "boardName": track.get("boardName", ""),
        "source": METHOD_FLOW_THS,
        "symbolThs": symbol,
        "mainNetInflow": round(net, 2),
        "unit": "亿元",
    }

    return {"ok": True, "reason": "OK", "record": record}


@_fail_closed
def collect_limit_up_pool(trade_date: str) -> dict[str, Any]:
    """东财涨停池当日全量（支持历史窗口内回补）。"""
    import akshare as ak

    pool = ak.stock_zt_pool_em(date=trade_date.replace("-", ""))

    if pool is None or pool.empty:
        return {"ok": False, "reason": "EMPTY", "record": None}

    items: list[dict[str, Any]] = []
    dropped = 0

    for _, row in pool.iterrows():
        code = _clean_stock_code(row.get("代码"))

        if code is None:
            dropped += 1
            continue

        items.append(
            {
                "code": code,
                "name": str(row.get("名称", "")),
                "changePct": _num(row.get("涨跌幅")),
                "close": _num(row.get("最新价")),
                "amount": _num(row.get("成交额")),
                "turnoverRate": _num(row.get("换手率")),
                "sealAmount": _num(row.get("封板资金")),
                "firstSealTime": str(row.get("首次封板时间", "") or ""),
                "lastSealTime": str(row.get("最后封板时间", "") or ""),
                "brokenTimes": _int(row.get("炸板次数")),
                "limitUpStat": str(row.get("涨停统计", "") or ""),
                "streak": _int(row.get("连板数")),
                "industry": str(row.get("所属行业", "") or ""),
            }
        )

    st_count = sum(1 for item in items if is_st_stock_name(item["name"]))

    record = {
        "tradeDate": trade_date,
        "trackId": "*",
        "boardCode": "*",
        "source": METHOD_ZT_POOL_EM,
        "items": items,
        "counts": {
            "nonStLimitUpCount": len(items) - st_count,
            "stLimitUpCount": st_count,
            "droppedItemCount": dropped,
        },
    }

    return {"ok": True, "reason": "OK", "record": record}


@_fail_closed
def collect_membership(
    trade_date: str,
    track: dict[str, Any],
) -> dict[str, Any]:
    """东财板块成分当日快照（仅当日）。

    概念成分接口实测被封：显式短路 CONCEPT_CONS_DISABLED，不请求
    （避免反复触发反爬升级）、不伪造；接口恢复后移除短路即可。
    """
    import akshare as ak

    if not _is_today(trade_date):
        return {
            "ok": False,
            "reason": "HISTORICAL_MEMBERSHIP_UNSUPPORTED",
            "record": None,
        }

    board_type = track.get("boardType")
    board_code = track.get("boardCode")

    if not board_code:
        return {"ok": False, "reason": "BOARD_CODE_MISSING", "record": None}

    if board_type == "industry":
        df = ak.stock_board_industry_cons_em(symbol=board_code)
    elif board_type == "concept":
        return {"ok": False, "reason": "CONCEPT_CONS_DISABLED", "record": None}
    else:
        return {
            "ok": False,
            "reason": f"UNKNOWN_BOARD_TYPE:{board_type}",
            "record": None,
        }

    if df is None or df.empty:
        return {"ok": False, "reason": "EMPTY", "record": None}

    members: list[str] = []
    dropped = 0

    for _, row in df.iterrows():
        code = _clean_stock_code(row.get("代码"))

        if code is None:
            dropped += 1
            continue

        members.append(code)

    record = {
        "tradeDate": trade_date,
        "trackId": track["trackId"],
        "trackName": track.get("trackName", ""),
        "boardType": board_type,
        "boardCode": board_code,
        "boardName": track.get("boardName", ""),
        "source": METHOD_MEMBERSHIP_EM,
        "members": members,
        "memberCount": len(members),
        "droppedMemberCount": dropped,
    }

    return {"ok": True, "reason": "OK", "record": record}


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
