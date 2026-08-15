"""任务公共逻辑：快照构建、幂等写入、manifest/status 更新。"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from collector.calendar import is_trading_day, previous_trading_day
from collector.config import (
    DAILY_DIR,
    daily_path,
    ensure_dirs,
    load_yaml,
    tmp_path,
)
from collector.schema import (
    TZ_SHANGHAI,
    canonical_json,
    finalize_snapshot,
    new_snapshot,
    now_iso,
)
from collector.status import ModuleStatus

VOLATILE_FIELDS = {
    "generatedAt",
    "updatedAt",
    "revision",
    "generationReason",
}

def resolve_target_date(raw: str) -> str:
    """解析目标日期，所有“今天”语义统一使用 Asia/Shanghai。"""
    if raw and raw != "auto":
        return date.fromisoformat(raw).isoformat()

    today = datetime.now(TZ_SHANGHAI).date()

    if is_trading_day(today, fallback_weekday=True):
        return today.isoformat()

    return previous_trading_day(
        today,
        fallback_weekday=True,
    ).isoformat()

def build_snapshot(
    trade_date: str,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    """按设计文档组装 9 大模块快照。"""
    from collector.calculators.summary import generate_summary
    from collector.modules.fund_flow import collect_fund_flow
    from collector.modules.margin import collect_margin
    from collector.modules.market_index import collect_market_index
    from collector.modules.northbound import collect_northbound
    from collector.modules.sectors import collect_sectors
    from collector.modules.sentiment import collect_sentiment
    from collector.modules.turnover import collect_turnover

    snapshot = new_snapshot(
        trade_date,
        legacy=legacy,
    )

    modules = snapshot["modules"]

    market_rules = load_yaml("market-rules.yaml")

    modules["marketIndex"] = collect_market_index(trade_date)
    modules["turnover"] = collect_turnover(
        trade_date,
        market_rules=market_rules,
    )
    modules["sentiment"] = collect_sentiment(trade_date)
    modules["sectorPerformance"] = collect_sectors(trade_date)
    modules["fundFlow"] = collect_fund_flow(trade_date)
    modules["northbound"] = collect_northbound(trade_date)
    modules["margin"] = collect_margin(trade_date)
    modules["tracks"] = _collect_tracks(trade_date, modules)
    modules["summary"] = generate_summary(snapshot)

    return finalize_snapshot(snapshot)

def _collect_tracks(
    trade_date: str,
    modules: dict[str, Any],
) -> dict[str, Any]:
    """Fail-closed 占位。

    当前送审代码尚未实现真实赛道指标采集，绝不能用 0/False 伪造评分。
    """
    cfg = load_yaml("tracks.yaml")
    tracks_cfg = cfg.get("tracks", [])

    items: list[dict[str, Any]] = []

    for tc in tracks_cfg:
        if not tc.get("enabled", True):
            continue

        items.append(
            {
                "trackId": tc["id"],
                "trackName": tc["name"],
                "positioning": tc.get("positioning", ""),
                "turnoverRank": None,
                "turnoverUniverseSize": None,
                "turnoverPercentile": None,
                "mainNetInflow": None,
                "mainNetInflowPercentile": None,
                "continuousInflowDays": None,
                "maAlignment": None,
                "rps60": None,
                "excessReturn20d": None,
                "limitUpCount": None,
                "limitUpRate": None,
                "ladderCompleteness": None,
                "redStockRatio": None,
                "coreCatalyst": {
                    "state": "UNKNOWN",
                    "text": "",
                },
                "earningsRealization": {
                    "state": "UNKNOWN",
                    "text": "",
                },
                "score": None,
                "coveragePct": 0.0,
                "decision": "INSUFFICIENT",
            }
        )

    from collector.calculators.tracks import score_tracks

    return {
        "status": ModuleStatus.UNAVAILABLE.value,
        "dataDate": trade_date,
        "configVersion": "1.0",
        "reason": "TRACK_METRICS_COLLECTOR_NOT_IMPLEMENTED",
        "items": score_tracks(items),
    }

def _semantic_payload(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """移除不应影响幂等比较的运行元数据。"""
    payload = deepcopy(snapshot)

    for field in VOLATILE_FIELDS:
        payload.pop(field, None)

    return payload

def _read_json(path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None

def write_if_changed(
    snapshot: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """语义幂等写入。

    - 时间戳/revision/generationReason 不参与 NO_CHANGE 判断；
    - 只有业务语义变化才 revision + 1；
    - force 只表示重新采集，不允许制造无意义 revision。
    """
    del force

    from collector.validators.schema import validate_snapshot

    ensure_dirs()

    path = daily_path(snapshot["tradeDate"])
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tmp_path(snapshot["tradeDate"])
    tmp.parent.mkdir(parents=True, exist_ok=True)

    finalize_snapshot(snapshot)

    validate_snapshot(snapshot)

    existing = _read_json(path)

    if existing is not None:
        old_semantic = canonical_json(
            _semantic_payload(existing)
        )
        new_semantic = canonical_json(
            _semantic_payload(snapshot)
        )

        if old_semantic == new_semantic:
            # 上一轮可能在 os.replace 后、parent fsync 前失败；即使业务语义
            # 已一致，也必须重新确认目录项耐久性，不能把不确定状态压成 NO_CHANGE
            # （R10.2-P1-01）。
            _fsync_directory(path.parent)
            return False, "NO_CHANGE"

        snapshot["generatedAt"] = (
            existing.get("generatedAt")
            or snapshot.get("generatedAt")
            or now_iso()
        )

        snapshot["revision"] = (
            int(existing.get("revision", 1)) + 1
        )
    else:
        snapshot["revision"] = max(
            1,
            int(snapshot.get("revision", 1)),
        )

    snapshot["updatedAt"] = now_iso()
    validate_snapshot(snapshot)

    text = json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    persisted = _read_json(path)

    if persisted is None:
        raise RuntimeError(
            "daily strict readback failed: "
            + str(snapshot.get("tradeDate"))
        )

    validate_snapshot(persisted)

    if canonical_json(persisted) != canonical_json(snapshot):
        raise RuntimeError(
            "daily strict readback mismatch: "
            + str(snapshot.get("tradeDate"))
        )

    return True, "CHANGED"

def _write_json_atomic(
    path,
    obj: dict[str, Any],
) -> None:
    """单 JSON 文件的耐久原子替换；提交后必须严格回读一致。"""
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(
        path.suffix + f".tmp-{os.getpid()}"
    )

    text = json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    try:
        with open(temp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)

    persisted = _read_json(path)

    if persisted is None:
        raise RuntimeError(
            f"json strict readback failed: {path}"
        )

    if canonical_json(persisted) != canonical_json(obj):
        raise RuntimeError(
            f"json strict readback mismatch: {path}"
        )

def _fsync_directory(path) -> None:
    """POSIX 下把目录项更新刷入磁盘；非 POSIX 由 os.replace + 严格回读兜底。"""
    if os.name != "posix":
        return

    fd = os.open(str(path), os.O_RDONLY)

    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_daily_for_index(
    trade_date: str,
) -> dict[str, Any]:
    """读取参与 manifest/latest 派生的 daily；身份不一致立即 fail-closed。

    文件名、snapshot.tradeDate、各 FINAL 模块 dataDate 必须同一天；
    防止错名/被改文件抬高完整性指针（R10-P2-01）。
    """
    item = _read_json(daily_path(trade_date))

    if item is None:
        raise RuntimeError(
            f"cannot read daily snapshot: {trade_date}"
        )

    if item.get("tradeDate") != trade_date:
        raise RuntimeError(
            "daily snapshot identity mismatch: "
            f"filename={trade_date} tradeDate={item.get('tradeDate')}"
        )

    modules = item.get("modules")

    if not isinstance(modules, dict):
        raise RuntimeError(
            f"daily snapshot modules invalid: {trade_date}"
        )

    # writer 已保证 FINAL dataDate == tradeDate；读侧再次做最关键的身份防御
    for name, module in modules.items():
        if (
            isinstance(module, dict)
            and module.get("status") == ModuleStatus.FINAL.value
            and module.get("dataDate") != trade_date
        ):
            raise RuntimeError(
                "daily module identity mismatch: "
                f"date={trade_date} module={name} "
                f"dataDate={module.get('dataDate')}"
            )

    # R10.2 新增 PARTIAL tracks 可以参与 CLOSE_COMPLETE，因此只校验 FINAL
    # dataDate 已不足以覆盖索引身份。当前 validator 允许的 PARTIAL
    # （sentiment / tracks）都要求 dataDate == tradeDate，读侧同步执行该身份防线
    # （R10.2-P2-01）。
    for name, module in modules.items():
        if (
            isinstance(module, dict)
            and module.get("status") == ModuleStatus.PARTIAL.value
            and module.get("dataDate") != trade_date
        ):
            raise RuntimeError(
                "daily PARTIAL module identity mismatch: "
                f"date={trade_date} module={name} "
                f"dataDate={module.get('dataDate')}"
            )

    return item


def _compute_derived_semantic(
    trade_date: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """manifest/latest/status 派生语义的唯一权威计算（R10.2-N03）。

    update_manifest_and_latest（重建权威）与 ensure_derived_state_consistent
    （一致性比较权威）必须共用本函数，从结构上消除两份手写计算分叉的
    可能。所有参与索引的 daily 均经 _read_daily_for_index 身份校验，
    错名/被改文件直接 raise（fail-closed，R10-P2-01）。
    """
    from collector.completeness import (
        PHASE_CLOSE_COMPLETE,
        PHASE_FINAL,
        snapshot_phase,
    )

    available_dates = _list_available_dates()

    if not available_dates:
        raise RuntimeError("no daily snapshot found")

    latest_date = available_dates[-1]

    # latest.json 的权威内容；同时触发最新日的身份校验
    authoritative_latest = _read_daily_for_index(latest_date)

    close_date: str | None = None
    final_date: str | None = None

    for value in reversed(available_dates):
        item = _read_daily_for_index(value)
        phase = snapshot_phase(item)

        # FINAL 隐含 CLOSE_COMPLETE（9 模块全 FINAL ⊃ 非 margin FINAL）
        if (
            close_date is None
            and phase in {PHASE_CLOSE_COMPLETE, PHASE_FINAL}
        ):
            close_date = value

        if final_date is None and phase == PHASE_FINAL:
            final_date = value

        if close_date is not None and final_date is not None:
            break

    errors = _collect_errors(snapshot)

    stale_modules = [
        name
        for name, module
        in snapshot.get("modules", {}).items()
        if isinstance(module, dict)
        and module.get("status")
        == ModuleStatus.STALE.value
    ]

    status_semantic = {
        "lastSuccessfulTradeDate": (
            trade_date
            if not errors
            else final_date
        ),
        # 三指针（R6-P2-03 / R7-P1）：completeness 与 health 分离
        "latestCapturedDate": latest_date,
        "latestCloseCompleteDate": close_date,
        "latestFinalDate": final_date,
        # 已废弃别名（保持旧消费者兼容），与 latestCapturedDate 同值
        "latestDate": latest_date,
        "health": (
            "DEGRADED"
            if errors or stale_modules
            else "OK"
        ),
        "errors": errors,
        "staleModules": stale_modules,
    }

    return {
        "available_dates": available_dates,
        "latest_date": latest_date,
        "close_date": close_date,
        "final_date": final_date,
        "authoritative_latest": authoritative_latest,
        "status_semantic": status_semantic,
    }


def update_manifest_and_latest(
    trade_date: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """从身份可信的 daily 文件重算 manifest/latest/status；身份冲突 fail-closed。

    三指针（R7-P1 / R6-P1-04 落地）：
    - latestCapturedDate：最新有快照文件的日期（任意阶段）；
    - latestCloseCompleteDate：最新达到 D0 CLOSE_COMPLETE 的日期；
    - latestFinalDate：最新达到 D+1 FINAL（9 模块全 FINAL）的日期。

    全部派生语义由 _compute_derived_semantic 唯一计算（R10.2-N03）。
    """
    ensure_dirs()

    data_root = DAILY_DIR.parent
    manifest_path = data_root / "manifest.json"
    latest_path = data_root / "latest.json"
    status_path = data_root / "status.json"

    semantic = _compute_derived_semantic(
        trade_date,
        snapshot,
    )

    manifest = {
        "schemaVersion": "1.2",
        "latestCapturedDate": semantic["latest_date"],
        "latestCloseCompleteDate": semantic["close_date"],
        "latestFinalDate": semantic["final_date"],
        # 已废弃别名（旧消费者兼容），与 latestCapturedDate 同值
        "latestDate": semantic["latest_date"],
        "updatedAt": now_iso(),
        "availableDates": semantic["available_dates"],
    }

    status = {
        "lastWorkflow": os.environ.get(
            "SMI_WORKFLOW",
            "manual",
        ),
        "lastRunAt": now_iso(),
        **semantic["status_semantic"],
    }

    # 先完成全部派生计算，再开始三个单文件提交；任一异常向上抛出，
    # 由调用方停止 git commit/deploy，并由下一次 consistency repair 收敛。
    _write_json_atomic(
        manifest_path,
        manifest,
    )
    _write_json_atomic(
        latest_path,
        semantic["authoritative_latest"],
    )
    _write_json_atomic(
        status_path,
        status,
    )

    return manifest


def ensure_derived_state_consistent(
    trade_date: str,
    snapshot: dict[str, Any],
) -> bool:
    """仅在派生文件缺失或语义上与 daily/本次事务不一致时重建。

    正常 NO_CHANGE 不更新时间戳、不制造 git diff；S2/S3 故障态必须被修复
    （R10-P1-01）。返回 True 表示执行了重建。

    期望语义与 update_manifest_and_latest 共用 _compute_derived_semantic，
    两个权威永不分叉（R10.2-N03）。
    """
    data_root = DAILY_DIR.parent
    manifest_path = data_root / "manifest.json"
    latest_path = data_root / "latest.json"
    status_path = data_root / "status.json"

    semantic = _compute_derived_semantic(
        trade_date,
        snapshot,
    )

    expected_manifest_semantic = {
        "schemaVersion": "1.2",
        "latestCapturedDate": semantic["latest_date"],
        "latestCloseCompleteDate": semantic["close_date"],
        "latestFinalDate": semantic["final_date"],
        "latestDate": semantic["latest_date"],
        "availableDates": semantic["available_dates"],
    }

    expected_status_semantic = semantic["status_semantic"]

    current_manifest = _read_json(manifest_path)
    current_latest = _read_json(latest_path)
    current_status = _read_json(status_path)

    def manifest_semantic(value):
        if value is None:
            return None
        return {key: value.get(key) for key in expected_manifest_semantic}

    def status_semantic(value):
        if value is None:
            return None
        return {key: value.get(key) for key in expected_status_semantic}

    needs_repair = (
        manifest_semantic(current_manifest)
        != expected_manifest_semantic
        or current_latest is None
        or canonical_json(current_latest)
        != canonical_json(
            semantic["authoritative_latest"]
        )
        or status_semantic(current_status)
        != expected_status_semantic
    )

    if not needs_repair:
        # 语义一致不等于上一事务的 parent fsync 已成功。重新 fsync 数据目录，
        # 使"提交后耐久性不确定"在重试时保持 fail-closed，直到耐久确认成功
        # （R10.2-P1-01）。
        _fsync_directory(data_root)
        return False

    update_manifest_and_latest(trade_date, snapshot)
    return True

def _list_available_dates() -> list[str]:
    dates: list[str] = []

    if not DAILY_DIR.exists():
        return dates

    for year_dir in DAILY_DIR.iterdir():
        if not year_dir.is_dir():
            continue

        for path in year_dir.glob("*.json"):
            try:
                date.fromisoformat(path.stem)
            except ValueError:
                continue

            dates.append(path.stem)

    return sorted(set(dates))

def _collect_errors(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """收集所有模块的真实错误；PARTIAL 中的子源失败也要进入健康信息（R6-P2-03）。"""
    output: list[dict[str, Any]] = []

    for name, module in snapshot.get(
        "modules",
        {},
    ).items():
        module_errors = module.get(
            "errors",
            [],
        )

        if not module_errors:
            continue

        output.append(
            {
                "module": name,
                "status": module.get("status"),
                "errors": module_errors,
            }
        )

    return output

def snapshot_hash(
    snapshot: dict[str, Any],
) -> str:
    """返回业务语义 Hash，不受运行时间戳影响。"""
    text = canonical_json(
        _semantic_payload(snapshot)
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
