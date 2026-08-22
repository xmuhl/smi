"""R12 动态主赛道：候选选池 / 元数据匹配 / 四级判定 / universe 验证器 / netguard。

零联网：全部基于假归档与纯函数。
"""

from __future__ import annotations

import time

import collector.archive as _archive
import collector.modules.tracks as tracks_mod
from collector.calculators.tracks import _dimension_flags, _decide_four
from collector.netguard import GuardTimeoutError, net_guard


TRADE_DATE = "2026-08-19"
D1 = "2026-08-18"
D2 = "2026-08-17"
D3 = "2026-08-14"
D4 = "2026-08-13"
D5 = "2026-08-12"


def _uni_record(dt: str, rows: list[dict]) -> dict:
    return {
        "tradeDate": dt,
        "kind": "industry-universe-snapshot",
        "source": "TEST",
        "capturedAt": dt + "T16:00:00+08:00",
        "items": rows,
        "counts": {"boardCount": len(rows)},
    }


def _uni_row(
    name: str,
    amount: float,
    inflow: float,
    rise: int = 60,
    fall: int = 40,
    code: str | None = None,
) -> dict:
    return {
        "boardName": name,
        "boardCodeEm": code,
        "chgPct": 1.0,
        "amount": amount,
        "netInflow": inflow,
        "riseCount": rise,
        "fallCount": fall,
    }


def _fake_universe() -> list[dict]:
    """6 日 × 6 板：银行/煤炭大额净流入，医药净流出，房地产无元数据，电力与种子重合。"""
    plan = {
        "银行": (900.0, 5.0, "BK0475"),
        "煤炭": (800.0, 4.0, "BK0437"),
        "医药生物": (700.0, -2.0, "BK1216"),
        "房地产": (650.0, 1.0, "BK0451"),
        "证券": (600.0, 3.0, "BK0473"),
        "电力": (500.0, 2.0, "BK0428"),
    }
    dates = [D5, D4, D3, D2, D1, TRADE_DATE]
    records = []
    for dt in dates:
        rows = [
            _uni_row(name, amount + i, inflow, code=code)
            for i, (name, (amount, inflow, code)) in enumerate(plan.items())
        ]
        records.append(_uni_record(dt, rows))
    return records


def _patch_archive(monkeypatch, fake):
    def fake_read(kind, **kwargs):
        return fake.get(kind, [])

    monkeypatch.setattr(_archive, "read_records", fake_read)


# ---------------------------------------------------------------------------
# 候选选池
# ---------------------------------------------------------------------------

def test_select_candidates_rank_and_inflow_filter(monkeypatch):
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )

    cands = tracks_mod.select_candidate_boards(TRADE_DATE)
    names = [c["boardName"] for c in cands]

    # 净流出（医药生物）不入池；电力与种子重合由 collect_tracks 去重，选池层保留
    assert "医药生物" not in names
    # 排名按近5日成交额降序
    assert names.index("银行") < names.index("煤炭") < names.index("证券")
    top = cands[0]
    assert top["turnoverRank"] == 1
    assert top["universeSize"] == 6
    assert top["netInflow"] > 0
    assert top["continuousInflowDays"] == 6  # 全部 6 日净流入
    assert top["redStockRatio"] == 60.0  # 60/(60+40)


def test_select_candidates_no_today_records(monkeypatch):
    records = [r for r in _fake_universe() if r["tradeDate"] != TRADE_DATE]
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    assert tracks_mod.select_candidate_boards(TRADE_DATE) == []


def test_collect_tracks_dynamic_items_and_seed_dedup(monkeypatch):
    fake = {"industry-universe-snapshot": _fake_universe()}
    _patch_archive(monkeypatch, fake)

    result = tracks_mod.collect_tracks(TRADE_DATE)
    items = result["items"]
    ids = [it["trackId"] for it in items]

    # 种子全部保留；电力（种子）未被动态候选重复输出
    for seed in ("dividend_cnsoe", "power", "healthcare", "semiconductor_ai"):
        assert seed in ids
    assert ids.count("dyn_BK0475") == 1  # 银行
    assert ids.count("dyn_BK0437") == 1  # 煤炭

    bank = next(it for it in items if it["trackId"] == "dyn_BK0475")
    assert bank["trackName"] == "银行"
    assert bank["selectionReason"].startswith("dynamic:rank=")
    # universe 口径资金指标与红盘占比
    assert bank["mainNetInflow"] == 5.0
    assert bank["continuousInflowDays"] == 6
    assert bank["redStockRatio"] == "60%"
    # boardMetadata 定性文案命中
    assert "高股息" in bank["coreCatalyst"]

    # 房地产（无 boardMetadata 条目）定性留空（fail-closed）
    estate = next(it for it in items if it["trackId"] == "dyn_BK0451")
    assert estate["coreCatalyst"] == ""
    assert estate["earningsRealization"] == ""
    assert estate["selectionReason"].startswith("dynamic:rank=")


