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


def _patch_archive(monkeypatch, fake, min_universe_boards=1):
    """打归档假数据。

    min_universe_boards：同步覆写 universe 完整性门禁的绝对下限。生产
    minUniverseBoards=45（已验证 90 板块快照之半），玩具宇宙只有 1~6
    板块，必须按玩具尺度放宽才能聚焦迟滞/预热语义；门禁专项测试传
    None（用真实配置）或自定义值（如 2）。
    """
    def fake_read(kind, **kwargs):
        return fake.get(kind, [])

    monkeypatch.setattr(_archive, "read_records", fake_read)
    if min_universe_boards is None:
        return
    real_load_yaml = tracks_mod.load_yaml

    def fake_load_yaml(name):
        cfg = real_load_yaml(name)
        if name == "tracks.yaml":
            sel = {
                **cfg.get("selection", {}),
                "minUniverseBoards": min_universe_boards,
            }
            cfg = {**cfg, "selection": sel}
        return cfg

    monkeypatch.setattr(tracks_mod, "load_yaml", fake_load_yaml)


# ---------------------------------------------------------------------------
# 候选选池
# ---------------------------------------------------------------------------

def test_select_candidates_rank_only_filter(monkeypatch):
    """R23-P2-02：候选发现仅按成交额排名前 entryRankMax(5)，不筛净流入。"""
    _patch_archive(
        monkeypatch, {"industry-universe-snapshot": _fake_universe()}
    )

    cands = tracks_mod.select_candidate_boards(TRADE_DATE)
    names = [c["boardName"] for c in cands]

    # 净流出（医药生物 -2/日）不再被资金条件挡在门外（排名决定监测资格）
    assert "医药生物" in names
    # 排名第 6 的电力超出前5口径，不入选池层（种子承继在 collect 层另行处理）
    assert "电力" not in names
    assert len(names) == 5
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

    # R22：种子须经状态机在池——fixture universe 仅含 电力/医药生物 两个
    # 种子的映射行（承继资格、排名健康 → 在池）；高股息中特估/半导体AI算力
    # 无 universe 行 → 不出现在监测表（不再无条件占位）。电力未被动态候选
    # 重复输出。
    assert "power" in ids and "healthcare" in ids
    assert "dividend_cnsoe" not in ids
    assert "semiconductor_ai" not in ids
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

    # 种子"电力"与 universe 行重合 → 监测口径排名（6 板中成交额最小 → 6）
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
# R13-P2-01：迟滞选池（R24 起当日前5直入；出池确认/观察保留）与预热池
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


def test_r24_entry_direct_top5_no_confirmation(monkeypatch):
    """R24（R22-P2-01 收口）：当日前5直接入池——每日范本真理源。

    2/3 日入池确认已退役（防抖由出池确认承担）：
    - 房地产：D2/D1 累计排名 6（历史未达），T 当日翻至第 4 →
      **立即入池**（单日达标即入选，无确认窗）；
    - F1：T 累计排名 6 >5 → 不入池；
    - F2：T 排名 5 → 入池；
    - 医药生物：全程净流出且排名 3 → 入池（R23-P2-02 锚点保持）。
    """
    # 单日名次目标（累计口径下推算）：
    #   D2：银1 煤2 医3 F1 4 F2 5 房6（房冷启动日未达标）
    #   D1：银1 煤2 医3 F1 4 F2 5 房6（累计）
    #   T ：银1 煤2 医3 房4 F2 5 F1 6（房当日翻进前5=第2次命中不足）
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
             ("医药生物", 700.0, -2.0, "BK1216"),
             ("F1", 200.0, 1.0, "BK9001"), ("F2", 200.0, 1.0, "BK9002"),
             ("房地产", 100.0, -1.0, "BK0451")],
        D1: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
             ("医药生物", 700.0, -2.0, "BK1216"),
             ("F1", 700.0, 1.0, "BK9001"), ("F2", 600.0, 1.0, "BK9002"),
             ("房地产", 10.0, -1.0, "BK0451")],
        TRADE_DATE: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
                     ("医药生物", 700.0, -2.0, "BK1216"),
                     ("F1", 300.0, 1.0, "BK9001"), ("F2", 700.0, 1.0, "BK9002"),
                     ("房地产", 1500.0, -1.0, "BK0451")],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    cands = tracks_mod.select_scoring_pool(TRADE_DATE)
    by = {c["boardName"]: c for c in cands}
    assert "医药生物" in by        # 全程净流出仍入池（R23-P2-02 锚点）
    assert "房地产" in by         # T 当日第4 → 直接入池（R24 无确认窗）
    assert by["房地产"]["poolQualification"] == "QUALIFIED_TODAY"
    assert "F1" in by             # D2 rank4 直入后 T 跌至第6 → 观察保留
    assert by["F1"]["poolQualification"] == "RETAINED_OBSERVATION"


