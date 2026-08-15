"""SMI 数据状态定义与状态机。"""

from __future__ import annotations

from enum import Enum


class ModuleStatus(str, Enum):
    FINAL = "FINAL"
    PENDING = "PENDING"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


STATUS_UI = {
    ModuleStatus.FINAL: ("已更新", "ok"),
    ModuleStatus.PENDING: ("待披露", "info"),
    ModuleStatus.STALE: ("数据延迟", "warn"),
    ModuleStatus.PARTIAL: ("部分数据", "info"),
    ModuleStatus.UNAVAILABLE: ("不再披露", "neutral"),
    ModuleStatus.ERROR: ("获取失败", "error"),
}


def available_transitions(status: ModuleStatus) -> list[ModuleStatus]:
    """返回采集态允许迁移到的目标状态集合（R8-P3-02）。

    这是描述性采集状态机；持久化质量单调性由 backfill merge 单独保证。
    """
    table = {
        ModuleStatus.PENDING: [
            ModuleStatus.PENDING,
            ModuleStatus.PARTIAL,
            ModuleStatus.FINAL,
            ModuleStatus.STALE,
            ModuleStatus.UNAVAILABLE,
            ModuleStatus.ERROR,
        ],
        ModuleStatus.PARTIAL: [
            ModuleStatus.PARTIAL,
            ModuleStatus.FINAL,
            ModuleStatus.STALE,
            ModuleStatus.UNAVAILABLE,
            ModuleStatus.ERROR,
        ],
        ModuleStatus.FINAL: [
            ModuleStatus.FINAL,
            ModuleStatus.STALE,
            ModuleStatus.ERROR,
        ],
        ModuleStatus.STALE: [
            ModuleStatus.STALE,
            ModuleStatus.PARTIAL,
            ModuleStatus.FINAL,
            ModuleStatus.ERROR,
        ],
        ModuleStatus.UNAVAILABLE: [
            ModuleStatus.UNAVAILABLE,
            ModuleStatus.PARTIAL,
            ModuleStatus.FINAL,
            ModuleStatus.ERROR,
        ],
        ModuleStatus.ERROR: [
            ModuleStatus.ERROR,
            ModuleStatus.PARTIAL,
            ModuleStatus.FINAL,
            ModuleStatus.STALE,
            ModuleStatus.UNAVAILABLE,
        ],
    }
    return table.get(status, [])
