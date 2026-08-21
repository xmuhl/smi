"""R13-P3-02：验收器顶层身份闭合（manifest/latest/daily）负向测试。

零联网：全部基于 tmp_path 构造的假 manifest/latest/daily。
accept.py 非包模块，用 importlib 按路径加载；LATEST_PATH 经 monkeypatch
指向临时文件，不触碰真实 web/public/data。
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_accept():
    spec = importlib.util.spec_from_file_location(
        "smi_accept", os.path.join(ROOT, "tools", "acceptance", "accept.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


accept = _load_accept()


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def _good_manifest():
    return {
        "availableDates": ["2026-08-18", "2026-08-19", "2026-08-20"],
        "latestDate": "2026-08-20",
        "latestCapturedDate": "2026-08-20",
        "latestCloseCompleteDate": "2026-08-20",
        "latestFinalDate": "2026-08-18",
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    """构造闭合的 manifest/latest/daily 三件套；返回 (manifest, daily_dir)。"""
    daily_dir = tmp_path / "daily"
    latest_path = tmp_path / "latest.json"
    monkeypatch.setattr(accept, "LATEST_PATH", str(latest_path))
    manifest = _good_manifest()
    _write_json(latest_path, {"tradeDate": "2026-08-20"})
    _write_json(daily_dir / "2026" / "2026-08-20.json", {"tradeDate": "2026-08-20"})
    return manifest, str(daily_dir)


def test_identity_happy_path(env):
    manifest, daily_dir = env
    assert accept._validate_manifest_latest_identity(manifest, daily_dir) == []


def test_identity_latest_alias_mismatch(env):
    manifest, daily_dir = env
    manifest["latestDate"] = "2026-08-19"
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("latestDate" in g for g in gaps)


def test_identity_pointer_order_violation(env):
    manifest, daily_dir = env
    manifest["latestFinalDate"] = "2026-08-19"
    manifest["latestCloseCompleteDate"] = "2026-08-18"
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("三指针顺序" in g for g in gaps)


def test_identity_pointer_not_in_available(env):
    manifest, daily_dir = env
    manifest["latestCloseCompleteDate"] = "2026-08-15"
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("不在 availableDates" in g for g in gaps)


def test_identity_latest_json_trade_date_mismatch(env, tmp_path, monkeypatch):
    manifest, daily_dir = env
    _write_json(tmp_path / "latest.json", {"tradeDate": "2026-08-19"})
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("latest.json.tradeDate" in g for g in gaps)


def test_identity_captured_daily_missing(env, tmp_path):
    manifest, daily_dir = env
    os.remove(os.path.join(daily_dir, "2026", "2026-08-20.json"))
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("daily 文件缺失" in g for g in gaps)


def test_identity_available_dates_unsorted(env):
    manifest, daily_dir = env
    manifest["availableDates"] = ["2026-08-20", "2026-08-18", "2026-08-19"]
    gaps = accept._validate_manifest_latest_identity(manifest, daily_dir)
    assert any("升序" in g for g in gaps)


def test_build_entry_snapshot_identity_mismatch(tmp_path):
    """文件名 08-20 但快照根 tradeDate=08-19 → SNAPSHOT_IDENTITY_MISMATCH。"""
    daily_dir = tmp_path / "daily"
    _write_json(
        daily_dir / "2026" / "2026-08-20.json",
        {"tradeDate": "2026-08-19", "modules": {}},
    )
    entry = accept.build_entry(
        "2026-08-20", _good_manifest(), standard=None, daily_dir=str(daily_dir)
    )
    assert entry["gap"] == "SNAPSHOT_IDENTITY_MISMATCH"
    assert entry["pass"] is False


def test_build_entry_file_invalid(tmp_path):
    daily_dir = tmp_path / "daily"
    os.makedirs(daily_dir / "2026")
    with open(daily_dir / "2026" / "2026-08-20.json", "w", encoding="utf-8") as fh:
        fh.write("{not json")
    entry = accept.build_entry(
        "2026-08-20", _good_manifest(), standard=None, daily_dir=str(daily_dir)
    )
    assert entry["gap"] == "FILE_INVALID"
    assert entry["pass"] is False
