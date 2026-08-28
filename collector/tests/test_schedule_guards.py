# -*- coding: utf-8 -*-
"""调度延迟补发的盘前守卫测试（2026-08-28 事故回归）。

GitHub 调度劣化时 cron 补发可延迟 7~10h（08-27/08-28 事故实测），
凌晨执行时 --date auto 解析到未收盘日：
- close_snapshot：BEFORE_CLOSE 必须以 exit 3 良性跳过（区别于
  VALIDATION_FAILED 的 exit 2），workflow 据此不打红灯、不发误报；
- archive_raw：盘前必须整体跳过——THS「即时」资金流/涨停池盘前返回
  昨日收盘值，照常归档会把旧值打成今日标签（450fd9a 脏数据根因）。
"""

from __future__ import annotations

import sys
from datetime import datetime

from collector.schema import TZ_SHANGHAI


def _pre_close_datetime_cls(hour: int = 3, minute: int = 14):
    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 28, hour, minute, 0, tzinfo=tz)

    return _FakeDateTime


def test_close_snapshot_before_close_exits_3(monkeypatch, capsys):
    import collector.jobs.close_snapshot as job

    monkeypatch.setattr(job, "resolve_target_date", lambda raw: "2026-08-28")
    monkeypatch.setattr(job, "is_trading_day", lambda *a, **k: True)
    monkeypatch.setattr(job, "datetime", _pre_close_datetime_cls())

    def _must_not_collect(*a, **k):  # noqa: ANN001
        raise AssertionError("pre-close run must not collect")

    monkeypatch.setattr(job, "build_snapshot", _must_not_collect)
    monkeypatch.setattr(sys, "argv", ["close_snapshot", "--date", "auto"])

    assert job.main() == 3
    assert "BEFORE_CLOSE 2026-08-28" in capsys.readouterr().out


def test_archive_raw_before_close_skips_without_collect(monkeypatch, capsys):
    import collector.jobs.archive_raw as job

    monkeypatch.setattr(job, "resolve_target_date", lambda raw: "2026-08-28")
    monkeypatch.setattr(job, "is_trading_day", lambda *a, **k: True)
    monkeypatch.setattr(job, "datetime", _pre_close_datetime_cls())

    def _must_not_expand(*a, **k):  # noqa: ANN001
        raise AssertionError("pre-close run must not expand tracks")

    monkeypatch.setattr(job, "_expanded_tracks", _must_not_expand)
    monkeypatch.setattr(sys, "argv", ["archive_raw", "--date", "auto"])

    assert job.main() == 0
    assert "BEFORE_CLOSE 2026-08-28" in capsys.readouterr().out


def test_archive_raw_after_close_proceeds(monkeypatch, capsys):
    """16:00 后守卫放行采集（不拦截）；测试自身零联网零落盘。"""
    import collector.jobs.archive_raw as job

    monkeypatch.setattr(job, "resolve_target_date", lambda raw: "2026-08-28")
    monkeypatch.setattr(job, "is_trading_day", lambda *a, **k: True)
    monkeypatch.setattr(job, "datetime", _pre_close_datetime_cls(hour=16, minute=35))

    def _skip(*a, **k):  # noqa: ANN001
        return {"ok": False, "reason": "SKIP_TEST", "record": None}

    # 全部采集器打桩：防止真实联网（collect_limit_up_pool 等「即时」源
    # 会真请求）与向生产归档目录写入（此前版本曾把 08-28 真实数据写进
    # web/public/data/archive/，与 dispatch 运行产物冲突）。
    for name in (
        "collect_board_close",
        "collect_board_flow",
        "collect_limit_up_pool",
        "collect_membership",
        "collect_industry_universe",
        "collect_board_close_history",
    ):
        monkeypatch.setattr(job, name, _skip)
    monkeypatch.setattr(job, "_expanded_tracks", lambda: [])
    monkeypatch.setattr(job, "_boards_needing_history", lambda *a, **k: [])
    monkeypatch.setattr(
        "collector.archive.read_records", lambda *a, **k: []
    )
    monkeypatch.setattr(sys, "argv", ["archive_raw", "--date", "auto"])

    # 全 SKIP 且零写入 → 交易日全源失败语义 rc=1；证明守卫未拦截主流程
    rc = job.main()
    assert rc == 1
    assert "BEFORE_CLOSE" not in capsys.readouterr().out
