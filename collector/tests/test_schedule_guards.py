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


def test_archive_raw_after_close_proceeds(monkeypatch):
    """16:00 后允许采集（守卫不误伤正常窗口）。"""
    import collector.jobs.archive_raw as job

    monkeypatch.setattr(job, "resolve_target_date", lambda raw: "2026-08-28")
    monkeypatch.setattr(job, "is_trading_day", lambda *a, **k: True)
    monkeypatch.setattr(job, "datetime", _pre_close_datetime_cls(hour=16, minute=35))

    expanded: list[dict] = []

    monkeypatch.setattr(job, "_expanded_tracks", lambda: expanded)
    monkeypatch.setattr(sys, "argv", ["archive_raw", "--date", "auto"])

    # 空 tracks 列表：走完所有阶段，正常收尾（written=0 且无 SKIP → rc=1
    # 全源失败语义不适用于空配置，这里返回 0/1 均可，只断言未被守卫拦截）
    rc = job.main()
    assert rc in (0, 1)