def test_seed_universe_rank_preferred(monkeypatch):
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )

    result = tracks_mod.collect_tracks(TRADE_DATE)
    power = next(it for it in result["items"] if it["trackId"] == "power")

    # 种子"电力"与 universe 行重合 → 全市场口径排名（6 板中成交额最小 → 6）
    assert power["turnoverRank"] == 6


# ---------------------------------------------------------------------------
# 元数据匹配
# ---------------------------------------------------------------------------

def test_match_board_metadata_alias():
    meta = {
        "电力": {"aliases": ["电力行业"], "positioning": "公用事业"},
        "医药生物": {"aliases": ["生物制品"]},
    }
    assert tracks_mod._match_board_metadata("电力行业", meta)["positioning"] == "公用事业"
    assert tracks_mod._match_board_metadata("生物制品", meta) is not None
    assert tracks_mod._match_board_metadata("未知板块", meta) is None


# ---------------------------------------------------------------------------
# 四级判定
# ---------------------------------------------------------------------------

def _track_input(**over) -> dict:
    base = {
        "trackId": "t",
        "trackName": "T",
        "turnoverRank": 2,
        "turnoverUniverseSize": 90,
        "mainNetInflow": 10.0,
        "continuousInflowDays": 4,
        "maAlignment": {"close": 12.0, "ma5": 11.0, "ma10": 10.0, "ma20": 9.0},
        "rps60": 88.0,
        "excessReturn20d": None,
        "limitUpCount": 7,
        "limitUpRate": 5.0,
        "ladderCompleteness": {"firstBoardCount": 3, "twoBoardCount": 2, "threePlusCount": 1},
        "redStockRatio": 75.0,
        "coreCatalyst": "政策催化",
        "earningsRealization": "业绩预增",
    }
    base.update(over)
    return base


def test_dimension_flags_and_core_main():
    dims = _dimension_flags(_track_input())
    assert dims == {"capital": True, "trend": True, "emotion": True, "logic": True}
    assert (
        _decide_four(80.0, dims, {"pass_min": 75, "watch_min": 55})
        == "CORE_MAIN"
    )


def test_secondary_main_missing_one_dimension():
    dims = _dimension_flags(
        _track_input(redStockRatio=50.0)  # 红盘不达标 → 情绪缺
    )
    assert dims["emotion"] is False
    assert (
        _decide_four(80.0, dims, {"pass_min": 75, "watch_min": 55})
        == "SECONDARY_MAIN"
    )


def test_emotion_data_gap_counts_as_missing():
    # 红盘数据不足但涨停/梯队可得 → 情绪判 False（无法确认达标）；
    # 决策层把"非 True"统一计为缺 1 维 → SECONDARY_MAIN
    dims = _dimension_flags(
        _track_input(redStockRatio=None)
    )
    assert dims["emotion"] is False
    assert (
        _decide_four(80.0, dims, {"pass_min": 75, "watch_min": 55})
        == "SECONDARY_MAIN"
    )


def test_all_emotion_unknown_gives_none():
    dims = _dimension_flags(
        _track_input(
            limitUpCount=None,
            ladderCompleteness=None,
            redStockRatio=None,
        )
    )
    assert dims["emotion"] is None


def test_short_line_and_pulse_avoid():
    dims = _dimension_flags(_track_input())
    assert (
        _decide_four(60.0, dims, {"pass_min": 75, "watch_min": 55})
        == "SHORT_LINE"
    )
    assert (
        _decide_four(40.0, dims, {"pass_min": 75, "watch_min": 55})
        == "PULSE_AVOID"
    )


def test_capital_fail_blocks_secondary():
    dims = _dimension_flags(
        _track_input(continuousInflowDays=1, redStockRatio=50.0)
    )
    assert dims["capital"] is False
    # 资金+趋势不全达标 → 不给 SECONDARY；分数够 watch → SHORT_LINE
    assert (
        _decide_four(80.0, dims, {"pass_min": 75, "watch_min": 55})
        == "SHORT_LINE"
    )