def test_r13_p2_01_exit_needs_two_consecutive_failures(monkeypatch):
    """出池迟滞（R22 排名口径）：连续 2 日排名跌出 exitRankMax 才退出。

    - 银行：3 日累计排名始终第 1 → 保留（且 T 日净流入 -1 也不出局，
      R22：净流入是评分维度，非出局条件）；
    - 煤炭：D2 健康入池，D1/T 成交额坍塌致窗口累计排名连续 2 日第 14
      → 出池；净流入保持为正，排除资金条件干扰。
    12 个 filler 板块 500/日把坍塌日累计排名压到 13 名开外。
    """
    fillers = [(f"板块{i:02d}", 500.0, 1.0, f"BK80{i:02d}") for i in range(1, 13)]
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")] + fillers,
        D1: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 10.0, 4.0, "BK0437")] + fillers,
        TRADE_DATE: [("银行", 900.0, -1.0, "BK0475"), ("煤炭", 10.0, 4.0, "BK0437")] + fillers,
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names        # 排名 1：单日净流出不出局（R22）
    assert "煤炭" not in names    # 连续 2 日排名 >12 → 出池


def test_r13_p2_01_exit_streak_resets_on_healthy_day(monkeypatch):
    """R14 §5.2 回归（R22 排名口径）：FAIL → PASS → FAIL 不得出池。

    银行 D3 健康入池；D2 排名 13（streak=1）；D1 恢复排名 1（健康日
    streak 清零）；T 再排名 13 → streak=1 < exitConfirmDays=2 → 保留。
    旧实现把两次非连续失败累计成 2 次错误出池。
    """
    fillers = [(f"板块{i:02d}", 500.0, 1.0, f"BK80{i:02d}") for i in range(1, 13)]
    records = _uni_records({
        D3: [("银行", 900.0, 5.0, "BK0475")] + fillers,
        D2: [("银行", 10.0, 5.0, "BK0475")] + fillers,
        D1: [("银行", 900.0, 5.0, "BK0475")] + fillers,
        TRADE_DATE: [("银行", 10.0, 5.0, "BK0475")] + fillers,
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
    # 绝对下限=2：D1 仅 1 板块 < 2 → 不完整（下限 1 会把 1 板块首日
    # 也放行，无法验证门禁本身）
    _patch_archive(
        monkeypatch,
        {"industry-universe-snapshot": records},
        min_universe_boards=2,
    )

    names = [c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)]
    assert "银行" in names  # D1 不作证据日；T 单日失败 streak=1 → 保留
    assert "煤炭" in names


def test_r15_universe_cold_start_tiny_not_evidence_day(monkeypatch):
    """R15 评审问题 1 回归：冷启动部分响应不得成为证据日（真实配置）。

    生产 minUniverseBoards=45（已验证 90 板块快照之半）。归档首日只
    返回 2 个板块时，"相对自身峰值"的旧基线（peak=2×0.5=1）会把它当
    完整证据日；绝对下限必须先拒绝，直到出现 >=45 板块的可信完整日。
    """
    records = _uni_records({
        TRADE_DATE: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")],
    })
    _patch_archive(
        monkeypatch,
        {"industry-universe-snapshot": records},
        min_universe_boards=None,  # 真实生产配置（45）
    )

    assert tracks_mod.select_scoring_pool(TRADE_DATE) == []


def test_r15_universe_gate_causal_no_retro_clear(monkeypatch):
    """R15 评审问题 2 回归：未来峰值不得回溯撤销历史证据（因果门禁）。

    D2/D1 各 2 板块（均过 min=2 门禁）建立池籍；T 日上游恢复返回 6
    板块。旧"全局峰值"实现会把 threshold 抬到 3，回放时 D2/D1 被判
    不完整 → 池无解释清空（R15 复现 08-19→08-20 跳变）。因果前向
    峰值下 D2/D1 的证据资格不随 T 日变化，池籍保留。
    """
    records = _uni_records({
        D2: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")],
        D1: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437")],
        TRADE_DATE: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
                     ("医药生物", 700.0, 3.0, "BK1216"), ("房地产", 650.0, 2.0, "BK0451"),
                     ("证券", 600.0, 3.0, "BK0473"), ("电力", 500.0, 2.0, "BK0428")],
    })
    _patch_archive(
        monkeypatch,
        {"industry-universe-snapshot": records},
        min_universe_boards=2,
    )

    names = {c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)}
    # D2/D1 建立的池籍在 T 日（更高峰值出现后）仍然保留
    assert {"银行", "煤炭"} <= names


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


