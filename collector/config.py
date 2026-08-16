"""通用路径与配置加载工具。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"
DAILY_DIR = DATA_DIR / "daily"
CALENDAR_DIR = DATA_DIR / "calendar"
# ⑧ daily raw archive：tracks 数据底座（JSONL 逐日追加，随站点部署）
ARCHIVE_DIR = DATA_DIR / "archive"


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_dirs() -> None:
    for d in (DAILY_DIR, CALENDAR_DIR, ARCHIVE_DIR, PROJECT_ROOT / "tmp"):
        d.mkdir(parents=True, exist_ok=True)


def daily_path(trade_date: str) -> Path:
    year = trade_date[:4]
    return DAILY_DIR / year / f"{trade_date}.json"


def tmp_path(trade_date: str) -> Path:
    return PROJECT_ROOT / "tmp" / f"{trade_date}.json"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "")
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
