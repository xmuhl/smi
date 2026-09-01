# -*- coding: utf-8 -*-
"""freshness-watchdog today 模式发布窗口守卫测试（2026-09-01 事故回归）。

GitHub 调度延迟补发可能把 today 巡检拖到当日 16:23 首窗之前执行
（09-01 实测 15:58 触发）：修订前把"当日未发布"当缺口——派发的
close-snapshot 恢复被 BEFORE_CLOSE 守卫（16:00 前 exit 3→0）静默跳过，
白跑一次恢复还误报红灯。修订后 16:00 CST 前良性跳过（exit 0）。

测试全程零联网零派发：站点/API/时间源全部打桩。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ALERT_DIR = REPO_ROOT / "tools" / "alert"
for _p in (str(REPO_ROOT), str(TOOLS_ALERT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import freshness_watchdog  # noqa: E402
from collector.schema import TZ_SHANGHAI  # noqa: E402


def _cst(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 1, hour, minute, 0, tzinfo=TZ_SHANGHAI)


def _patch_common(monkeypatch, *, hour: int, minute: int, site_date: str):
    monkeypatch.setattr(freshness_watchdog, "is_trading_day", lambda *a, **k: True)
    monkeypatch.setattr(freshness_watchdog, "_now_cst", lambda: _cst(hour, minute))
    monkeypatch.setattr(
        freshness_watchdog, "_fetch_json", lambda *a, **k: {"tradeDate": site_date}
    )


def test_today_mode_before_publish_window_benign_skip(monkeypatch, capsys):
    """16:00 前的 today 巡检（调度延迟补发）：不巡检、不派发、不告警、exit 0。"""
    _patch_common(monkeypatch, hour=15, minute=58, site_date="2026-08-31")

    def _must_not_call(*a, **k):  # noqa: ANN001
        raise AssertionError("pre-window run must not dispatch/notify")

    monkeypatch.setattr(freshness_watchdog, "_recent_run_created_within", _must_not_call)
    monkeypatch.setattr(freshness_watchdog, "_post_dispatch_payload", _must_not_call)
    monkeypatch.setattr(freshness_watchdog.data_health, "_notify", _must_not_call)

    assert freshness_watchdog._run_today_mode() == 0
    out = capsys.readouterr().out
    assert "BEFORE_PUBLISH_WINDOW" in out
    # 守卫先于站点探测：未发布属预期，无需拉线上状态
    assert "SITE_LATEST_STALE" not in out


def test_today_mode_after_window_stale_dispatches_and_alerts(monkeypatch, capsys):
    """窗口后仍停滞：照常派发恢复 + 告警 + exit 1（既有语义回归）。"""
    _patch_common(monkeypatch, hour=17, minute=12, site_date="2026-08-31")

    dispatched: list[tuple[str, dict]] = []
    notified: list[tuple[str, list]] = []

    monkeypatch.setattr(
        freshness_watchdog, "_recent_run_created_within", lambda *a, **k: False
    )
    monkeypatch.setattr(
        freshness_watchdog,
        "_post_dispatch_payload",
        lambda wf, inputs: dispatched.append((wf, inputs)) or True,
    )
    monkeypatch.setattr(
        freshness_watchdog.data_health,
        "_notify",
        lambda title, findings: notified.append((title, findings)),
    )

    assert freshness_watchdog._run_today_mode() == 1
    assert dispatched == [
        ("close-snapshot.yml", {"date": "auto", "deploy": "false"})
    ]
    assert notified and "SITE_LATEST_STALE" in notified[0][1][0]


def test_today_mode_fresh_exits_zero_without_dispatch(monkeypatch, capsys):
    """当日已发布：FRESH exit 0，零派发零告警。"""
    _patch_common(monkeypatch, hour=17, minute=12, site_date="2026-09-01")

    def _must_not_call(*a, **k):  # noqa: ANN001
        raise AssertionError("fresh site must not dispatch/notify")

    monkeypatch.setattr(freshness_watchdog, "_recent_run_created_within", _must_not_call)
    monkeypatch.setattr(freshness_watchdog, "_post_dispatch_payload", _must_not_call)
    monkeypatch.setattr(freshness_watchdog.data_health, "_notify", _must_not_call)

    assert freshness_watchdog._run_today_mode() == 0
    assert "FRESH" in capsys.readouterr().out