def test_r23_p2_01_two_layer_qualification(monkeypatch):
    """R23-P2-01 两层资格：QUALIFIED_TODAY（rank<=5）与 RETAINED_OBSERVATION
    （rank>5 未满出池确认，含观察区与出池宽限）独立分层，不得等价呈现。

    常量成交额宇宙（排名逐日稳定）：
    - 银行 rank1 / 医药B rank3：当日范本资格 → QUALIFIED_TODAY；
    - 证券C rank7：grandfather 承继在池、未满出池确认 → RETAINED_OBSERVATION
      （曾入选语义由承继资格模拟）；
    - 尾部D rank14：grandfather 承继但连续 2 日 >12 → 出池（对照）。
    """
    boards = [
        ("银行", 1400.0, "BK0475"), ("医药B", 1200.0, "BK1216"),
        ("证券C", 700.0, "BK0473"), ("尾部D", 60.0, "BK0451"),
    ] + [(f"填{i:02d}", 1000.0 - i * 40.0, f"BK80{i:02d}") for i in range(1, 11)]
    plan = {
        dt: [(n, a, 1.0, c) for n, a, c in boards]
        for dt in (D2, D1, TRADE_DATE)
    }
    _patch_archive(monkeypatch, {"industry-universe-snapshot": _uni_records(plan)})

    cands = tracks_mod.select_scoring_pool(
        TRADE_DATE, grandfather=["证券C", "尾部D"]
    )
    by_name = {c["boardName"]: c for c in cands}

    # 常量宇宙单日排名：银行1 医药B2 填01..10 3-12 证券C13 尾部D14
    # ——重新设计为稳定名次：填板 1300..1000（rank3-12），证券C 700 rank13
    # 超出 exitRankMax=12 → 出池。改用以下断言前先校准排名：
    rank = {c["boardName"]: c["turnoverRank"] for c in cands}
    assert rank.get("银行") == 1
    assert by_name["银行"]["poolQualification"] == "QUALIFIED_TODAY"
    assert by_name["医药B"]["poolQualification"] == "QUALIFIED_TODAY"
    # 证券C 若 rank<=5 则 QUALIFIED_TODAY，rank>5 未满出池确认则 RETAINED
    c_rank = by_name["证券C"]["turnoverRank"]
    assert by_name["证券C"]["poolQualification"] == (
        "QUALIFIED_TODAY" if c_rank <= 5 else "RETAINED_OBSERVATION"
    )
    # 尾部D：rank14 连续 2 日 >12 → 出池（不在池）
    assert "尾部D" not in by_name


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