# ---------------------------------------------------------------------------
# industry-universe-snapshot 行级验证器
# ---------------------------------------------------------------------------

def _valid_universe_line() -> dict:
    return {
        "tradeDate": "2026-08-19",
        "capturedAt": "2026-08-19T16:00:00+08:00",
        "kind": "industry-universe-snapshot",
        "source": "THS_INDUSTRY_SUMMARY_V1",
        "trackId": "*",
        "boardCode": "*",
        "items": [
            {
                "boardName": "银行",
                "boardCodeEm": "BK0475",
                "chgPct": 1.2,
                "amount": 900.5,
                "netInflow": 5.0,
                "riseCount": 60,
                "fallCount": 40,
            }
        ],
        "counts": {"boardCount": 1},
    }


def test_universe_line_valid():
    assert _archive._validate_line(_valid_universe_line()) == []


def test_universe_line_rejects_missing_name_and_bad_code():
    record = _valid_universe_line()
    record["items"][0]["boardName"] = ""
    record["items"][0]["boardCodeEm"] = "9999"
    errors = _archive._validate_line(record)
    assert any("boardName" in e for e in errors)
    assert any("boardCodeEm" in e for e in errors)


def test_universe_line_rejects_bad_numbers_and_count_mismatch():
    record = _valid_universe_line()
    record["items"][0]["netInflow"] = "many"
    record["items"][0]["riseCount"] = -1
    record["counts"]["boardCount"] = 2
    errors = _archive._validate_line(record)
    assert any("netInflow" in e for e in errors)
    assert any("riseCount" in e for e in errors)
    assert any("boardCount" in e for e in errors)


# ---------------------------------------------------------------------------
# netguard
# ---------------------------------------------------------------------------

# R13-P3-01：netguard 已改为进程级隔离（POSIX fork / Windows spawn）。
# 被装饰的测试 worker 必须是模块级函数（spawn 子进程按限定名重新 import），
# 且不能依赖闭包共享状态（子进程内存独立）——重试计数改用计数文件。
import os as _os

import pytest as _pytest


@_pytest.fixture
def _real_netguard(monkeypatch):
    """netguard 专项测试必须走真实进程隔离（conftest 默认 inline 直通）。"""
    monkeypatch.delenv("SMI_NETGUARD_MODE", raising=False)


def _ng_slow() -> str:
    time.sleep(5.0)
    return "done"


def _ng_slow_with_pid(pid_path: str) -> str:
    with open(pid_path, "w") as fh:
        fh.write(str(_os.getpid()))
    time.sleep(30.0)
    return "done"


def _ng_quick() -> int:
    return 42


def _ng_boom() -> None:
    raise ValueError("boom")


def _ng_flaky(counter_path: str) -> str:
    n = 0
    if _os.path.exists(counter_path):
        with open(counter_path) as fh:
            n = int(fh.read() or "0")
    n += 1
    with open(counter_path, "w") as fh:
        fh.write(str(n))
    if n == 1:
        raise RuntimeError("transient")
    return "ok"


def _ng_dataframe():
    import pandas as pd

    return pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})


def _ng_unpicklable_exc() -> None:
    # 异常对象携带 lambda：不可 pickle，应退化为 GuardedCallError
    raise RuntimeError("unpicklable", lambda: None)


def _pid_alive(pid: int) -> bool:
    if _os.name == "posix":
        try:
            _os.kill(pid, 0)
        except OSError:
            return False
        return True
    # Windows：os.kill(pid, 0) 会调用 TerminateProcess（危险且语义不符），
    # 用 OpenProcess + GetExitCodeProcess 只读探测（STILL_ACTIVE=259）
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong(0)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def test_net_guard_timeout_raises(_real_netguard):
    slow = net_guard(timeout=0.5, retries=0)(_ng_slow)
    started = time.time()
    try:
        slow()
        raise AssertionError("should have timed out")
    except GuardTimeoutError:
        pass
    # spawn（Windows）子进程启动有秒级开销，阈值放宽但仍远小于 worker 的 5s
    assert time.time() - started < 8.0


def test_net_guard_timeout_kills_worker(tmp_path, _real_netguard):
    pid_path = str(tmp_path / "worker.pid")
    slow = net_guard(timeout=1.5, retries=0)(_ng_slow_with_pid)
    try:
        slow(pid_path)
        raise AssertionError("should have timed out")
    except GuardTimeoutError:
        pass
    with open(pid_path) as fh:
        pid = int(fh.read())
    # 超时后 worker 子进程必须已被终止（R13-P3-01 核心回归断言）
    assert not _pid_alive(pid), f"worker pid {pid} still alive after hard timeout"


