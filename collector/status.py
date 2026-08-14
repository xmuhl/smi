"""SMI 数据状态定义与状态机。"""

from __future__ import annotations

from enum import Enum


class ModuleStatus(str, Enum):
    FINAL = "FINAL"
    PENDING = "PENDING"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


STATUS_UI = {
    ModuleStatus.FINAL: ("已更新", "ok"),
    ModuleStatus.PENDING: ("待披露", "info"),
    ModuleStatus.STALE: ("数据延迟", "warn"),
    ModuleStatus.UNAVAILABLE: ("不再披露", "neutral"),
    ModuleStatus.ERROR: ("获取失败", "error"),
}


def available_transitions(status: ModuleStatus) -> list[ModuleStatus]:
    """返回可迁移到的目标状态集合。"""
    table = {
        ModuleStatus.PENDING: [ModuleStatus.FINAL, ModuleStatus.STALE, ModuleStatus.ERROR],
        ModuleStatus.FINAL: [ModuleStatus.FINAL, ModuleStatus.STALE],
        ModuleStatus.STALE: [ModuleStatus.FINAL, ModuleStatus.ERROR],
        ModuleStatus.UNAVAILABLE: [ModuleStatus.UNAVAILABLE],
        ModuleStatus.ERROR: [ModuleStatus.FINAL, ModuleStatus.STALE, ModuleStatus.ERROR],
    }
    return table.get(status, [])
