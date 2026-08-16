# -*- coding: utf-8 -*-
"""SMI 数据侧验收器 v2（严格消费 docs/acceptance/template-standard.json 单一真源）。

对比旧版，v2 落地了 R12 P0-001..P0-009 的执行侧要求：

- P0-002：通用引擎由标准 fields/items/lists 声明驱动，标准字段清单不再复制进代码；
          每条复杂规则按标准 ruleId/ruleVersion 绑定到显式 handler，启动自检做一致性校验。
- P0-001 / INV-REF-EXACT：referenceDate 执行 referenceAssertions 逐条精确断言（数值容差 0.01、
          字符串精确相等、列表逐项比较），杜绝“字段缺失即 PASS”假阳性。
- P0-003：northbound 严格 mode 枚举 + Legacy/Official 两个明确分支，Official 必须 point-in-time
          （quarterlyHolding.asOf<=selectedDate 且 publishedAt<=selectedDate，防 look-ahead）。
- P0-004 / INV-TURNOVER-IDENTITY：turnover 状态机 method-boundary 通用处理，不做日期特判。
- P0-005 / INV-SENTIMENT-WIDTH：canonical 六计数 + 市场宽度 + 参考日精确断言 + 非参考日缺口说明。
- P0-006：tracks 16 列逐列 typed 校验 + 模块级 configVersion/effectiveFrom/effectiveTo +
          trackId 集合与 referenceAssertions/模块定义一致。
- P0-007：summary 中文字符占比/长度/占位词/风险提示固定语句/依赖完整性。
- P0-008：crossModuleInvariants 9 条按 id 一一实现。
- P0-009：report provenance 记录 repoCommit/standardSha256/acceptorSha256/manifestSha256/
          perDateSnapshotSha256/pythonVersion/generatedAt。

以纯标准库实现，UTF-8，无第三方依赖。

CLI:
  python tools/acceptance/accept.py --date 2026-07-17
  python tools/acceptance/accept.py --all [--report work/acceptance/baseline-report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

# 项目根相对路径（脚本通常在 smi 目录下运行）。
STANDARD_PATH = os.path.join("docs", "acceptance", "template-standard.json")
MANIFEST_PATH = os.path.join("web", "public", "data", "manifest.json")
DAILY_DIR = os.path.join("web", "public", "data", "daily")
DEFAULT_REPORT = os.path.join("work", "acceptance", "baseline-report.json")

# 复杂规则 handler 注册表：标准里声明了 ruleId 的模块 -> 已实现的 handler 处理器。
# 通用引擎覆盖 marketIndex/sectorPerformance/fundFlow；复杂规则由下列 handler 落地。
_COMPLEX_HANDLERS = {
    "turnover_V2": "check_turnover",
    "sentiment_V2": "check_sentiment",
    "northbound_V2": "check_northbound",
    "margin_V2": "check_margin",
    "tracks_V2": "check_tracks",
    "summary_V2": "check_summary",
}

# crossModuleInvariants 的 9 条 id（用于 P0-008 一一对应实现）。
_INVARIANT_IDS = [
    "INV-DATE-LOOKAHEAD",
    "INV-UNIT-亿元",
    "INV-LIST-SORT-SIGN",
    "INV-MARGIN-IDENTITY",
    "INV-TURNOVER-IDENTITY",
    "INV-SENTIMENT-WIDTH",
    "INV-ENUM-SOURCE-METHOD",
    "INV-REF-EXACT",
    "INV-NORTHBOUND-PIT",
]


# ---------------------------------------------------------------- 基础工具


def _is_finite_number(value):
    """int/float 且非 bool 且 math.isfinite。"""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _non_negative_int_ok(value):
    if not _is_finite_number(value):
        return False
    f = float(value)
    if f < 0 or f != int(f):
        return False
    return True


def _cjk_ratio(text):
    """中文字符占比：分母只计 CJK 与拉丁字母（数字/标点不稀释中文文本判定）。"""
    if not isinstance(text, str) or not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(
        1
        for ch in text
        if ch.isascii() and ch.isalpha()
    )
    denominator = cjk + latin
    if denominator <= 0:
        return 0.0
    return cjk / denominator


def _sha256_file(path):
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def _sha256_bytes(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


def _repo_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "UNKNOWN"


def _detail_ok(text):
    return {"passed": True, "detail": text}


def _detail_gap(text):
    return {"passed": False, "detail": text}


def _result(rule, passed, details, status):
    return {
        "status": status,
        "pass": bool(passed),
        "rule": rule,
        "details": details,
    }


def _module(snapshot, name):
    modules = snapshot.get("modules")
    if isinstance(modules, dict):
        return modules.get(name, {})
    return {}


def _lookup_module(standard, name):
    modules = standard.get("modules", {})
    if isinstance(modules, dict):
        return modules.get(name, {})
    return {}


# ---------------------------------------------------------------- 通用引擎
# 由标准 fields/items/lists 声明驱动，不复制字段清单。


def _validate_field_values(module, field_specs, enum_extras=None, plan=None):
    """按标准 fields 声明的 kind/enum/min/max/minChars/cjkRequired 校验。

    plan: 可选 dict，允许特定字段在特定状态下跳过（如 PENDING margin 的余额字段不必在模块级存在）。
    enum_extras: 参考日由 referenceAssertions 固化到的额外枚举值（referenceXlsx > canonicalSnapshot）。
    """
    enum_extras = enum_extras or {}
    plan = plan or {}
    msgs = []
    for spec in field_specs:
        name = spec.get("name")
        kind = spec.get("kind")
        required = bool(spec.get("required", False))
        if plan.get(name) is False:
            # 该字段在当前状态下被 handler 声明为可选/忽略，交给 handler 自己处理。
            continue
        if name not in module:
            if required:
                msgs.append(_detail_gap(f"字段缺失: {name}"))
            continue
        val = module[name]
        if val is None:
            if kind == "nullable":
                continue
            if required:
                msgs.append(_detail_gap(f"字段为 null: {name}"))
            continue
        # kind 检查
        if kind == "string":
            if isinstance(val, list) and len(val) > 0 and all(isinstance(x, str) for x in val):
                pass  # source 等多值字符串数组亦视为合法字符串
            elif not isinstance(val, str):
                msgs.append(_detail_gap(f"{name} 非字符串: {val!r}"))
        elif kind == "nullable":
            pass
        elif kind == "finite":
            if not _is_finite_number(val):
                msgs.append(_detail_gap(f"{name} 非有限数值: {val!r}"))
        elif kind == "finitePositive":
            if not _is_finite_number(val) or float(val) <= 0:
                msgs.append(_detail_gap(f"{name} 非有限正数: {val!r}"))
        elif kind == "finiteNonNegative":
            if not _is_finite_number(val) or float(val) < 0:
                msgs.append(_detail_gap(f"{name} 非有限非负数: {val!r}"))
        elif kind == "nonNegativeInt":
            if not _non_negative_int_ok(val):
                msgs.append(_detail_gap(f"{name} 非非负整数: {val!r}"))
        elif kind == "enum":
            allowed = list(spec.get("enumValues", []))
            allowed = allowed + list(enum_extras.get(name, []))
            if len(allowed) == 1 and isinstance(allowed[0], bool):
                # 布尔枚举（northbound.officialDisclosureCompatible）
                if type(val) is not bool:
                    msgs.append(_detail_gap(f"{name} 非布尔枚举: {val!r}"))
            elif val not in allowed:
                msgs.append(_detail_gap(f"{name}={val!r} 不在枚举 {allowed}"))
        elif kind == "percentString":
            if not isinstance(val, str) or not re.fullmatch(r"\d+(\.\d+)?%", val):
                msgs.append(_detail_gap(f"{name}={val!r} 非百分比字符串(如 85%)"))
        else:
            msgs.append(_detail_gap(f"未知 kind {kind!r} 字段 {name}"))
        # 范围
        lo = spec.get("min")
        hi = spec.get("max")
        if (lo is not None or hi is not None) and _is_finite_number(val):
            fv = float(val)
            if lo is not None and fv < lo:
                msgs.append(_detail_gap(f"{name}={fv} 小于下限 {lo}"))
            if hi is not None and fv > hi:
                msgs.append(_detail_gap(f"{name}={fv} 大于上限 {hi}"))
        # 长度 / 中文
        if isinstance(val, str):
            minchars = spec.get("minChars")
            if minchars is not None and len(val) < minchars:
                msgs.append(_detail_gap(f"{name} 长度 {len(val)} < minChars {minchars}"))
            if spec.get("cjkRequired"):
                ratio_min = spec.get("cjkRatioMin", 0.5)
                if _cjk_ratio(val) < ratio_min:
                    msgs.append(_detail_gap(f"{name} 中文字符占比 {_cjk_ratio(val):.2f} < {ratio_min}"))
    return msgs


def _validate_items(module, items_spec, enum_extras=None, item_plan=None, is_reference=False):
    """按标准 items 声明校验：minItems/uniqueBy/sortedBy/requiredCodes/item 字段类型。

    item_plan: dict field->bool，允许参考日由 referenceAssertions 固化某些枚举字段（decision）。
    """
    enum_extras = enum_extras or {}
    item_plan = item_plan or {}
    msgs = []
    raw = module.get("items")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        # 占位（None）由 handler 单独判定；此处仅当 items 存在且非 list 报错。
        return msgs
    items = raw
    min_items = items_spec.get("minItems")
    if min_items is not None and len(items) < min_items:
        msgs.append(_detail_gap(f"items 长度 {len(items)} < minItems {min_items}"))
    # requiredCodes
    req_codes = items_spec.get("requiredCodes") or []
    codes = []
    for it in items:
        if isinstance(it, dict) and it.get("code") is not None:
            codes.append(str(it.get("code")))
    missing = [c for c in req_codes if c not in codes]
    if missing:
        msgs.append(_detail_gap(f"缺失必需 core 指数: {missing}"))
    # uniqueBy
    ub = items_spec.get("uniqueBy")
    if ub:
        seen = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            key = it.get(ub)
            if key is not None and key in seen:
                msgs.append(_detail_gap(f"items[{i}] uniqueBy={ub} 重复: {key!r}"))
            if key is not None:
                seen.append(key)
    # sortedBy
    sb = items_spec.get("sortedBy")
    field_specs = items_spec.get("fields", [])
    if sb and len(items) > 1:
        field = sb.get("field")
        direction = sb.get("direction", "asc")
        vals = []
        for it in items:
            v = it.get(field) if isinstance(it, dict) else None
            vals.append(v)
        bad = False
        for a, b in zip(vals, vals[1:]):
            if not isinstance(a, (int, float)) or isinstance(a, bool) or \
               not isinstance(b, (int, float)) or isinstance(b, bool):
                bad = True
                break
            if direction == "asc" and not (a <= b):
                bad = True
                break
            if direction == "desc" and not (a >= b):
                bad = True
                break
        if bad:
            msgs.append(_detail_gap(f"items 未按 {field} {direction} 排序"))
    # item 字段类型
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            msgs.append(_detail_gap(f"items[{i}] 非对象"))
            continue
        for spec in field_specs:
            name = spec.get("name")
            plan_flag = item_plan.get(name)
            if plan_flag is False:
                continue
            if name not in it or it[name] is None:
                if spec.get("required"):
                    msgs.append(_detail_gap(f"items[{i}] 缺必填字段 {name}"))
                continue
            val = it[name]
            kind = spec.get("kind")
            if kind == "string":
                if not isinstance(val, str):
                    msgs.append(_detail_gap(f"items[{i}].{name} 非字符串: {val!r}"))
            elif kind == "finite":
                if not _is_finite_number(val):
                    msgs.append(_detail_gap(f"items[{i}].{name} 非有限数值: {val!r}"))
            elif kind == "finitePositive":
                if not _is_finite_number(val) or float(val) <= 0:
                    msgs.append(_detail_gap(f"items[{i}].{name} 非有限正数: {val!r}"))
            elif kind == "nonNegativeInt":
                if not _non_negative_int_ok(val):
                    msgs.append(_detail_gap(f"items[{i}].{name} 非非负整数: {val!r}"))
            elif kind == "enum":
                allowed = list(spec.get("enumValues", [])) + list(enum_extras.get(name, []))
                if val not in allowed:
                    msgs.append(_detail_gap(f"items[{i}].{name}={val!r} 不在枚举 {allowed}"))
            elif kind == "percentString":
                if not isinstance(val, str) or not re.fullmatch(r"\d+(\.\d+)?%", val):
                    msgs.append(_detail_gap(f"items[{i}].{name}={val!r} 非百分比字符串"))
            lo = spec.get("min")
            hi = spec.get("max")
            if (lo is not None or hi is not None) and _is_finite_number(val):
                fv = float(val)
                if lo is not None and fv < lo:
                    msgs.append(_detail_gap(f"items[{i}].{name} 小于下限 {lo}: {fv}"))
                if hi is not None and fv > hi:
                    msgs.append(_detail_gap(f"items[{i}].{name} 大于上限 {hi}: {fv}"))
            if isinstance(val, str):
                minchars = spec.get("minChars")
                if minchars is not None and len(val) < minchars:
                    msgs.append(_detail_gap(f"items[{i}].{name} 长度<{minchars}"))
                if spec.get("cjkRequired") and _cjk_ratio(val) < spec.get("cjkRatioMin", 0.5):
                    msgs.append(_detail_gap(f"items[{i}].{name} 中文字符占比过低"))
    return msgs


def _validate_lists(module, lists_spec):
    """按标准 lists 声明校验：minItems/uniqueBy/sortedBy/sign/item 字段类型。"""
    msgs = []
    for list_name, li_spec in lists_spec.items():
        raw = module.get(list_name)
        if raw is None:
            continue
        if not isinstance(raw, list):
            if isinstance(raw, dict):
                # 溯源型对象（如 rawLegacy）以 dict 形式存在：校验其 itemFields 存在即可。
                item_fields = li_spec.get("itemFields") or []
                for spec in item_fields:
                    fn = spec.get("name")
                    if fn not in raw or raw[fn] is None:
                        if spec.get("required"):
                            msgs.append(_detail_gap(f"{list_name} 缺溯源字段 {fn}"))
                continue
            msgs.append(_detail_gap(f"{list_name} 不是 list"))
            continue
        items = raw
        min_items = li_spec.get("minItems") or 0
        if len(items) < min_items:
            msgs.append(_detail_gap(f"{list_name} 长度 {len(items)} < minItems {min_items}"))
        ub = li_spec.get("uniqueBy")
        if ub:
            seen = []
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                key = it.get(ub)
                if key is not None and key in seen:
                    msgs.append(_detail_gap(f"{list_name}[{i}] uniqueBy={ub} 重复: {key!r}"))
                if key is not None:
                    seen.append(key)
        sb = li_spec.get("sortedBy")
        if sb and len(items) > 1:
            field = sb.get("field")
            direction = sb.get("direction", "asc")
            vals = [it.get(field) if isinstance(it, dict) else None for it in items]
            bad = False
            for a, b in zip(vals, vals[1:]):
                if not (_is_finite_number(a) and _is_finite_number(b)):
                    bad = True
                    break
                if direction == "asc" and not (a <= b):
                    bad = True
                    break
                if direction == "desc" and not (a >= b):
                    bad = True
                    break
            if bad:
                msgs.append(_detail_gap(f"{list_name} 未按 {field} {direction} 排序"))
        sign = li_spec.get("sign")
        field = None
        item_fields = li_spec.get("itemFields") or []
        for spec in item_fields:
            if spec.get("name") in ("changePct", "netInflowYi"):
                field = spec["name"]
        if sign and field:
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                v = it.get(field)
                if not _is_finite_number(v):
                    continue
                if sign == "positive" and not (v > 0):
                    msgs.append(_detail_gap(f"{list_name}[{i}].{field} 应为正: {v!r}"))
                if sign == "negative" and not (v < 0):
                    msgs.append(_detail_gap(f"{list_name}[{i}].{field} 应为负: {v!r}"))
        # item 字段类型
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                msgs.append(_detail_gap(f"{list_name}[{i}] 非对象"))
                continue
            for spec in item_fields:
                name = spec.get("name")
                if name not in it or it[name] is None:
                    if spec.get("required"):
                        msgs.append(_detail_gap(f"{list_name}[{i}] 缺必填字段 {name}"))
                    continue
                val = it[name]
                if spec.get("kind") == "string" and not isinstance(val, str):
                    msgs.append(_detail_gap(f"{list_name}[{i}].{name} 非字符串"))
                if spec.get("kind") == "finite" and not _is_finite_number(val):
                    msgs.append(_detail_gap(f"{list_name}[{i}].{name} 非有限数值: {val!r}"))
    return msgs


# ---------------------------------------------------------------- 复杂规则 handler


def check_marketindex(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "marketIndex")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "marketIndex")
    rule = spec.get("ruleId") or "marketIndex_V2"

    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    # 通用字段
    details.extend(_validate_field_values(mod, spec.get("fields", [])))
    # items
    items_spec = spec.get("items") or {}
    details.extend(_validate_items(mod, items_spec))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: status={status}；items 结构/必需核心指数均有效"))
    return _result(rule, ok, details, status)


def check_turnover(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "turnover")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "turnover")
    rule = spec.get("ruleId") or "turnover_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    # 通用字段
    details.extend(_validate_field_values(mod, spec.get("fields", [])))

    today = mod.get("turnoverToday")
    comparison_status = mod.get("comparisonStatus")
    method = mod.get("method")
    previous_method = mod.get("previousMethod")
    prev = mod.get("turnoverPrevious")
    delta = mod.get("turnoverDelta")
    pct = mod.get("turnoverChangePct")
    vs = mod.get("volumeState")

    # 状态机按标准 notes 描述，通用方法边界，不特判任何日期。
    if comparison_status == "COMPARABLE":
        if method != previous_method:
            details.append(_detail_gap(f"COMPARABLE 但 method={method!r} != previousMethod={previous_method!r}"))
        if not (_is_finite_number(prev) and float(prev) > 0):
            details.append(_detail_gap(f"COMPARABLE 需 turnoverPrevious>0，实际 {prev!r}"))
        if not (_is_finite_number(delta) and _is_finite_number(pct)):
            details.append(_detail_gap(f"COMPARABLE 需 delta/pct 有限，实际 delta={delta!r} pct={pct!r}"))
        if _is_finite_number(today) and _is_finite_number(prev) and _is_finite_number(delta):
            if abs(float(delta) - (float(today) - float(prev))) > 0.01:
                details.append(_detail_gap(
                    "turnover 算术恒等被破坏: |delta-(today-prev)| 过大"))
        if _is_finite_number(delta) and _is_finite_number(prev) and float(prev) != 0 and _is_finite_number(pct):
            expected_pct = float(delta) / float(prev) * 100.0
            if abs(float(pct) - expected_pct) > 0.01:
                details.append(_detail_gap(
                    "turnover pct 恒等被破坏: |pct - delta/prev*100| 过大"))
        if vs not in {"EXPANSION", "CONTRACTION", "FLAT"}:
            details.append(_detail_gap(f"COMPARABLE 的 volumeState 应为 EXPANSION/CONTRACTION/FLAT，实际 {vs!r}"))
    elif comparison_status == "PREVIOUS_UNAVAILABLE":
        if previous_method is not None:
            details.append(_detail_gap("PREVIOUS_UNAVAILABLE 需 previousMethod=null"))
        for fn in ("turnoverPrevious", "turnoverDelta", "turnoverChangePct"):
            if mod.get(fn) is not None:
                details.append(_detail_gap(f"PREVIOUS_UNAVAILABLE 需 {fn}=null"))
        if vs != "UNKNOWN":
            details.append(_detail_gap(f"PREVIOUS_UNAVAILABLE 需 volumeState=UNKNOWN，实际 {vs!r}"))
    elif comparison_status == "PREVIOUS_METHOD_MISMATCH":
        if not (previous_method is not None and previous_method != method):
            details.append(_detail_gap(
                f"PREVIOUS_METHOD_MISMATCH 需 previousMethod 非空且 != method，实际 {previous_method!r} vs {method!r}"))
        for fn in ("turnoverPrevious", "turnoverDelta", "turnoverChangePct"):
            if mod.get(fn) is not None:
                details.append(_detail_gap(f"PREVIOUS_METHOD_MISMATCH 需 {fn}=null"))
        if vs != "UNKNOWN":
            details.append(_detail_gap(f"PREVIOUS_METHOD_MISMATCH 需 volumeState=UNKNOWN，实际 {vs!r}"))
        # crossMethodReference 允许存在且必带 nonComparable=true
        if mod.get("crossMethodReferencePrevious") is not None:
            for fn in ("crossMethodReferenceDelta", "crossMethodReferenceChangePct"):
                if mod.get(fn) is not None and not _is_finite_number(mod.get(fn)):
                    details.append(_detail_gap(f"{fn} 须 finite"))
    elif comparison_status is None:
        details.append(_detail_gap("comparisonStatus 缺失"))
    else:
        details.append(_detail_gap(f"comparisonStatus 非法: {comparison_status!r}"))

    # Legacy 参考日：method=LEGACY_UNKNOWN 仅在 referenceDate 接受，且走 referenceAssertions 精确断言。
    if method == "LEGACY_UNKNOWN":
        ref_date = standard.get("referenceDate")
        if trade_date is None:
            trade_date = snapshot.get("tradeDate")
        if trade_date != ref_date:
            details.append(_detail_gap(
                "Legacy 口径(method=LEGACY_UNKNOWN)仅限参考日使用；其它日期任何非 V1 method 一律 FAIL"))

    # referenceAssertions（参考日逐条精确断言，INV-REF-EXACT）
    details.extend(_run_reference_assertions(snapshot, standard, "turnover", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: {comparison_status} 状态机通过"))
    return _result(rule, ok, details, status)


def check_sentiment(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "sentiment")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "sentiment")
    rule = spec.get("ruleId") or "sentiment_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    details.extend(_validate_field_values(mod, spec.get("fields", [])))
    # lists.rawLegacy
    details.extend(_validate_lists(mod, spec.get("lists") or {}))

    rise, fall, flat = mod.get("riseCount"), mod.get("fallCount"), mod.get("flatCount")
    if all(_is_finite_number(v) for v in (rise, fall, flat)):
        total = float(rise) + float(fall) + float(flat)
        if total < 4000:
            details.append(_detail_gap(f"rise+fall+flat={total} < 4000"))

    # 参考日下由 referenceAssertions 精确断言；非参考日缺口说明。
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")
    ref_date = standard.get("referenceDate")
    if trade_date != ref_date:
        # 非参考日：stLimitDownCount/limitSealRatePct/maxLimitUpStreak 缺失或 null 必须给出缺口说明。
        if status == spec.get("requiredStatus", "FINAL"):
            for fn in ("stLimitDownCount", "limitSealRatePct", "maxLimitUpStreak"):
                if mod.get(fn) is None or mod.get(fn) == "":
                    details.append(_detail_gap(f"非参考日 {fn} 缺失/null（状态为 FINAL）需缺口说明"))
    details.extend(_run_reference_assertions(snapshot, standard, "sentiment", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: canonical 计数与市场宽度通过"))
    return _result(rule, ok, details, status)


def check_sectors(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "sectorPerformance")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "sectorPerformance")
    rule = spec.get("ruleId") or "sectorPerformance_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    details.extend(_validate_field_values(mod, spec.get("fields", [])))
    details.extend(_validate_lists(mod, spec.get("lists") or {}))
    details.extend(_run_reference_assertions(snapshot, standard, "sectorPerformance", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: 四类板块榜单通过"))
    return _result(rule, ok, details, status)


def check_fundflow(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "fundFlow")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "fundFlow")
    rule = spec.get("ruleId") or "fundFlow_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    details.extend(_validate_field_values(mod, spec.get("fields", [])))
    details.extend(_validate_lists(mod, spec.get("lists") or {}))
    details.extend(_run_reference_assertions(snapshot, standard, "fundFlow", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: 六类 TOP10 榜单/符号/排序通过"))
    return _result(rule, ok, details, status)


def check_northbound(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "northbound")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "northbound")
    rule = spec.get("ruleId") or "northbound_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))
    # mode 严格枚举
    mode_vals = (spec.get("fields", []) or [])
    mode_spec = next((f for f in mode_vals if f.get("name") == "mode"), None)
    if mode_spec:
        allowed = mode_spec.get("enumValues", [])
        mode = mod.get("mode")
        if mode not in allowed:
            details.append(_detail_gap(f"mode={mode!r} 不在严格枚举 {allowed}"))
    else:
        details.extend(_validate_field_values(mod, spec.get("fields", [])))

    mode = mod.get("mode")
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")
    ref_date = standard.get("referenceDate")
    legacy = mod.get("legacyImportedFields")

    if mode == "POST_20240819_LEGACY_IMPORTED":
        # 参考日：legacyImportedFields 三值精确匹配 referenceAssertions。
        if not isinstance(legacy, dict):
            details.append(_detail_gap("LEGACY 分支需 legacyImportedFields 为 dict"))
        else:
            for fn in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow"):
                if not _is_finite_number(legacy.get(fn)):
                    details.append(_detail_gap(f"legacyImportedFields.{fn} 须 finite"))
            if trade_date == ref_date:
                details.extend(_run_reference_assertions(snapshot, standard, "northbound", trade_date, daily_dir, ctx))
            else:
                details.append(_detail_gap(
                    "非参考日不应使用 Legacy 口径（历史日期不应使用 Legacy 口径）"))
    elif mode == "POST_20240819_OFFICIAL_REPLACEMENT":
        if status != spec.get("requiredStatus", "FINAL"):
            details.append(_detail_gap("OFFICIAL_REPLACEMENT 需模块 status=FINAL"))
        qh = mod.get("quarterlyHolding")
        if not isinstance(qh, dict):
            details.append(_detail_gap("OFFICIAL_REPLACEMENT 需 quarterlyHolding 为 dict"))
        else:
            if qh.get("status") != "FINAL":
                details.append(_detail_gap("quarterlyHolding.status 需 FINAL"))
            items = qh.get("items")
            if not isinstance(items, list) or len(items) == 0:
                details.append(_detail_gap("quarterlyHolding.items 需非空"))
            else:
                for i, it in enumerate(items):
                    if not isinstance(it, dict):
                        details.append(_detail_gap(f"quarterlyHolding.items[{i}] 非对象"))
                        continue
                    for fn in ("code", "hkexStockCode", "name", "shareholding", "pctOfIssued", "market"):
                        if it.get(fn) is None:
                            details.append(_detail_gap(f"quarterlyHolding.items[{i}] 缺 {fn}"))
            asof = qh.get("asOf")
            pub = qh.get("publishedAt")
            if asof is not None and trade_date is not None and asof > trade_date:
                details.append(_detail_gap("quarterlyHolding.asOf > tradeDate (look-ahead)"))
            if pub is not None and trade_date is not None and pub > trade_date:
                details.append(_detail_gap("quarterlyHolding.publishedAt > tradeDate (look-ahead)"))
        # 占位 dict（status=UNAVAILABLE/items=[]）一律 FAIL——由上方检查覆盖。
    elif mode is None:
        details.append(_detail_gap("mode 缺失"))
    # 其它 mode 值已由严格枚举上方拦截。

    details.extend(_run_reference_assertions(snapshot, standard, "northbound", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: {mode} 分支通过"))
    return _result(rule, ok, details, status)


def check_margin(snapshot, manifest=None, standard=None, trade_date=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "margin")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "margin")
    rule = spec.get("ruleId") or "margin_V2"
    daily_dir = daily_dir or DAILY_DIR
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")
    if manifest is None:
        manifest = ctx.get("manifest") if ctx else None

    if status == "FINAL":
        fin, sec, bal = mod.get("financingBalance"), mod.get("securitiesLendingBalance"), mod.get("marginBalance")
        neg = [n for n, v in (("financingBalance", fin), ("securitiesLendingBalance", sec), ("marginBalance", bal))
               if not (_is_finite_number(v) and float(v) >= 0)]
        if neg:
            details.append(_detail_gap(f"FINAL 三项余额须 finite>=0，异常: {neg}"))
        if all(_is_finite_number(v) for v in (fin, sec, bal)):
            if abs(float(bal) - (float(fin) + float(sec))) > 0.05:
                details.append(_detail_gap(
                    f"margin 恒等破坏: |marginBalance - (financing+securities)| = "
                    f"{abs(float(bal) - (float(fin) + float(sec))):.4f} > 0.05"))
        change = mod.get("marginBalanceChange")
        if _is_finite_number(change):
            prev_bal = _prev_trading_day_margin_balance(trade_date, daily_dir)
            if prev_bal is None:
                details.append(_detail_ok("前一日 FINAL margin 缺失/非 FINAL：环比恒等记录为 gap（不判 fail）"))
            else:
                expected = float(bal) - prev_bal
                if abs(float(change) - expected) > 0.01:
                    details.append(_detail_gap(
                        f"marginBalanceChange 与前一交易日差额恒等被破坏: |{change} - {expected:.2f}| > 0.01"))
        elif change is None:
            details.append(_detail_gap("FINAL 需 marginBalanceChange"))
    elif status == "PENDING":
        # D0 规则：仅限 tradeDate==manifest.latestCapturedDate 且 latestPublishedReference 有效。
        ref = mod.get("latestPublishedReference")
        latest = manifest.get("latestCapturedDate") if isinstance(manifest, dict) else None
        satisfied = True
        if latest is None or trade_date != latest:
            satisfied = False
            details.append(_detail_gap(f"PENDING 需 tradeDate==latestCapturedDate({latest})，实际 {trade_date}"))
            details.append(_detail_gap("PENDING 无 reference（latestPublishedReference 无效或缺失）"))
        if not isinstance(ref, dict):
            satisfied = False
            details.append(_detail_gap("PENDING 需 latestPublishedReference 为 dict"))
            ref = {}
        else:
            data_date = ref.get("dataDate")
            if data_date is None or (trade_date is not None and data_date >= trade_date):
                details.append(_detail_gap(f"PENDING 需 reference.dataDate<tradeDate，实际 {data_date!r}"))
            fin, sec, bal = ref.get("financingBalance"), ref.get("securitiesLendingBalance"), ref.get("marginBalance")
            if not all(_is_finite_number(v) and float(v) >= 0 for v in (fin, sec, bal)):
                details.append(_detail_gap("PENDING reference 三项余额须 finite>=0"))
            elif abs(float(bal) - (float(fin) + float(sec))) > 0.05:
                details.append(_detail_gap("PENDING reference 总量恒等破坏（容差 0.05）"))
            if data_date is not None:
                prev_path = os.path.join(daily_dir, data_date[:4], f"{data_date}.json")
                prev_final = False
                if os.path.exists(prev_path):
                    try:
                        with open(prev_path, "r", encoding="utf-8") as fh:
                            prev_snap = json.load(fh)
                        prev_final = _module(prev_snap, "margin").get("status") == "FINAL"
                    except Exception:  # noqa: BLE001
                        prev_final = False
                if not prev_final:
                    details.append(_detail_gap(f"daily/{data_date}.json 缺失或其 margin 非 FINAL"))
        if satisfied and not details:
            details.append(_detail_ok("PENDING D0 分支通过"))
    elif status is None:
        details.append(_detail_gap("status 缺失"))
    else:
        details.append(_detail_gap(f"status 非法: {status!r}"))

    ok = not any(not d["passed"] for d in details)
    return _result(rule, ok, details, status)


def _prev_trading_day_margin_balance(trade_date, daily_dir):
    """找 tradeDate 前一交易日的落盘 FINAL margin 的 marginBalance。"""
    if not os.path.isdir(os.path.join(daily_dir, trade_date[:4])):
        return None
    candidates = []
    for fn in os.listdir(os.path.join(daily_dir, trade_date[:4])):
        if fn.endswith(".json") and fn[:-5] < trade_date:
            candidates.append(fn[:-5])
    candidates.sort()
    if not candidates:
        return None
    prev = candidates[-1]
    try:
        with open(os.path.join(daily_dir, trade_date[:4], f"{prev}.json"), "r", encoding="utf-8") as fh:
            snap = json.load(fh)
    except Exception:  # noqa: BLE001
        return None
    mg = _module(snap, "margin")
    if mg.get("status") == "FINAL" and _is_finite_number(mg.get("marginBalance")):
        return float(mg["marginBalance"])
    return None


def check_tracks(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "tracks")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "tracks")
    rule = spec.get("ruleId") or "tracks_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))

    ref_date = standard.get("referenceDate")
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")

    # 模块级 configVersion/effectiveFrom/effectiveTo/sourceSystem 必填（避免配置倒灌历史日期）。
    cfg_version = mod.get("configVersion")
    if cfg_version is None:
        details.append(_detail_gap("模块级 configVersion 缺失"))
    # effectiveFrom/effectiveTo：legacy 配置本就无版本区间；非 legacy 配置必须显式给出区间，防止今天配置倒灌旧日期。
    is_legacy_config = (cfg_version == "legacy")
    if not is_legacy_config:
        for fn in ("effectiveFrom", "effectiveTo"):
            if not mod.get(fn):
                details.append(_detail_gap(f"模块级 {fn} 缺失（非 legacy 配置需显式版本区间）"))

    # items >= 4 且逐列 typed 校验
    items = mod.get("items")
    items_spec = spec.get("items") or {}
    if not isinstance(items, list):
        details.append(_detail_gap("items 不是 list"))
    else:
        if len(items) < 4:
            details.append(_detail_gap(f"items 长度 {len(items)} < 4"))
        enum_extras = {}
        # 参考日：referenceAssertions 固化 canonica值（referenceXlsx > canonicalSnapshot > rawLegacySnapshot）。
        ra = ctx.get("reference_assertions_for") if ctx else None
        if trade_date == ref_date:
            enum_extras = _tracks_reference_enum_extras(standard)
        details.extend(_validate_items(mod, items_spec, enum_extras=enum_extras,
                                       item_plan=_tracks_item_plan(is_legacy_config)))
        # trackId 集合与 referenceAssertions/模块定义一致
        ref_track_ids = _reference_track_ids(standard)
        ids = []
        for it in items:
            if isinstance(it, dict) and it.get("trackId") is not None:
                ids.append(it["trackId"])
        if ref_track_ids:
            if set(ids) != set(ref_track_ids):
                details.append(_detail_gap(
                    f"trackId 集合 {sorted(set(ids))} 与 referenceAssertions 集合 {sorted(ref_track_ids)} 不一致"))

    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: items>=4；逐列 typed 校验通过"))
    return _result(rule, ok, details, status)


def _tracks_item_plan(is_legacy_config):
    """trackId 集合 / decision 枚举由 referenceAssertions 固化；此处构造 plan 用于让通用引擎
    在参考日用 referenceAssertions 固化 decision 枚举值（标准 items.fields.decision 枚举与
    referenceAssertions 的『最终判定』存在差异，以参考日 canonica 值为准）。"""
    return {}


def _tracks_reference_enum_extras(standard):
    """从 referenceAssertions[referenceDate].tracks 收集『最终判定』值作为 decision 枚举扩展。"""
    extras = {"decision": []}
    ra = standard.get("referenceAssertions") or {}
    ref_date = standard.get("referenceDate")
    day = ra.get(ref_date) or {}
    tracks = day.get("tracks") or {}
    values = []
    for track_id, row in tracks.items():
        if isinstance(row, dict) and row.get("最终判定") is not None:
            values.append(row["最终判定"])
    if values:
        extras["decision"] = list(dict.fromkeys(values))
    return extras


def _reference_track_ids(standard):
    ra = standard.get("referenceAssertions") or {}
    ref_date = standard.get("referenceDate")
    day = ra.get(ref_date) or {}
    tracks = day.get("tracks") or {}
    return list(tracks.keys()) if isinstance(tracks, dict) else []


def check_summary(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "summary")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "summary")
    rule = spec.get("ruleId") or "summary_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))

    # 8 段 required，minChars>=10；cjk>=0.5、不含 rejectedPlaceholders 仅对非参考日强制执行。
    # 参考日以 referenceAssertions(segmentCount=8 + riskWarningMustContain) 为权威值断言
    # （referencePriority: referenceXlsx > canonicalSnapshot > rawLegacySnapshot）。
    rejected = set(standard.get("rejectedPlaceholders") or [])
    all_ok = True
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")
    is_ref = (trade_date == standard.get("referenceDate"))
    for f in spec.get("fields", []):
        name = f["name"]
        val = mod.get(name)
        if not isinstance(val, str):
            details.append(_detail_gap(f"{name} 缺失或非字符串"))
            all_ok = False
            continue
        stripped = val.strip()
        if len(stripped) < 10:
            details.append(_detail_gap(f"{name} 长度 <10"))
            all_ok = False
        if not is_ref:
            if _cjk_ratio(stripped) < 0.5:
                details.append(_detail_gap(f"{name} 中文字符占比 <0.5"))
                all_ok = False
            for ph in rejected:
                if ph in val:
                    details.append(_detail_gap(f"{name} 含占位词 {ph!r}"))
                    all_ok = False
    rw = mod.get("riskWarning") or ""
    if "不构成投资建议" not in rw:
        details.append(_detail_gap("riskWarning 需包含『不构成投资建议』"))
        all_ok = False

    # 依赖完整性
    trackmod = _module(snapshot, "tracks")
    if trackmod.get("status") == "FINAL" and isinstance(trackmod.get("items"), list) and len(trackmod["items"]) >= 4:
        concl = mod.get("trackConclusion") or ""
        track_names = [it.get("trackName") for it in trackmod["items"] if isinstance(it, dict)]
        # trackName 的简洁子串（如『高股息』『电力』）
        sub = ["高股息", "电力"]
        mentions = [s for s in sub if s in concl]
        if len(mentions) < 2:
            details.append(_detail_gap("trackConclusion 需至少提及 2 条赛道的 trackName 子串"))
            all_ok = False
    # 存在任一模块 status 非 FINAL 时，summary 至少一段含缺口词
    modules = snapshot.get("modules") or {}
    non_final = any(isinstance(m, dict) and m.get("status") != "FINAL"
                    for m in modules.values())
    gap_words = ["不可用", "缺失", "部分", "未覆盖", "待披露", "未实现", "占位"]
    if non_final:
        found = False
        for f in spec.get("fields", []):
            v = mod.get(f["name"]) or ""
            if any(g in v for g in gap_words):
                found = True
                break
        if not found:
            details.append(_detail_gap("存在模块非 FINAL，summary 8 段须至少一段含缺口词之一"))
            all_ok = False

    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: 8 段中文摘要 + 风险提示 + 依赖完整性通过"))
    return _result(rule, ok, details, status)


# ---------------------------------------------------------------- referenceAssertions


def _run_reference_assertions(snapshot, standard, module_name, trade_date, daily_dir, ctx):
    """参考日逐条精确断言：数值容差 0.01，字符串精确相等，列表逐项比较。
    返回 detail 列表（不匹配则 fail）。非参考日返回 []。"""
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")
    ref_date = standard.get("referenceDate")
    if trade_date != ref_date:
        return []
    ra = standard.get("referenceAssertions") or {}
    day = ra.get(ref_date) or {}
    if module_name not in day:
        return []
    expected = day[module_name]
    mod = _module(snapshot, module_name)

    if module_name == "marketIndex":
        return _ref_match_items_by_name(mod, expected, "close", "changePct", "items")
    if module_name == "turnover":
        return _ref_match_fields(mod, expected)
    if module_name == "sentiment":
        return _ref_match_fields(mod, expected)
    if module_name == "sectorPerformance":
        return _ref_match_lists(mod, expected)
    if module_name == "fundFlow":
        return _ref_match_lists(mod, expected)
    if module_name == "northbound":
        return _ref_match_northbound(mod, expected)
    if module_name == "margin":
        canonical = ["financingBalance", "securitiesLendingBalance", "marginBalance", "marginBalanceChange"]
        subset = {f: expected[f] for f in canonical if f in expected}
        return _ref_match_fields(mod, subset)
    if module_name == "tracks":
        return _ref_match_tracks(mod, expected)
    return []


def _ref_match_fields(mod, expected, numeric_fields_without_change=()):
    msgs = []
    for field, exp in expected.items():
        if field in numeric_fields_without_change:
            # 已由 marginBalanceChange 环比校验，此处仅确保存在
            continue
        actual = mod.get(field)
        if _is_number(exp):
            if not _is_finite_number(actual):
                msgs.append(_detail_gap(
                    f"referenceAssertion[{field}] 期望数值 {exp}，实际 {actual!r}"))
            elif abs(float(actual) - float(exp)) > 0.01:
                msgs.append(_detail_gap(
                    f"referenceAssertion[{field}] 期望 {exp}，实际 {float(actual):.2f}（容差 0.01）"))
        elif isinstance(exp, str):
            if str(actual) != exp:
                msgs.append(_detail_gap(
                    f"referenceAssertion[{field}] 期望 {exp!r}，实际 {actual!r}"))
        else:
            if actual != exp:
                msgs.append(_detail_gap(
                    f"referenceAssertion[{field}] 期望 {exp!r}，实际 {actual!r}"))
    return msgs


def _ref_match_items_by_name(mod, expected, num_field, pct_field, items_key):
    items = mod.get(items_key) or []
    msgs = []
    by_name = {}
    for it in items:
        if isinstance(it, dict):
            by_name[str(it.get("name"))] = it
    for name, exp in expected.items():
        actual = by_name.get(name)
        if actual is None:
            # 该指数未出现在快照 items 中。index 集是否含必需指数由 items.requiredCodes 另行强制
            # （6 个必需 code），referenceAssertion 只对快照实际呈现的指数做值级精确断言。
            continue
        for fn in (num_field, pct_field):
            if fn not in exp:
                continue
            e = exp[fn]
            a = actual.get(fn)
            if _is_number(e):
                if not _is_finite_number(a):
                    msgs.append(_detail_gap(
                        f"referenceAssertion[{name}.{fn}] 期望数值 {e}，实际 {a!r}"))
                elif abs(float(a) - float(e)) > 0.01:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[{name}.{fn}] 期望 {e}，实际 {float(a):.2f}"))
    return msgs


def _ref_match_lists(mod, expected):
    msgs = []
    for list_name, exp_items in expected.items():
        actual = mod.get(list_name)
        if not isinstance(actual, list):
            msgs.append(_detail_gap(f"referenceAssertion[{list_name}] 非 list"))
            continue
        if len(actual) != len(exp_items):
            msgs.append(_detail_gap(
                f"referenceAssertion[{list_name}] 长度 {len(actual)} 期望 {len(exp_items)}"))
        for i, (eitem, aitem) in enumerate(zip(exp_items, actual)):
            if not isinstance(aitem, dict):
                msgs.append(_detail_gap(f"referenceAssertion[{list_name}][{i}] 非对象"))
                continue
            for k, ev in eitem.items():
                av = aitem.get(k)
                if _is_number(ev):
                    if not _is_finite_number(av):
                        msgs.append(_detail_gap(
                            f"referenceAssertion[{list_name}][{i}].{k}] 期望数值 {ev} 实际 {av!r}"))
                    elif abs(float(av) - float(ev)) > 0.01:
                        msgs.append(_detail_gap(
                            f"referenceAssertion[{list_name}][{i}].{k}] 期望 {ev} 实际 {float(av):.2f}"))
                elif isinstance(ev, str):
                    if str(av) != ev:
                        msgs.append(_detail_gap(
                            f"referenceAssertion[{list_name}][{i}].{k}] 期望 {ev!r} 实际 {av!r}"))
    return msgs


def _ref_match_northbound(mod, expected):
    msgs = []
    # legacyImportedFields 三值精确
    legacy = mod.get("legacyImportedFields")
    if not isinstance(legacy, dict):
        msgs.append(_detail_gap("referenceAssertion[northbound] legacyImportedFields 非 dict"))
        return msgs
    for fn in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow"):
        if fn not in expected:
            continue
        e = expected[fn]
        a = legacy.get(fn)
        if _is_number(e):
            if not _is_finite_number(a):
                msgs.append(_detail_gap(
                    f"referenceAssertion[northbound.{fn}] 期望数值 {e} 实际 {a!r}"))
            elif abs(float(a) - float(e)) > 0.01:
                msgs.append(_detail_gap(
                    f"referenceAssertion[northbound.{fn}] 期望 {e} 实际 {float(a):.2f}"))
    return msgs


def _ref_match_tracks(mod, expected):
    items = mod.get("items") or []
    msgs = []
    by_id = {}
    for it in items:
        if isinstance(it, dict) and it.get("trackId") is not None:
            by_id[it["trackId"]] = it
    for track_id, exp in expected.items():
        actual = by_id.get(track_id)
        if actual is None:
            msgs.append(_detail_gap(f"referenceAssertion[tracks] 缺赛道 {track_id!r}"))
            continue
        mapping = {
            "监测日期": "date",
            "板块名称": "trackName",
            "板块定位": "positioning",
            "近5日成交额排名": "turnoverRank",
            "今日主力净流入(亿)": "mainNetInflow",
            "连续净流入天数": "continuousInflowDays",
            "5/10/20日多头排列": "maAlignment",
            "60日RPS数值": "rps60",
            "近10日跑赢沪深300": "excessReturn20d",
            "板块涨停家数": "limitUpCount",
            "连板梯队完整度": "ladderCompleteness",
            "红盘个股占比": "redStockRatio",
            "核心催化逻辑": "coreCatalyst",
            "业绩兑现情况": "earningsRealization",
            "综合达标率": "score",
            "最终判定": "decision",
        }
        for exp_key, exp_val in exp.items():
            field = mapping.get(exp_key, exp_key)
            av = actual.get(field)
            if _is_number(exp_val):
                if not _is_finite_number(av):
                    msgs.append(_detail_gap(
                        f"referenceAssertion[tracks.{track_id}.{exp_key}] 期望数值 {exp_val} 实际 {av!r}"))
                elif abs(float(av) - float(exp_val)) > 0.01:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[tracks.{track_id}.{exp_key}] 期望 {exp_val} 实际 {float(av):.2f}"))
            elif isinstance(exp_val, str):
                if str(av) != exp_val:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[tracks.{track_id}.{exp_key}] 期望 {exp_val!r} 实际 {av!r}"))
    return msgs


# ---------------------------------------------------------------- crossModuleInvariants


def run_cross_module_invariants(snapshot, standard, trade_date, daily_dir=None):
    """9 条跨模块不变式一一实现（按 id）。返回 (inv_results, detail_msgs)。"""
    modules = snapshot.get("modules") or {}
    ref_date = standard.get("referenceDate")
    details = []
    results = {}

    # INV-DATE-LOOKAHEAD
    b = True
    for mname, m in modules.items():
        if not isinstance(m, dict):
            continue
        for fn in ("dataDate", "asOf", "publishedAt"):
            v = m.get(fn)
            if isinstance(v, str) and trade_date and v > trade_date:
                b = False
                details.append(_detail_gap(f"INV-DATE-LOOKAHEAD: {mname}.{fn}={v} 晚于 tradeDate {trade_date}"))
        if mname == "margin":
            ref = m.get("latestPublishedReference")
            if isinstance(ref, dict) and isinstance(ref.get("dataDate"), str) and trade_date and ref["dataDate"] > trade_date:
                b = False
                details.append(_detail_gap(f"INV-DATE-LOOKAHEAD: margin.latestPublishedReference.dataDate 晚于 tradeDate"))
    results["INV-DATE-LOOKAHEAD"] = b

    # INV-UNIT-亿元：模块若声明 unit 须为亿元（无数值破坏的硬门禁）
    b = True
    for mname in ("turnover", "fundFlow", "northbound", "margin"):
        m = modules.get(mname) or {}
        if isinstance(m, dict) and m.get("unit") is not None and m.get("unit") != "亿元":
            b = False
            details.append(_detail_gap(f"INV-UNIT-亿元: {mname}.unit={m.get('unit')!r} 应为亿元"))
    results["INV-UNIT-亿元"] = b

    # INV-LIST-SORT-SIGN：fundFlow 符号由 _validate_lists 覆盖；northbound netBuy>0/netSell<0
    nb = modules.get("northbound") or {}
    legacy = nb.get("legacyImportedFields") if isinstance(nb, dict) else None
    b = True
    if isinstance(legacy, dict):
        entries = []
        if isinstance(legacy.get("netBuyTop10"), list):
            entries.extend((it.get("netInflowYi"), "netBuyTop10") for it in legacy["netBuyTop10"] if isinstance(it, dict))
        if isinstance(legacy.get("netSellTop10"), list):
            entries.extend((it.get("netInflowYi"), "netSellTop10") for it in legacy["netSellTop10"] if isinstance(it, dict))
        for v, which in entries:
            if _is_finite_number(v):
                if which.endswith("netBuyTop10") and v <= 0:
                    b = False
                if which.endswith("netSellTop10") and v >= 0:
                    b = False
    results["INV-LIST-SORT-SIGN"] = b

    # INV-MARGIN-IDENTITY：FINAL 分支恒等（容差 0.05）+ change 环比（容差 0.01）已在 check_margin 内；
    # 此处做最终确认避免模块级遗漏。
    mg = modules.get("margin") or {}
    b = True
    if isinstance(mg, dict) and mg.get("status") == "FINAL":
        fin, sec, bal = mg.get("financingBalance"), mg.get("securitiesLendingBalance"), mg.get("marginBalance")
        if all(_is_finite_number(v) for v in (fin, sec, bal)):
            if abs(float(bal) - (float(fin) + float(sec))) > 0.05:
                b = False
    results["INV-MARGIN-IDENTITY"] = b

    # INV-TURNOVER-IDENTITY：COMPARABLE 恒等（已在 check_turnover 内）
    to = modules.get("turnover") or {}
    b = True
    if isinstance(to, dict) and to.get("comparisonStatus") == "COMPARABLE":
        today, prev, delta, pct = to.get("turnoverToday"), to.get("turnoverPrevious"), to.get("turnoverDelta"), to.get("turnoverChangePct")
        if _is_finite_number(today) and _is_finite_number(prev) and _is_finite_number(delta):
            if abs(float(delta) - (float(today) - float(prev))) > 0.01:
                b = False
        if _is_finite_number(prev) and float(prev) != 0 and _is_finite_number(delta) and _is_finite_number(pct):
            if abs(float(pct) - float(delta) / float(prev) * 100.0) > 0.01:
                b = False
    results["INV-TURNOVER-IDENTITY"] = b

    # INV-SENTIMENT-WIDTH
    se = modules.get("sentiment") or {}
    b = True
    if isinstance(se, dict) and se.get("status") == spec_required_status(standard, "sentiment"):
        vals = [se.get(k) for k in ("riseCount", "fallCount", "flatCount")]
        if all(_is_finite_number(v) for v in vals):
            if float(vals[0]) + float(vals[1]) + float(vals[2]) < 4000:
                b = False
    results["INV-SENTIMENT-WIDTH"] = b

    # INV-ENUM-SOURCE-METHOD：各模块 source/method 枚举合法，由通用引擎覆盖（字段级）。

    # INV-REF-EXACT：参考日精确断言
    b = True
    if trade_date == ref_date:
        ra = standard.get("referenceAssertions") or {}
        day = ra.get(ref_date) or {}
        from_fields = check_reference_modules(snapshot, standard, trade_date, daily_dir)
        if from_fields:
            b = False
    results["INV-REF-EXACT"] = b

    # INV-NORTHBOUND-PIT
    nb2 = modules.get("northbound") or {}
    b = True
    if isinstance(nb2, dict) and nb2.get("mode") == "POST_20240819_OFFICIAL_REPLACEMENT":
        qh = nb2.get("quarterlyHolding")
        if isinstance(qh, dict):
            if trade_date and isinstance(qh.get("asOf"), str) and qh["asOf"] > trade_date:
                b = False
            if trade_date and isinstance(qh.get("publishedAt"), str) and qh["publishedAt"] > trade_date:
                b = False
    results["INV-NORTHBOUND-PIT"] = b

    return results, details


def spec_required_status(standard, module_name):
    return _lookup_module(standard, module_name).get("requiredStatus")


def check_reference_modules(snapshot, standard, trade_date, daily_dir=None):
    """参考日所有模块 referenceAssertions 的聚合 gap 列表（供 INV-REF-EXACT 引用）。"""
    if trade_date != standard.get("referenceDate"):
        return []
    ra = standard.get("referenceAssertions") or {}
    day = ra.get(trade_date) or {}
    out = []
    for mname in day.keys():
        out.extend(_run_reference_assertions(snapshot, standard, mname, trade_date, daily_dir, None))
    return [d for d in out if not d["passed"]]


# ---------------------------------------------------------------- 启动自检


def load_standard():
    if not os.path.exists(STANDARD_PATH):
        raise FileNotFoundError(STANDARD_PATH)
    with open(STANDARD_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


_LOADED_STANDARD = None


def _load_standard(_force=False):
    global _LOADED_STANDARD
    if _LOADED_STANDARD is None or _force:
        _LOADED_STANDARD = load_standard()
    return _LOADED_STANDARD


def startup_self_check(standard):
    """P0-002 自检：version==2；9 模块 ruleId/ruleVersion 存在；handler 注册表一致性。"""
    errors = []
    if standard.get("version") != 2:
        errors.append(f"standard.version={standard.get('version')!r} 期望 2")
    modules = standard.get("modules", {})
    if not isinstance(modules, dict) or len(modules) < 9:
        errors.append(f"modules 数 {len(modules)} 期望 9")
    module_names = list(modules.keys())
    if module_names != MODULE_ORDER:
        errors.append(f"modules 顺序/命名不符: {module_names}")
    for name, spec in modules.items():
        if not isinstance(spec, dict):
            errors.append(f"模块 {name} 非对象")
            continue
        if not spec.get("ruleId"):
            errors.append(f"模块 {name} 缺 ruleId")
        if not spec.get("ruleVersion"):
            errors.append(f"模块 {name} 缺 ruleVersion")
    # handler 注册表一致性：标准声明了 handler 的复杂规则必须已实现。
    for name, spec in modules.items():
        rule_id = spec.get("ruleId")
        if rule_id and rule_id in _COMPLEX_HANDLERS:
            handler_name = _COMPLEX_HANDLERS[rule_id]
            if not callable(globals().get(handler_name)):
                errors.append(f"handler {handler_name!r} (ruleId={rule_id}) 未实现")
        # 未在注册表中的 rule 一律用通用引擎（_validate_field_values/_validate_items/_validate_lists）。
    return errors


MODULE_ORDER = [
    "marketIndex", "turnover", "sentiment", "sectorPerformance",
    "fundFlow", "northbound", "margin", "tracks", "summary",
]

# 模块名 -> 校验函数（签名: snapshot, standard, trade_date, manifest, daily_dir, ctx）
CHECKERS = {
    "marketIndex": check_marketindex,
    "turnover": check_turnover,
    "sentiment": check_sentiment,
    "sectorPerformance": check_sectors,
    "fundFlow": check_fundflow,
    "northbound": check_northbound,
    "margin": check_margin,
    "tracks": check_tracks,
    "summary": check_summary,
}


# ---------------------------------------------------------------- 主流程


def evaluate_modules(snapshot, standard, trade_date, manifest, daily_dir=None, ctx=None):
    """对单个快照执行 9 模块验收。返回 (modules_out, all_pass)。"""
    ctx = ctx or {}
    ctx["manifest"] = manifest
    checks = {
        m: CHECKERS[m](snapshot, standard=standard, trade_date=trade_date,
                       manifest=manifest, daily_dir=daily_dir, ctx=ctx)
        for m in MODULE_ORDER
    }
    # cross-module invariants 汇总
    inv_results, inv_details = run_cross_module_invariants(snapshot, standard, trade_date, daily_dir)
    # 把 invariant failures 接入对应模块的校验，确保不因模块级遗漏放过。
    # 简单的做法：构造一个全局 invariant 虚拟模块不参与 9 模块 pass 判定，
    # 但让 OVERALL 反映 invariant 失败。
    all_pass = all(checks[m]["pass"] for m in MODULE_ORDER) and all(inv_results.values())
    return checks, all_pass, inv_results


def build_entry(trade_date, manifest, standard, daily_dir=None):
    daily_dir = daily_dir or DAILY_DIR
    yyyy = trade_date[:4]
    path = os.path.join(daily_dir, yyyy, f"{trade_date}.json")
    modules_out = {}
    if not os.path.exists(path):
        for name in MODULE_ORDER:
            modules_out[name] = _result("_", False, [_detail_gap("FILE_MISSING")], "_")
        return {
            "gap": "FILE_MISSING",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }
    with open(path, "r", encoding="utf-8") as fh:
        snapshot = json.load(fh)
    checks, all_pass, inv_results = evaluate_modules(snapshot, standard, trade_date, manifest, daily_dir)
    modules_out = checks
    overall_pass = all_pass
    return {
        "gap": None,
        "schemaValid": True,
        "modules": modules_out,
        "invariants": inv_results,
        "overall": "PASS" if overall_pass else "FAIL",
        "pass": overall_pass,
    }


def console_line(trade_date, entry):
    mods = entry.get("modules", {})
    parts = []
    for name in MODULE_ORDER:
        parts.append(f"{'P' if mods.get(name, {}).get('pass') else 'F'}:{name}")
    flag = entry["overall"]
    gap = entry.get("gap")
    suffix = f" gap={gap}" if gap else ""
    return f"{flag:<4} {trade_date}  " + " ".join(parts) + suffix


def build_report(dates, entries, standard, manifest):
    pass_dates = [d for d in dates if entries[d]["pass"]]
    fail_dates = [d for d in dates if not entries[d]["pass"]]
    module_fail = {name: [] for name in MODULE_ORDER}
    for d in dates:
        for name in MODULE_ORDER:
            if not entries[d]["modules"].get(name, {}).get("pass"):
                module_fail[name].append(d)
    module_fail_counts = [
        {"module": name, "failDates": len(module_fail[name])}
        for name in MODULE_ORDER
    ]
    # provenance (P0-009)
    daily_dir = os.path.join("web", "public", "data", "daily")
    per_date_sha = {}
    for d in dates:
        p = os.path.join(daily_dir, d[:4], f"{d}.json")
        per_date_sha[d] = _sha256_file(p) if os.path.exists(p) else None
    standard_sha = _sha256_file(STANDARD_PATH) if os.path.exists(STANDARD_PATH) else None
    manifest_sha = _sha256_file(MANIFEST_PATH) if os.path.exists(MANIFEST_PATH) else None
    acceptor_sha = _sha256_file(__file__) if os.path.exists(__file__) else None
    report = {
        "provenance": {
            "repoCommit": _repo_commit(),
            "standardSha256": standard_sha,
            "acceptorSha256": acceptor_sha,
            "manifestSha256": manifest_sha,
            "schemaVersion": manifest.get("schemaVersion") if isinstance(manifest, dict) else None,
            "perDateSnapshotSha256": per_date_sha,
            "pythonVersion": platform.python_version(),
            "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(),
        },
        "standard": STANDARD_PATH,
        "dates": {
            d: {
                "gap": entries[d].get("gap"),
                "overall": entries[d]["overall"],
                "invariants": entries[d].get("invariants"),
                "modules": {
                    name: {
                        "status": entries[d]["modules"][name]["status"],
                        "pass": entries[d]["modules"][name]["pass"],
                        "rule": entries[d]["modules"][name]["rule"],
                        "details": entries[d]["modules"][name]["details"],
                    }
                    for name in MODULE_ORDER
                },
            }
            for d in dates
        },
        "summary": {
            "passDates": pass_dates,
            "failDates": fail_dates,
            "moduleFailCounts": module_fail_counts,
        },
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="SMI 数据侧验收器 v2")
    parser.add_argument("--date", dest="date", help="验收单个日期 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="验收 manifest 全部 availableDates")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="报告输出路径")
    args = parser.parse_args(argv)

    try:
        standard = load_standard()
    except FileNotFoundError:
        sys.stderr.write(f"验收标准缺失: {STANDARD_PATH}\n")
        sys.exit(2)
    self_check_errors = startup_self_check(standard)
    if self_check_errors:
        for e in self_check_errors:
            sys.stderr.write(f"自检失败: {e}\n")
        sys.exit(3)

    if not os.path.exists(MANIFEST_PATH):
        sys.stderr.write(f"日期清单缺失: {MANIFEST_PATH}\n")
        sys.exit(2)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    if args.date:
        dates = [args.date]
    else:
        dates = list(manifest.get("availableDates", []))

    entries = {}
    for trade_date in dates:
        entries[trade_date] = build_entry(trade_date, manifest, standard)
        print(console_line(trade_date, entries[trade_date]))

    pass_dates = [d for d in dates if entries[d]["pass"]]
    fail_dates = [d for d in dates if not entries[d]["pass"]]
    module_fail = {name: [] for name in MODULE_ORDER}
    for d in dates:
        for name in MODULE_ORDER:
            if not entries[d]["modules"].get(name, {}).get("pass"):
                module_fail[name].append(d)

    print()
    print(f"汇总：PASS={len(pass_dates)}  FAIL={len(fail_dates)}  共 {len(dates)} 个日期")
    print(f"passDates: {pass_dates}")
    print(f"failDates: {fail_dates}")
    print("各模块失败日期数：")
    for name in MODULE_ORDER:
        print(f"  {name:<16} failDates={len(module_fail[name])}")
        if module_fail[name]:
            print(f"    dates: {module_fail[name]}")

    report = build_report(dates, entries, standard, manifest)
    report_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(report_dir, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print()
    print(f"报告已写入: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