def test_net_guard_passes_result_and_exception(_real_netguard):
    quick = net_guard(timeout=30.0, retries=0)(_ng_quick)
    assert quick() == 42

    boom = net_guard(timeout=30.0, retries=0)(_ng_boom)
    try:
        boom()
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_net_guard_retries_then_succeeds(tmp_path, _real_netguard):
    counter = str(tmp_path / "calls.txt")
    flaky = net_guard(timeout=30.0, retries=1, backoff=0.05)(_ng_flaky)
    assert flaky(counter) == "ok"
    with open(counter) as fh:
        assert int(fh.read()) == 2


def test_net_guard_retries_zero_never_respawns(tmp_path, _real_netguard):
    # THS/mini_racer 语义：retries=0 时失败绝不产生第二个子进程
    counter = str(tmp_path / "calls.txt")
    once = net_guard(timeout=30.0, retries=0)(_ng_flaky)
    try:
        once(counter)
        raise AssertionError("first call should fail")
    except RuntimeError:
        pass
    with open(counter) as fh:
        assert int(fh.read()) == 1


def test_net_guard_dataframe_result_picklable(_real_netguard):
    get_df = net_guard(timeout=30.0, retries=0)(_ng_dataframe)
    df = get_df()
    assert list(df["a"]) == [1, 2]
    assert list(df["b"]) == ["x", "y"]


def test_net_guard_unpicklable_exception_fails_closed(_real_netguard):
    from collector.netguard import GuardedCallError

    boom = net_guard(timeout=30.0, retries=0)(_ng_unpicklable_exc)
    try:
        boom()
        raise AssertionError("should have raised GuardedCallError")
    except GuardedCallError:
        pass


# 负向变异说明（R13-P3-01 [FIX] 验收第 8 条，手工执行）：
# 删除 netguard._terminate_process 中的 process.kill() 分支后，
# test_net_guard_timeout_kills_worker 应变红（terminate 杀不掉时 pid 仍存活）。


# ---------------------------------------------------------------------------
# R12 复核修订轮新增：P1-1/P1-3/P2-5/P2-6/P2-8/P2-9 回归防护
# ---------------------------------------------------------------------------

def test_p2_6_names_overlap_strict():
    # 规范化相等：电力 == 电力行业；子串不再误伤
    assert tracks_mod._names_overlap("电力", {"电力", "银行"})
    assert tracks_mod._names_overlap("电力行业", {"电力"})
    assert not tracks_mod._names_overlap("电力设备", {"电力"})
    assert not tracks_mod._names_overlap("医药商业", {"医药生物"})


def test_p2_6_metadata_strict():
    meta = {"电力": {"aliases": ["电力行业"], "positioning": "公用事业"}}
    assert tracks_mod._match_board_metadata("电力", meta) is not None
    assert tracks_mod._match_board_metadata("电力行业", meta) is not None
    assert tracks_mod._match_board_metadata("电力设备", meta) is None


def test_p2_8_gap_truncates_window_and_streak():
    from collector.modules import tracks as t

    per_board = {
        "甲": [
            {"date": "2026-08-12", "amount": 100.0, "netInflow": 1.0,
             "riseCount": 60, "fallCount": 40, "boardCodeEm": None},
            # 08-13 该板缺行（其余板块有 → known_dates 覆盖 08-13）
            {"date": "2026-08-14", "amount": 50.0, "netInflow": 2.0,
             "riseCount": 60, "fallCount": 40, "boardCodeEm": None},
        ],
        "乙": [
            {"date": "2026-08-12", "amount": 1.0, "netInflow": 1.0,
             "riseCount": 1, "fallCount": 1, "boardCodeEm": None},
            {"date": "2026-08-13", "amount": 1.0, "netInflow": 1.0,
             "riseCount": 1, "fallCount": 1, "boardCodeEm": None},
            {"date": "2026-08-14", "amount": 1.0, "netInflow": 1.0,
             "riseCount": 1, "fallCount": 1, "boardCodeEm": None},
        ],
    }
    known = t._universe_known_dates(per_board)
    assert known == ["2026-08-12", "2026-08-13", "2026-08-14"]

    m = t._universe_metrics(per_board["甲"], "2026-08-14", 5, known_dates=known)
    # 窗口在 08-13 断档处截断：只计 08-14 的 50（08-12 不跨缺口计入）
    assert m["fiveDayAmount"] == 50.0
    assert m["amountWindowDays"] == 1
    # 连续净流入同样在断档截断 → 1 天
    assert m["continuousInflowDays"] == 1


