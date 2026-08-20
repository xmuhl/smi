"""⑧ daily raw archive：tracks 数据底座（R7 第四优先级）。

从上线日起每日归档归一化的原始数据（JSONL 逐行追加），为 ③ tracks
采集器提供历史底座：

- track-board-close.jsonl   THS 板块历史指数当日 OHLCV（行业/概念）
- track-board-flow.jsonl    THS 当日资金流净额（行业/概念，亿元）
- limit-up-pool.jsonl       东财涨停池当日全量（含连板数/炸板/封板）
- track-membership-snapshot.jsonl 东财板块成分当日快照

设计约束：
- 每行自包含（tradeDate + capturedAt + kind 冗余），追加时按
  tradeDate+trackId+boardCode 幂等去重（重复采集不产生重复行）；
- 原子写：持锁完成 dedupe/冲突检查 → 读全文 → 追加 →
  tmp + file fsync + os.replace + parent-directory fsync + strict readback；
  只有全部成功后才返回 APPENDED；同 key 不同业务 payload 视为完整性冲突，
  fail-closed，不得压成 ALREADY_EXISTS；Windows 无 fcntl 时退化为无锁，
  依赖单写者约定（CI 由 workflow concurrency group 串行化，见设计文档 §39.5.5）；
- fail-closed：行级校验失败（缺字段/非规范日期/非有限数值/非法代码/
  负计数/计数与明细不一致/序列化异常）一律返回 INVALID 拒绝写入，
  绝不抛异常、绝不写入伪造数据；单行失败不影响其他行；
- 读取容错：非 JSON 或非 JSON 对象的损坏行静默跳过（其键不参与
  dedupe；os.replace 保证读者看到旧或新完整文件，读侧无需加锁）。
"""

from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager
from datetime import date
from threading import get_ident
from typing import Any, Iterator

from collector.config import ARCHIVE_DIR
from collector.schema import now_iso

try:  # POSIX（CI/Linux、macOS 本地）；Windows 退化见模块 docstring
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

ARCHIVE_KINDS = (
    "track-board-close",
    "track-board-flow",
    "limit-up-pool",
    "track-membership-snapshot",
    "industry-universe-snapshot",
)

# track 专属归档：trackId/boardCode 为幂等键组成部分，必填非空
_TRACK_KINDS = (
    "track-board-close",
    "track-board-flow",
    "track-membership-snapshot",
)

_REQUIRED_COMMON = ("tradeDate", "capturedAt", "kind", "source")
_CLOSE_FIELDS = ("open", "high", "low", "close", "volume", "amount")
_ITEM_NUM_FIELDS = ("changePct", "close", "amount", "turnoverRate", "sealAmount")
_ITEM_INT_FIELDS = ("brokenTimes", "streak")


def archive_path(kind: str) -> Any:
    """返回某类归档的 JSONL 路径。"""
    return ARCHIVE_DIR / f"{kind}.jsonl"