# ---------------------------------------------------------------------------
# R22-DEF-01（人工验收）：种子并入状态机 / 仅排名出池 / 无数据日空池
# ---------------------------------------------------------------------------

def test_r22_exit_hit_rank_only():
    """出池判定单元：仅排名口径（净流入不参与）。

    实证锚点：2026-08-21 生产数据 半导体 rank1/inflow-10.51（留池）、
    电力 rank24/inflow+14.82（出池轨迹第 2 日）。
    """
    assert tracks_mod._exit_hit({"turnoverRank": 1, "netInflow": -730.77}, 12) is False
    assert tracks_mod._exit_hit({"turnoverRank": 24, "netInflow": 14.82}, 12) is True
    assert tracks_mod._exit_hit({"turnoverRank": None, "netInflow": 5.0}, 12) is True
    assert tracks_mod._exit_hit(None, 12) is True


def test_r22_grandfather_seed_exits_after_two_rank_failures(monkeypatch):
    """承继种子与动态成员同规则：连续 2 日排名跌出 exitRankMax → 出池。

    电力 D3/D2 累计排名第 9（∈(8,12]：入池不达标、出池健康）——仅凭
    grandfather 资格在池；D1/T 排名第 13（12 个上方板块）连续 2 日 →
    于 T 日出池。对照组：无 grandfather 时电力从未入池（排名 9 > 8
    永不满足准入），证明其池籍唯一来源是承继资格。
    """
    early = [(f"F{i}", 600.0, 1.0, f"BK71{i}") for i in range(1, 9)]
    records = _uni_records({
        D3: [("电力", 500.0, 1.0, "BK0428")] + early,
        D2: [("电力", 500.0, 1.0, "BK0428")] + early,
        D1: [("电力", 10.0, 1.0, "BK0428")] + early
        + [(f"L{i}", 1500.0, 1.0, f"BK72{i}") for i in range(1, 5)],
        TRADE_DATE: [("电力", 10.0, 1.0, "BK0428")] + early
        + [(f"L{i}", 1500.0, 1.0, f"BK72{i}") for i in range(1, 5)],
    })
    _patch_archive(monkeypatch, {"industry-universe-snapshot": records})

    # D1：首次排名失败（streak=1）→ 承继宽限，仍在池
    names_d1 = [
        c["boardName"]
        for c in tracks_mod.select_scoring_pool(D1, grandfather=["电力"])
    ]
    assert "电力" in names_d1
    # T：连续第 2 次排名失败 → 出池
    names_t = [
        c["boardName"]
        for c in tracks_mod.select_scoring_pool(TRADE_DATE, grandfather=["电力"])
    ]
    assert "电力" not in names_t
    # 对照：无 grandfather，电力排名 9/9/13/13 从未满足准入（>entryRankMax=5）
    names_plain = [
        c["boardName"] for c in tracks_mod.select_scoring_pool(TRADE_DATE)
    ]
    assert "电力" not in names_plain


def test_r22_collect_no_universe_empty_pool(monkeypatch):
    """无 universe 归档日：种子不再占位——空池 + fail-closed UNAVAILABLE。

    人工验收决议：07-20..08-19（上游板块快照接入前/不可回溯）诚实输出
    空表，而非静态四板块"数据不足"占位。
    """
    _patch_archive(monkeypatch, {})

    result = tracks_mod.collect_tracks(TRADE_DATE)
    assert result["status"] == "UNAVAILABLE"
    assert result["decision"] == "TRACKS_INSUFFICIENT"
    assert result["reason"] == "TRACK_CRITICAL_INPUT_MISSING"
    assert result["items"] == []
    assert result["warmingUpBoards"] == []
    assert result["configVersion"] == "3.5"