def test_p2_5_unconfigured_qualitative_excluded_from_coverage():
    from collector.calculators.tracks import score_tracks

    # 定性列无枚举分级（中文长文本或空串）→ 不计入分母：
    # quant 全得 + excess 缺（15）→ valid=70/85 ≈ 82.4 ≥ 80 → 可正常判定
    track = _track_input(coreCatalyst="", earningsRealization="")
    out = score_tracks([track])[0]
    assert round(out["coveragePct"], 1) == 82.4
    assert out["decision"] in {"CORE_MAIN", "SECONDARY_MAIN", "SHORT_LINE"}

    # 种子（定性为文本但同样无枚举）→ 与动态候选同口径
    seeded = score_tracks([_track_input()])[0]
    assert round(seeded["coveragePct"], 1) == 82.4


def test_p2_9_secondary_missing_reads_config():
    dims = _dimension_flags(_track_input(redStockRatio=50.0, limitUpCount=2))
    # 情绪 False + 逻辑 True → 缺 1 维
    cfg = {"pass_min": 75, "watch_min": 55, "secondary_missing_dimensions_allowed": 1}
    assert _decide_four(80.0, dims, cfg) == "SECONDARY_MAIN"
    # 允许 0 维缺失时同样形态降级为 SHORT_LINE
    cfg0 = {"pass_min": 75, "watch_min": 55, "secondary_missing_dimensions_allowed": 0}
    assert _decide_four(80.0, dims, cfg0) == "SHORT_LINE"


def test_p1_1_boards_needing_history_camelcase(monkeypatch):
    import collector.archive as _ar
    from collector.jobs.archive_raw import _boards_needing_history

    # 归档中 08-10 前已有：power/BK0428 → 其余种子需要回补；无 universe → 无动态
    monkeypatch.setattr(
        _ar,
        "read_records",
        lambda kind, **kw: (
            [
                {"tradeDate": "2026-08-05", "trackId": "power", "boardCode": "BK0428"},
            ]
            if kind == "track-board-close"
            else []
        ),
    )
    expanded = [
        {"trackId": "power", "trackName": "电力", "boardType": "industry",
         "boardCode": "BK0428", "boardName": "电力", "indexNameThs": "电力"},
        {"trackId": "healthcare", "trackName": "医药生物", "boardType": "industry",
         "boardCode": "BK1216", "boardName": "医药生物", "indexNameThs": "生物制品"},
        {"trackId": "semiconductor_ai", "trackName": "半导体/AI算力", "boardType": "concept",
         "boardCode": "BK1134", "boardName": "算力概念", "indexNameThs": "东数西算(算力)"},
    ]
    boards = _boards_needing_history("2026-08-20", expanded)
    keys = [(b["trackId"], b["boardCode"]) for b in boards]
    assert keys == [("healthcare", "BK1216"), ("semiconductor_ai", "BK1134")]


def test_p1_3_ensure_universe_archived(monkeypatch):
    import collector.jobs.common as common

    called = {"collect": 0, "append": 0}

    class _FakeDT:
        @classmethod
        def now(cls, tz=None):
            import datetime as _d
            return _d.datetime(2026, 8, 20, 17, 0, tzinfo=tz)

    # _ensure_universe_archived 使用模块级 datetime 做"当日"判定，
    # 必须显式 patch 时间源，否则测试跨日即红（时间炸弹）。
    monkeypatch.setattr(common, "datetime", _FakeDT)

    monkeypatch.setattr("collector.schema.TZ_SHANGHAI", None, raising=False)
    import collector.schema as schema
    monkeypatch.setattr(schema, "TZ_SHANGHAI", __import__("datetime").timezone(__import__("datetime").timedelta(hours=8)))

    def fake_collect(date):
        called["collect"] += 1
        return {"ok": True, "record": {"tradeDate": date, "items": [], "counts": {"boardCount": 0}}}

    def fake_append(kind, record):
        called["append"] += 1
        return True, "APPENDED"

    monkeypatch.setattr(
        "collector.modules.raw_archive.collect_industry_universe", fake_collect
    )
    monkeypatch.setattr("collector.archive.append_record", fake_append)

    common._ensure_universe_archived("2026-08-20")
    assert called == {"collect": 1, "append": 1}

    # 失败路径：采集异常不抛出（fail-closed 回退种子）
    def boom(date):
        raise RuntimeError("net down")
    monkeypatch.setattr(
        "collector.modules.raw_archive.collect_industry_universe", boom
    )
    common._ensure_universe_archived("2026-08-20")  # 不抛异常即通过


