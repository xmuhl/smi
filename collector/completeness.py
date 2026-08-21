"""D0/D+1 两阶段完整性模型（R7-P1 / R6-P1-04 正式落地）。

阶段定义：
- FINAL（D+1）：9 个模块全部 FINAL。
- CLOSE_COMPLETE（D0）：8 个非 margin 模块满足 D0 要求；margin 允许 PENDING。
- CAPTURED：快照存在但未达到 CLOSE_COMPLETE。

边界：
- FINAL 隐含 CLOSE_COMPLETE。
- 2026-07-17 Legacy 快照为 9 模块 FINAL，因此当前
  latestCloseCompleteDate 与 latestFinalDate 均可锚定 2026-07-17。
- 2026-07-20 起真实 tracks collector 尚未启用，tracks=UNAVAILABLE 的日期
  只能是 CAPTURED；真实 collector 启用后 D0 指针才会继续向后推进。
- 本模块只做纯函数判定，不触碰磁盘。
"""

from __future__ import annotations

from typing import Any

from collector.status import ModuleStatus

# D0 CLOSE_COMPLETE 需要 tracks 达到 FINAL 或 TRACKS_SUFFICIENT
# （coverage >= coverage_target_pct，缺省 80；R13-P2-02 起以
# config/track-scoring.yaml 为单一真源。TRACKS_DEGRADED 不点亮 D0）
TRACKS_SUFFICIENT_MIN_COVERAGE = 80.0


def _tracks_sufficient_min_coverage() -> float:
    try:
        from collector.config import load_yaml

        dcfg = load_yaml("track-scoring.yaml").get("decision", {}) or {}
        return float(
            dcfg.get("coverage_target_pct", TRACKS_SUFFICIENT_MIN_COVERAGE)
        )
    except Exception:  # noqa: BLE001 配置不可读时退化常量（fail-closed 等价）
        return TRACKS_SUFFICIENT_MIN_COVERAGE

NON_MARGIN_MODULES = (
    "marketIndex",
    "turnover",
    "sentiment",
    "sectorPerformance",
    "fundFlow",
    "northbound",
    "tracks",
    "summary",
)

# D+1 FINAL 要求的完整模块集合（9 个，按名锚定）
REQUIRED_MODULES = NON_MARGIN_MODULES + ("margin",)

# 阶段常量
PHASE_CAPTURED = "CAPTURED"
PHASE_CLOSE_COMPLETE = "CLOSE_COMPLETE"
PHASE_FINAL = "FINAL"


def _tracks_ok(tracks: dict[str, Any] | None) -> bool:
    """tracks 是否满足 D0：FINAL，或受约束的 PARTIAL/TRACKS_SUFFICIENT。

    fail-closed（R10-P1-02）：
    - PENDING/STALE/ERROR/UNAVAILABLE 均不得点亮 D0——即使携带
      TRACKS_SUFFICIENT decision 与达标覆盖率，也属矛盾数据；
    - sufficient 是 PARTIAL 的受约束替代态：coveragePct 必须是有限数值
      （排除 bool/Inf/NaN）且落在 [80, 100]。
    当前占位实现返回 UNAVAILABLE，故返回 False；
    ③ tracks 采集器落地后，FINAL 分支自然点亮。
    """
    from math import isfinite

    if not isinstance(tracks, dict):
        return False

    status = tracks.get("status")

    if status == ModuleStatus.FINAL.value:
        return True

    # sufficient 是 PARTIAL 的受约束替代态；PENDING/STALE/ERROR/UNAVAILABLE
    # 均不得点亮 D0。
    if status != ModuleStatus.PARTIAL.value:
        return False

    coverage = tracks.get("coveragePct")

    if (
        tracks.get("decision") != "TRACKS_SUFFICIENT"
        or not isinstance(coverage, (int, float))
        or isinstance(coverage, bool)
    ):
        return False

    value = float(coverage)

    return (
        isfinite(value)
        and _tracks_sufficient_min_coverage() <= value <= 100.0
    )


def _module_status(
    modules: dict[str, Any],
    name: str,
) -> str | None:
    module = modules.get(name)

    if not isinstance(module, dict):
        return None

    status = module.get("status")
    return status if isinstance(status, str) else None


def snapshot_phase(snapshot: dict[str, Any]) -> str:
    """返回快照的完整性阶段：CAPTURED / CLOSE_COMPLETE / FINAL。

    FINAL 按 REQUIRED_MODULES（9 个模块名）逐一锚定判定：
    缺少任一必需模块（如缺 tracks）或存在未 FINAL 必需模块的快照
    不得判 FINAL，即使现存模块全部 FINAL（防 8/9 FINAL 误抬
    latestFinalDate / latestCloseCompleteDate）。modules 中的额外
    键不参与判定（既不点亮也不阻断）。
    """
    modules = snapshot.get("modules", {})

    if not isinstance(modules, dict):
        return PHASE_CAPTURED

    # D+1 FINAL：9 个必需模块（按名锚定）全部 FINAL
    if all(
        _module_status(modules, name) == ModuleStatus.FINAL.value
        for name in REQUIRED_MODULES
    ):
        return PHASE_FINAL

    # D0 CLOSE_COMPLETE：非 margin 模块全部 FINAL（tracks 特殊要求），
    # margin 只允许 FINAL / PENDING。
    for name in NON_MARGIN_MODULES:
        module = modules.get(name)

        if not isinstance(module, dict):
            return PHASE_CAPTURED

        if name == "tracks":
            if not _tracks_ok(module):
                return PHASE_CAPTURED
            continue

        if module.get("status") != ModuleStatus.FINAL.value:
            return PHASE_CAPTURED

    margin = modules.get("margin")

    if not isinstance(margin, dict):
        return PHASE_CAPTURED

    margin_status = margin.get("status")

    if margin_status not in {
        ModuleStatus.FINAL.value,
        ModuleStatus.PENDING.value,
    }:
        return PHASE_CAPTURED

    return PHASE_CLOSE_COMPLETE