def test_r22_collect_partial_universe_day_empty_output(monkeypatch):
    """当日快照不过完整性门禁（部分响应）→ 当日不输出任何池成员。

    08-18/08-19 实况：仅 3 个板块的部分快照（< minUniverseBoards）。
    """
    records = _uni_records({
        D1: [("高股息中特估", 900.0, 5.0, "BK1139"), ("电力", 800.0, 4.0, "BK0428"),
             ("医药生物", 700.0, 3.0, "BK1216")],
        TRADE_DATE: [("高股息中特估", 900.0, 5.0, "BK1139"), ("电力", 800.0, 4.0, "BK0428"),
                     ("医药生物", 700.0, 3.0, "BK1216")],
    })
    # 真实生产门禁（minUniverseBoards=45）：3 板块 < 45 → 部分响应日
    _patch_archive(
        monkeypatch,
        {"industry-universe-snapshot": records},
        min_universe_boards=None,
    )

    assert tracks_mod.select_scoring_pool(TRADE_DATE, grandfather=["电力"]) == []


def test_r22_unmapped_seed_disclosed_in_errors(monkeypatch):
    """未映射行业 universe 的种子以 module errors 明示，不得静默消失。

    实证锚点：高股息中特估为概念板块，不在 industry-universe-snapshot
    （行业口径）内——旧实现以种子互排的回退假排名掩盖该缺口。
    """
    _patch_archive(monkeypatch, {"industry-universe-snapshot": _fake_universe()})
    result = tracks_mod.collect_tracks(TRADE_DATE)

    errs = " ".join(result["errors"])
    assert "seed_unmapped_in_industry_universe:dividend_cnsoe(高股息中特估)" in errs
    assert "seed_unmapped_in_industry_universe:semiconductor_ai" in errs
    assert "seed_unmapped_in_industry_universe:power" not in errs

    ids = [it["trackId"] for it in result["items"]]
    assert "dividend_cnsoe" not in ids


def test_r23_concept_qualification_injection(monkeypatch):
    """R23-P2-03：概念资格腿注入行业 universe 联合排名（跨 taxonomy 可比）。

    高股息中特估（board_type=concept，close 归档单位=元）逐日成交额按
    /1e8 换算为亿后参与联合排名：金额（850 亿/日）大于多数行业板块 →
    获得市场名次（第 2）、映射成功、随状态机入选；errors 不再有
    seed_unmapped 披露。注入仅限行业 universe 已有日期（close 更早历史
    不扩展证据日历）。
    """
    uni_days = (D2, D1, TRADE_DATE)
    uni = _uni_records({
        dt: [("银行", 900.0, 5.0, "BK0475"), ("煤炭", 800.0, 4.0, "BK0437"),
             ("医药生物", 700.0, -2.0, "BK1216"), ("房地产", 650.0, 1.0, "BK0451")]
        for dt in uni_days
    })
    close_rows = [
        {
            "tradeDate": dt, "trackId": "dividend_cnsoe", "boardCode": "309062",
            "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1000.0,
            "volume": 1e8, "amount": 8.5e10,
            "kind": "track-board-close", "source": "TEST",
            "capturedAt": dt + "T16:00:00+08:00",
        }
        for dt in uni_days
    ]
    _patch_archive(monkeypatch, {
        "industry-universe-snapshot": uni,
        "track-board-close": close_rows,
    })

    result = tracks_mod.collect_tracks(TRADE_DATE)
    ids = {it["trackId"] for it in result["items"]}
    assert "dividend_cnsoe" in ids

    div = next(it for it in result["items"] if it["trackId"] == "dividend_cnsoe")
    # 850 亿/日 > 煤炭 800 → 联合排名第 2（银行 900 第一）
    assert div["turnoverRank"] == 2
    assert div["poolQualification"] == "QUALIFIED_TODAY"
    errs = " ".join(result["errors"])
    assert "seed_unmapped_in_industry_universe:dividend_cnsoe" not in errs