# ---------------------------------------------------------------------------
# R13-P2-01：迟滞选池（入池确认/出池确认/双阈值/冷启动）与预热池
# ---------------------------------------------------------------------------

def _uni_records(plan_by_date: dict) -> list[dict]:
    """plan_by_date: {date: [(name, amount, inflow, code), ...]}"""
    records = []
    for dt, rows in plan_by_date.items():
        records.append(
            _uni_record(
                dt,
                [
                    _uni_row(name, amount, inflow, code=code)
                    for name, amount, inflow, code in rows
                ],
            )
        )
    return records


def test_r13_p2_01_entry_needs_two_of_three_days(monkeypatch):
    """入池迟滞：近 3 日至少 2 日满足准入才入池（单日翻正不入池）。"""
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
             ("房地产", 650.0, -1.0, "BK0451"), ("医药生物", 700.0, -2.0, "BK1216")],
        D1: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, -1.0, "BK0437"),
             ("房地产", 650.0, -1.0, "BK0451"), ("医药生物", 700.0, -2.0, "BK1216")],
        TRADE_DATE: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
                     ("房地产", 650.0, 1.0, "BK0451"), ("医药生物", 700.0, -2.0, "BK1216")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names        # 3/3 满足
    assert "煤炭" in names        # 2/3 满足（D1 净流出中断）
    assert "房地产" not in names  # 仅当日翻正 1/3 → 不入池
    assert "医药生物" not in names