@contextmanager
def _archive_lock(path) -> Iterator[None]:
    """跨进程/跨线程排它锁（flock 建议性锁；锁文件 *.lock 不入库）。"""
    lock_path = path.parent / (path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        handle.close()  # 关闭 fd 即释放锁


def _iter_lines(path) -> Iterator[dict[str, Any]]:
    """逐行读取 JSONL；损坏行（非 JSON / 非 JSON 对象）跳过。"""
    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


def _read_keys(path, kind: str) -> set[tuple[str, str, str]]:
    """已归档行的 (tradeDate, trackId, boardCode) 键集合（用于幂等去重）。"""
    keys: set[tuple[str, str, str]] = set()

    for record in _iter_lines(path):
        if record.get("kind") != kind:
            continue
        keys.add(
            (
                str(record.get("tradeDate", "")),
                str(record.get("trackId", "")),
                str(record.get("boardCode", "")),
            )
        )

    return keys


def _is_finite_number(value: Any) -> bool:
    """有限数值（排除 bool；排除 None/字符串/NaN/Inf）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _non_negative_int(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= 0


def _validate_line(record: dict[str, Any]) -> list[str]:
    """行级校验；返回错误列表，非空则拒绝写入。"""
    errors: list[str] = []

    for field in _REQUIRED_COMMON:
        if record.get(field) in (None, ""):
            errors.append(f"missing {field}")

    trade_date = record.get("tradeDate")

    try:
        date.fromisoformat(str(trade_date))
    except (ValueError, TypeError):
        errors.append(f"invalid tradeDate: {trade_date}")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(trade_date or "")):
        errors.append(f"non-canonical tradeDate: {trade_date}")

    kind = record.get("kind")

    if kind in _TRACK_KINDS:
        for field in ("trackId", "boardCode"):
            if not str(record.get(field) or "").strip():
                errors.append(f"missing {field}")

    if kind == "track-board-close":
        for field in _CLOSE_FIELDS:
            if not _is_finite_number(record.get(field)):
                errors.append(f"{field} must be finite number")

        if all(_is_finite_number(record.get(f)) for f in ("open", "high", "low", "close")):
            low = float(record["low"])
            high = float(record["high"])
            open_ = float(record["open"])
            close = float(record["close"])
            if low > high:
                errors.append("low > high")
            if not low <= open_ <= high:
                errors.append("open out of [low, high]")
            if not low <= close <= high:
                errors.append("close out of [low, high]")

    elif kind == "track-board-flow":
        if not _is_finite_number(record.get("mainNetInflow")):
            errors.append("mainNetInflow must be finite number")

    elif kind == "limit-up-pool":
        items = record.get("items")
        items_ok = isinstance(items, list)

        if not items_ok:
            errors.append("items must be list")
        else:
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"items[{index}] must be object")
                    items_ok = False
                    continue

                code = str(item.get("code") or "")
                if not re.fullmatch(r"\d{6}", code):
                    errors.append(f"items[{index}] invalid stock code: {code}")

                for field in _ITEM_NUM_FIELDS:
                    value = item.get(field)
                    if value is not None and not _is_finite_number(value):
                        errors.append(
                            f"items[{index}].{field} must be finite number or null"
                        )

                for field in _ITEM_INT_FIELDS:
                    value = item.get(field)
                    if value is not None and not _non_negative_int(value):
                        errors.append(
                            f"items[{index}].{field} must be non-negative int or null"
                        )

        counts = record.get("counts")
        counts_ok = isinstance(counts, dict)

        if not counts_ok:
            errors.append("counts must be object")
        else:
            for field in ("nonStLimitUpCount", "stLimitUpCount"):
                if not _non_negative_int(counts.get(field)):
                    errors.append(f"counts.{field} must be non-negative int")
                    counts_ok = False

            dropped = counts.get("droppedItemCount")
            if dropped is not None and not _non_negative_int(dropped):
                errors.append("counts.droppedItemCount must be non-negative int or null")

        if items_ok and counts_ok:
            total = counts["nonStLimitUpCount"] + counts["stLimitUpCount"]
            if total != len(items):
                errors.append(
                    f"counts sum {total} != len(items)={len(items)}"
                )

    elif kind == "industry-universe-snapshot":
        # R12-PLAN-3：全市场行业板块每日快照（THS 行业汇总 + 东财代码映射），
        # 为动态主赛道选池提供全市场口径的成交额/资金/红盘底座。
        items = record.get("items")
        items_ok = isinstance(items, list)

        if not items_ok:
            errors.append("items must be list")
        else:
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"items[{index}] must be object")
                    items_ok = False
                    continue

                if not str(item.get("boardName") or "").strip():
                    errors.append(f"items[{index}] missing boardName")

                code_em = item.get("boardCodeEm")
                if code_em is not None and not re.fullmatch(
                    r"BK\d+", str(code_em)
                ):
                    errors.append(
                        f"items[{index}] invalid boardCodeEm: {code_em}"
                    )

                for field in ("chgPct", "amount", "netInflow"):
                    value = item.get(field)
                    if value is not None and not _is_finite_number(value):
                        errors.append(
                            f"items[{index}].{field} must be finite number or null"
                        )

                for field in ("riseCount", "fallCount"):
                    value = item.get(field)
                    if value is not None and not _non_negative_int(value):
                        errors.append(
                            f"items[{index}].{field} must be non-negative int or null"
                        )

        counts = record.get("counts")
        counts_ok = isinstance(counts, dict)

        if not counts_ok:
            errors.append("counts must be object")
        else:
            board_count = counts.get("boardCount")
            if not _non_negative_int(board_count):
                errors.append("counts.boardCount must be non-negative int")
                counts_ok = False

        if items_ok and counts_ok:
            if counts["boardCount"] != len(items):
                errors.append(
                    f"counts.boardCount {counts['boardCount']} "
                    f"!= len(items)={len(items)}"
                )

    elif kind == "track-membership-snapshot":
        members = record.get("members")

        if not isinstance(members, list):
            errors.append("members must be list")
        else:
            for index, code in enumerate(members):
                if not re.fullmatch(r"\d{6}", str(code or "")):
                    errors.append(f"members[{index}] invalid code: {code}")

            member_count = record.get("memberCount")
            if member_count is not None and (
                isinstance(member_count, bool)
                or not isinstance(member_count, int)
                or member_count != len(members)
            ):
                errors.append("memberCount must equal len(members)")

        dropped = record.get("droppedMemberCount")
        if dropped is not None and not _non_negative_int(dropped):
            errors.append("droppedMemberCount must be non-negative int or null")

    return errors


def _dedupe_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """返回归档幂等键。"""
    return (
        str(record.get("tradeDate", "")),
        str(record.get("trackId", "")),
        str(record.get("boardCode", "")),
    )


def _business_payload(record: dict[str, Any]) -> dict[str, Any]:
    """用于幂等一致性比较；capturedAt 仅是采集时间，不属于业务载荷。"""
    return {
        key: value
        for key, value in record.items()
        if key != "capturedAt"
    }


def _matching_records(
    path,
    kind: str,
    key: tuple[str, str, str],
) -> list[dict[str, Any]]:
    """返回指定 kind+幂等键的全部可解析记录。"""
    return [
        record
        for record in _iter_lines(path)
        if record.get("kind") == kind
        and _dedupe_key(record) == key
    ]


def _fsync_directory(path) -> None:
    """POSIX 下确认目录项更新耐久；非 POSIX 依赖 os.replace + 严格回读。"""
    if os.name != "posix":
        return

    fd = os.open(str(path), os.O_RDONLY)

    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_record(
    kind: str,
    record: dict[str, Any],
    *,
    dedupe: bool = True,
) -> tuple[bool, str]:
    """耐久原子追加一行归档；返回 (written, reason)。

    - kind 与 record.kind 必须一致；不一致直接 INVALID；
    - 幂等：同 key 已存在且现有记录业务 payload（排除 capturedAt）与本次
      一致时，重新确认目录 durability 后返回 (False, "ALREADY_EXISTS")；
      同 key 不同 payload 属完整性冲突，抛 RuntimeError fail-closed；
    - 校验/序列化失败返回 INVALID，不写入；
    - 写事务（持锁）：dedupe → 全文读入 → 修复缺失的行分隔符 →
      tmp + file fsync + os.replace + parent fsync + 严格回读。
    """
    if kind not in ARCHIVE_KINDS:
        return False, f"UNKNOWN_KIND:{kind}"

    record = dict(record)

    supplied_kind = record.get("kind")

    if supplied_kind is not None and supplied_kind != kind:
        return False, f"INVALID:kind mismatch:{supplied_kind}!={kind}"

    record["kind"] = kind
    record.setdefault("capturedAt", now_iso())

    errors = _validate_line(record)

    if errors:
        return False, "INVALID:" + ";".join(errors)

    try:
        line = (
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        return False, f"INVALID:serialize:{exc}"

    path = archive_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _archive_lock(path):
        if dedupe:
            key = _dedupe_key(record)
            matches = _matching_records(path, kind, key)

            if matches:
                # 上一轮可能 replace 已成功但 parent fsync 失败；
                # 即使 key 已存在，也必须先重新确认目录项耐久。
                _fsync_directory(path.parent)

                if len(matches) != 1:
                    raise RuntimeError(
                        f"archive duplicate-key conflict: {kind} key={key} "
                        f"count={len(matches)}"
                    )

                existing_record = matches[0]
                existing_errors = _validate_line(existing_record)

                if existing_errors:
                    raise RuntimeError(
                        f"archive existing record invalid: {kind} key={key}: "
                        + ";".join(existing_errors)
                    )

                if _business_payload(existing_record) != _business_payload(record):
                    raise RuntimeError(
                        f"archive key conflict: {kind} key={key}"
                    )

                return False, "ALREADY_EXISTS"

        existing = (
            path.read_text(encoding="utf-8")
            if path.exists()
            else ""
        )

        if existing and not existing.endswith("\n"):
            existing += "\n"

        expected = existing + line

        tmp = path.with_suffix(
            path.suffix + f".tmp-{os.getpid()}-{get_ident()}"
        )

        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(expected)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp, path)
            _fsync_directory(path.parent)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

        try:
            persisted = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(
                f"archive strict readback failed: {path}"
            ) from exc

        if persisted != expected:
            raise RuntimeError(
                f"archive strict readback mismatch: {path}"
            )

    return True, "APPENDED"


def read_records(
    kind: str,
    *,
    trade_date: str | None = None,
    track_id: str | None = None,
) -> list[dict[str, Any]]:
    """读取归档；支持按日期/赛道过滤。"""
    if kind not in ARCHIVE_KINDS:
        return []

    records = [
        record
        for record in _iter_lines(archive_path(kind))
        if (
            trade_date is None
            or record.get("tradeDate") == trade_date
        )
        and (
            track_id is None
            or record.get("trackId") == track_id
        )
    ]

    return records


def count_records(kind: str) -> int:
    if kind not in ARCHIVE_KINDS:
        return 0
    return sum(1 for _ in _iter_lines(archive_path(kind)))