def test_r13_p2_01_exit_needs_two_consecutive_failures(monkeypatch):
    """出池迟滞：连续 2 日触及出池条件才退出（单日失败保留池籍）。"""
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")],
        D1: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, -1.0, "BK0437")],
        TRADE_DATE: [("银行", 900.0, -1.0, "BK0475"), ("煤炭", 800.0, -1.0, "BK0437")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names        # 仅当日失败（streak=1）→ 保留
    assert "煤炭" not in names    # 连续 2 日失败 → 出池


def test_r13_p2_01_exit_streak_resets_on_healthy_day(monkeypatch):
    """R14 §5.2 回归：FAIL → PASS → FAIL 不得出池（健康日清零 streak）。

    银行 D3 入池（冷启动）；D2 净流出 streak=1；D1 恢复净流入（健康日，
    streak 必须清零）；T 仅单日失败 → 保留池籍。旧实现把两次非连续失败
    累计成 2 次错误出池。
    """
    records = _uni_records({
        D3: [("银行", 900.0, 5.0, "BK0475")],
        D2: [("银行", 900.0, -1.0, "BK0475")],
        D1: [("银行", 900.0, 5.0, "BK0475")],
        TRADE_DATE: [("银行", 900.0, -1.0, "BK0475")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names  # 两次失败不连续，streak=1 < exitConfirmDays=2


def test_r13_p2_01_incomplete_universe_day_not_exit_evidence(monkeypatch):
    """R14 §5.4 回归：部分响应日（板块行数 < 峰值*0.5）不作出池证据。

    D1 仅 1/4 板块（上游部分响应）且缺银行行——若该日被当作证据日，
    银行"缺行"会累计 exit streak；加完整性门禁后 D1 被跳过，T 日仅
    单日失败，银行保留池籍。
    """
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
             ("医药生物", 700.0, 3.0, "BK1216"), ("房地产", 650.0, 2.0, "BK0451")],
        D1: [("煤炭", 800.0, 4.0, "BK0437")],  # 部分响应：1/4 板块且缺银行
        TRADE_DATE: [("银行", 900.0, -1.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
                     ("医药生物", 700.0, 3.0, "BK1216"), ("房地产", 650.0, 2.0, "BK0451")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names  # D1 不作证据日；T 单日失败 streak=1 → 保留
    assert "煤炭" in names


def test_r13_p2_01_warming_up_not_formally_scored(monkeypatch):
    """R14 §5.3 回归：WARMING_UP 候选不输出成熟评分、不计入 coverage。

    minHistoryDays 从输出标签升级为真实评分池门禁：预热候选 score=null、
    decision=数据不足、coveragePct=null；模块 coverage 只统计正式成员。
    """
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )
    result = tracks_mod.collect_tracks(TRADE_DATE)
    bank = next(it for it in result["items"] if it["trackId"] == "dyn_BK0475")
    assert bank["dataReadiness"] == "WARMING_UP"
    assert bank["score"] is None
    assert bank["coveragePct"] is None
    assert bank["decisionCode"] == "INSUFFICIENT"
    assert bank["decision"] == "数据不足"
    assert "银行" in result["warmingUpBoards"]


def test_r13_p2_01_all_warming_fails_closed(monkeypatch):
    """R14 §5.3：全部候选预热 → 无成熟评分 → UNAVAILABLE/TRACKS_ALL_WARMING_UP。

    摘掉种子后池内只剩动态预热候选：WARMING_UP 不算正式评分成员，
    模块不得伪装出成熟结论。
    """
    real_load_yaml = tracks_mod.load_yaml

    def fake_load_yaml(name):
        cfg = real_load_yaml(name)
        if name == "tracks.yaml":
            cfg = {**cfg, "tracks": []}
        return cfg

    monkeypatch.setattr(tracks_mod, "load_yaml", fake_load_yaml)
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )
    result = tracks_mod.collect_tracks(TRADE_DATE)
    assert result["status"] == "UNAVAILABLE"
    assert result["decision"] == "TRACKS_INSUFFICIENT"
    assert result["reason"] == "TRACKS_ALL_WARMING_UP"
    assert all(it["score"] is None for it in result["items"])


def test_r13_p2_01_cold_start_falls_back_to_single_day(monkeypatch):
    """冷启动：归档历史不足 entryMinDays 时按实际天数收敛（单日可入池）。"""
    records = _uni_records({
        TRADE_DATE: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert names == ["银行", "煤炭"]


def test_r13_p2_01_dual_rank_threshold(monkeypatch):
    """双阈值：排名 9~12 的存量成员保留（exitRankMax=12），连续 2 日 >12 出池。

    排名口径是近 amountWindowDays 日累计成交额（范本口径）：第 k 日的
    排名由 D2..当日累计和决定，各日数据按此推算——
    - 证券X：D2 rank7 入池；D1 rank12 / T rank9 落入 (8,12] 保留区 → 留池；
    - 医药Y：D2 rank1 入池；D1/T 连续 2 日 rank14 > 12 → 出池；
    - 板块07：仅 D1 rank7 一日命中准入（<entryMinDays=2）→ 不入池；
    - 板块08：D1 rank8 + T rank7 两日命中 → T 日入池（正向对照）。
    净流入全正，排除资金条件干扰，只考察排名阈值。
    """
    boards = [
        # (name, D2, D1, T, code)
        ("医药Y", 1100.0, 20.0, 20.0, "BK9002"),
        ("板块01", 1000.0, 1000.0, 1000.0, "BK8001"),
        ("板块02", 990.0, 990.0, 990.0, "BK8002"),
        ("板块03", 980.0, 980.0, 980.0, "BK8003"),
        ("板块04", 970.0, 970.0, 970.0, "BK8004"),
        ("板块05", 960.0, 960.0, 960.0, "BK8005"),
        ("证券X", 955.0, 200.0, 1145.0, "BK9001"),
        ("板块06", 950.0, 950.0, 950.0, "BK8006"),
        ("板块07", 99.0, 1300.0, 50.0, "BK8007"),
        ("板块08", 95.0, 1150.0, 1150.0, "BK8008"),
        ("板块09", 90.0, 1120.0, 1120.0, "BK8009"),
        ("板块10", 85.0, 1100.0, 1100.0, "BK8010"),
        ("板块11", 80.0, 1080.0, 1080.0, "BK8011"),
        ("板块12", 75.0, 1060.0, 1060.0, "BK8012"),
    ]
    records = _uni_records({
        D2: [(n, d2, 1.0, code) for n, d2, _1, _2, code in boards],
        D1: [(n, d1, 1.0, code) for n, _1, d1, _2, code in boards],
        TRADE_DATE: [(n, t, 1.0, code) for n, _1, _2, t, code in boards],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "证券X" in names     # D1 rank12 / T rank9 ∈ (8,12] 保留区 → 留池
    assert "医药Y" not in names  # D1/T 连续 2 日 rank14 > exitRankMax=12 → 出池
    assert "板块07" not in names  # 仅 D1 一日命中准入 < entryMinDays=2 → 不入池
    assert "板块08" in names     # D1 rank8 + T rank7 两日命中 → 入池（正向对照）


def test_r13_p2_01_discovery_pool_ignores_inflow(monkeypatch):
    """预热池：只按成交额排名取前 N，不筛净流入（含净流出板块）。"""
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )
    pool = tracks_mod.select_discovery_pool(TRADE_DATE, rank_max=4)
    names = [c["boardName"] for c in pool]
    assert names == ["银行", "煤炭", "医药生物", "房地产"]  # 医药净流出仍入预热池
    assert "证券" not in names


def test_r13_p2_01_dynamic_candidate_warming_up(monkeypatch):
    """动态候选 close 历史不足 → dataReadiness=WARMING_UP（非获取失败）。"""
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )
    result = tracks_mod.collect_tracks(TRADE_DATE)
    bank = next(it for it in result["items"] if it["trackId"] == "dyn_BK0475")
    assert bank["dataReadiness"] == "WARMING_UP"
    assert bank["historyDays"] == 0
    # 种子不受 WARMING_UP 影响
    power = next(it for it in result["items"] if it["trackId"] == "power")
    assert power["dataReadiness"] != "WARMING_UP"


# ---------------------------------------------------------------------------
# R13-P2-02：coverage 三态分级（评分器 + 校验器）
# ---------------------------------------------------------------------------

def _quant_track(**overrides):
    base = {
        "trackId": "t1",
        "trackName": "测试赛道",
        "turnoverRank": 1,
        "turnoverUniverseSize": 10,
        "mainNetInflow": 5.0,
        "continuousInflowDays": 3,
        "maAlignment": {"close": 13.0, "ma5": 12.0, "ma10": 11.0, "ma20": 10.0},
        "rps60": 90.0,
        "excessReturn20d": 3.0,
        "limitUpRate": 2.0,
        "ladderCompleteness": {"firstBoardCount": 2, "twoBoardCount": 1, "threePlusCount": 0},
        "redStockRatio": 75.0,
        "coreCatalyst": "测试催化",
        "earningsRealization": "测试业绩",
    }
    base.update(overrides)
    return base


def test_r13_p2_02_scorer_three_tier():
    from collector.calculators.tracks import score_tracks

    # READY：仅 excess 缺失（15 权重）→ 85-15=70/85=82.4% ≥ target(80)
    ready = score_tracks([_quant_track()])[0]
    assert ready["dataReadiness"] == "READY"
    assert ready["decision"] != "INSUFFICIENT"

    # DEGRADED：再缺 rps60(10) 与 redStockRatio(9) → 51/85=60%…
    # 精确构造：缺 excess(15)+rps(10) → 60/85=70.6% ∈ [65,80)
    degraded = score_tracks([
        _quant_track(excessReturn20d=None, rps60=None)
    ])[0]
    assert 65.0 <= degraded["coveragePct"] < 80.0
    assert degraded["dataReadiness"] == "DEGRADED"
    assert degraded["decision"] != "INSUFFICIENT"  # 保留评分，不一刀切

    # INSUFFICIENT：仅 turnover/inflow/days → 25/85=29.4% < floor(65)
    poor = score_tracks([
        _quant_track(
            maAlignment=None, rps60=None, excessReturn20d=None,
            limitUpRate=None, ladderCompleteness=None, redStockRatio=None,
        )
    ])[0]
    assert poor["dataReadiness"] == "INSUFFICIENT"
    assert poor["decision"] == "INSUFFICIENT"


def test_r13_p2_02_validator_accepts_degraded():
    from collector.validators.schema import _validate_partial_module

    base = {"status": "PARTIAL", "dataDate": TRADE_DATE}
    # DEGRADED + 70 ∈ [floor, target) → 通过
    errors: list[str] = []
    _validate_partial_module(
        "tracks", {**base, "decision": "TRACKS_DEGRADED", "coveragePct": 70.0},
        TRADE_DATE, errors,
    )
    assert errors == []
    # SUFFICIENT + 70 < target → 拒绝
    errors = []
    _validate_partial_module(
        "tracks", {**base, "decision": "TRACKS_SUFFICIENT", "coveragePct": 70.0},
        TRADE_DATE, errors,
    )
    assert errors
    # DEGRADED + 85 ≥ target → 状态矛盾，拒绝
    errors = []
    _validate_partial_module(
        "tracks", {**base, "decision": "TRACKS_DEGRADED", "coveragePct": 85.0},
        TRADE_DATE, errors,
    )
    assert errors
    # 低于 floor → 拒绝
    errors = []
    _validate_partial_module(
        "tracks", {**base, "decision": "TRACKS_DEGRADED", "coveragePct": 60.0},
        TRADE_DATE, errors,
    )
    assert errors

