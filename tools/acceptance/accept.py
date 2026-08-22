# -*- coding: utf-8 -*-
"""SMI 数据侧验收器 v2（严格消费 docs/acceptance/template-standard.json 单一真源）。

对比旧版，v2 落地 R12 P0-001..P0-009 的执行侧要求，并针对评审报告
（work/SMI_R12_P01_Review_Report.md）FIX 建议加固到 P0.2：

- P0-001 / INV-REF-EXACT：referenceAssertions fail-closed 全量消费。expected 中每个
          name/dict-key 都必须被实际比对（missing 即 _detail_gap，禁止 continue 跳过）；
          参考日执行后做 declaredAssertionCount / consumedAssertionCount 覆盖率自检，二者不等该模块即 FAIL。
- P0-002：_COMPLEX_HANDLERS 改为 ruleId -> {supportedVersions, handler} 的真实 dispatch 真源；
          ruleId 未知或 ruleVersion 不受支持 → 启动自检失败(退出码 3)；CHECKERS 由 dispatch 表构造。
          所有复杂 handler 开头统一 _validate_field_values(mod, spec.fields)，状态豁免一律经标准
          fields 的 per-state 声明（required=false 或 skipStates），代码不做私自豁免。
- P0-003：northbound OFFICIAL_REPLACEMENT/PIT 强制 asOf/publishedAt 必存在且可解析（date.fromisoformat
          截断到日期）、asOf<=tradeDate 且 publishedAt<=tradeDate；缺任一即 FAIL；INV-NORTHBOUND-PIT 同样强制。
- P0-004 / INV-TURNOVER-IDENTITY：PREVIOUS_METHOD_MISMATCH 必须存在 crossMethodReference 对象
          （previous/delta/changePct 成组有限值、nonComparable===true、currentMethod/previousMethod 非空、
          内部算术恒等），任一缺失即 FAIL。
- P0-005 / INV-SENTIMENT-WIDTH：canonical 六计数 + 市场宽度 + 参考日精确断言 + 非参考日缺口说明。
- P0-006：tracks 时序/区间/占位/重算。item.date==tradeDate；模块 effectiveFrom/effectiveTo 覆盖
          tradeDate（仅 snapshot.meta.legacy && tradeDate==referenceDate 豁免）；redStockRatio 0~100；
          coreCatalyst/earningsRealization 按标准 rejectedPlaceholders 检查；sourceSystem 按标准 required；
          非 legacy 且 FINAL 的 tracks 用 collector.calculators.tracks.score_tracks 重算 score/decision。
- P0-007：summary 事实锚点。marketEnvironment↔turnover、trackConclusion↔tracks、margin段↔margin、
          northbound段↔northbound 逐条校验底层结构化事实。
- P0-008：crossModuleInvariants 9 条按 id 一一产出 results key（含 INV-ENUM-SOURCE-METHOD）；
          DATE 递归扫描 nested 时序字段；startup 校验 invariant id 集合相等。
- P0-009：report provenance 新增 evaluatedCommit(HEAD) + dirty(git status --porcelain)；
          repoCommit 语义注释为与 evaluatedCommit 同值；报告顶层加 reportCommitSemantics。

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
LATEST_PATH = os.path.join("web", "public", "data", "latest.json")
DAILY_DIR = os.path.join("web", "public", "data", "daily")
DEFAULT_REPORT = os.path.join("work", "acceptance", "baseline-report.json")

# 复杂规则 handler 注册表（P0-002 真实 dispatch 真源）。
# ruleId -> {supportedVersions, handler}。dispatch 时按标准该模块的 ruleId 查表：
# ruleId 未知或 ruleVersion 不在 supportedVersions -> 启动自检失败(退出码 3)。
# 通用引擎覆盖 marketIndex/sectorPerformance/fundFlow；复杂规则由下列 handler 落地。
# 支持版本以标准 modules[*].ruleVersion 为准（本仓标准当前值：turnover/northbound/tracks/summary=2，sentiment/margin=1）。
# 复杂规则 handler 注册表（P0-002 真实 dispatch 真源，P0-003 严格化后本表不变）。
# ruleVersion 以标准 modules[*].ruleVersion 为准；northbound/tracks 本轮(0.3)动过 fields 版本+1。
_COMPLEX_HANDLERS = {
    "turnover_V2": {"supportedVersions": [2, 3], "handler": "check_turnover"},
    "sentiment_V2": {"supportedVersions": [1], "handler": "check_sentiment"},
    "northbound_V2": {"supportedVersions": [2, 3], "handler": "check_northbound"},
    "margin_V2": {"supportedVersions": [1, 2, 3], "handler": "check_margin"},
    "tracks_V2": {"supportedVersions": [2, 3, 4], "handler": "check_tracks"},
    "summary_V2": {"supportedVersions": [2, 3, 4], "handler": "check_summary"},
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


def _parse_iso_date_strict(value):
    """把 YYYY-MM-DD 或严格 ISO-8601 datetime(YYYY-MM-DDTHH:MM:SS[±tz])解析为 datetime.date。

    全串严格解析，禁止任何“截断前 10 字符”逻辑：
    - len(s)==10  -> date.fromisoformat(s)（全串严格，抛错 -> None）
    - 含 "T"      -> datetime.fromisoformat(s) 严格解析后取 .date()（抛错 -> None）
    - 其它形态     -> None（不可解析）
    解析失败返回 None（调用方据此判定缺失/非法）。用于 P0-003 北向 PIT / DATE invariant / tracks 生效区间。
    """
    if not isinstance(value, str) or not value:
        return None
    from datetime import date as _date, datetime as _datetime
    try:
        if len(value) == 10:
            return _date.fromisoformat(value)
        if "T" in value or " " in value:
            dt = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return _datetime.fromisoformat(dt).date()
    except Exception:  # noqa: BLE001
        pass
    return None


def _git_dirty():
    """git status --porcelain 非空即为 dirty（P0-009）。"""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            timeout=10,
        )
        if out.returncode == 0:
            return bool(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return None
    return None


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



def _required_condition_met(container, rc):
    """requiredCondition 形如 {"whenField": X, "equals": V}：当 container[X] == V 时条件满足。
    非 dict 的 requiredCondition（如纯说明字符串）视为不 gate（恒满足）。rc 为 None 恒满足。"""
    if not isinstance(rc, dict):
        return True
    wf = rc.get("whenField")
    eq = rc.get("equals")
    if wf is None:
        return True
    return container.get(wf) == eq


def _validate_nested_value(val, spec, path, msgs):
    """递归值校验（统一顶层与嵌套）。支持 kind: string / finite / finitePositive /
    finiteNonNegative / nonNegativeInt / percentString / numericString / dateString /
    enum / boolean / const / object(递归 subFields) / array(minItems + itemFields 递归)。"""
    kind = spec.get("kind")
    if kind == "string":
        if not isinstance(val, str):
            msgs.append(_detail_gap(f"{path} 非字符串: {val!r}"))
    elif kind == "finite":
        if not _is_finite_number(val):
            msgs.append(_detail_gap(f"{path} 非有限数值: {val!r}"))
    elif kind == "finitePositive":
        if not _is_finite_number(val) or float(val) <= 0:
            msgs.append(_detail_gap(f"{path} 非有限正数: {val!r}"))
    elif kind == "finiteNonNegative":
        if not _is_finite_number(val) or float(val) < 0:
            msgs.append(_detail_gap(f"{path} 非有限非负数: {val!r}"))
    elif kind == "nonNegativeInt":
        if not _non_negative_int_ok(val):
            msgs.append(_detail_gap(f"{path} 非非负整数: {val!r}"))
    elif kind == "percentString":
        # 真实数字百分比全串：\d+(\.\d+)?%，且数值 0~100（P0-003/评审复核）
        if not isinstance(val, str) or not re.fullmatch(r"\d+(\.\d+)?%", val):
            msgs.append(_detail_gap(f"{path}={val!r} 非百分比字符串(如 85%)"))
        else:
            try:
                pv = float(val.rstrip("%"))
            except ValueError:
                pv = None
            if pv is None or not (math.isfinite(pv) and 0.0 <= pv <= 100.0):
                msgs.append(_detail_gap(f"{path}={val!r} 百分比数值须在 0~100"))
    elif kind == "numericString":
        if isinstance(val, bool) or not isinstance(val, str):
            msgs.append(_detail_gap(f"{path}={val!r} 非字符串"))
        else:
            try:
                nv = float(val.replace(",", "").strip())
            except (TypeError, ValueError):
                nv = None
            # 逗号数字串业务语义 = 有限且非负（P0-003：拒绝 NaN/Infinity/负值）
            if nv is None or not (math.isfinite(nv) and nv >= 0.0):
                msgs.append(_detail_gap(f"{path}={val!r} 非有限非负数值字符串"))
    elif kind == "dateString":
        if _parse_iso_date_strict(val) is None:
            msgs.append(_detail_gap(f"{path}={val!r} 非严格 ISO 日期"))
    elif kind == "boolean":
        if type(val) is not bool:
            msgs.append(_detail_gap(f"{path}={val!r} 非布尔"))
    elif kind == "const":
        exp = spec.get("constValue")
        if not (val == exp):
            msgs.append(_detail_gap(f"{path}={val!r} 应为 const {exp!r}"))
    elif kind == "enum":
        allowed = list(spec.get("enumValues", []))
        if len(allowed) == 1 and isinstance(allowed[0], bool):
            if type(val) is not bool:
                msgs.append(_detail_gap(f"{path}={val!r} 非布尔枚举"))
        elif val not in allowed:
            msgs.append(_detail_gap(f"{path}={val!r} 不在枚举 {allowed}"))
    elif kind == "object":
        if not isinstance(val, dict):
            msgs.append(_detail_gap(f"{path}={val!r} 非对象(dict)"))
        else:
            for sub in spec.get("subFields", []):
                _validate_sub_field(val, sub, f"{path}.{sub.get('name')}", msgs)
    elif kind == "array":
        if not isinstance(val, list):
            msgs.append(_detail_gap(f"{path}={val!r} 非列表"))
        else:
            min_items = spec.get("minItems")
            if min_items is not None and len(val) < min_items:
                msgs.append(_detail_gap(f"{path} 长度 {len(val)} < minItems {min_items}"))
            for i, item in enumerate(val):
                if not isinstance(item, dict):
                    msgs.append(_detail_gap(f"{path}[{i}] 非对象"))
                    continue
                for fsc in spec.get("itemFields", []):
                    _validate_sub_field(item, fsc, f"{path}[{i}].{fsc.get('name')}", msgs)
    else:
        msgs.append(_detail_gap(f"未知 kind {kind!r} 字段 {path}"))
    # 范围 / 长度 / 中文约束（字符串通用）
    if isinstance(val, str) and kind == "string":
        minchars = spec.get("minChars")
        if minchars is not None and len(val) < minchars:
            msgs.append(_detail_gap(f"{path} 长度 {len(val)} < minChars {minchars}"))
        if spec.get("cjkRequired"):
            ratio_min = spec.get("cjkRatioMin", 0.5)
            if _cjk_ratio(val) < ratio_min:
                msgs.append(_detail_gap(f"{path} 中文字符占比 {_cjk_ratio(val):.2f} < {ratio_min}"))
    lo = spec.get("min")
    hi = spec.get("max")
    if (lo is not None or hi is not None) and _is_finite_number(val):
        fv = float(val)
        if lo is not None and fv < lo:
            msgs.append(_detail_gap(f"{path}={fv} 小于下限 {lo}"))
        if hi is not None and fv > hi:
            msgs.append(_detail_gap(f"{path}={fv} 大于上限 {hi}"))


def _validate_sub_field(container, spec, path, msgs):
    """校验一个子字段：required + requiredCondition 门控 + 存在性，最后委托值校验。
    用于 object.subFields 与 array.itemFields（即递归 DSL）。"""
    name = spec.get("name")
    required = bool(spec.get("required", False))
    rc = spec.get("requiredCondition")
    if not _required_condition_met(container, rc):
        return
    if name not in container or container.get(name) is None:
        if required:
            msgs.append(_detail_gap(f"{path} 缺失/null（required）"))
        return
    _validate_nested_value(container[name], spec, path, msgs)



def _validate_field_values(module, field_specs, enum_extras=None, plan=None, status=None):
    """按标准 fields 声明的 kind/enum/min/max/minChars/cjkRequired 校验。

    plan: 可选 dict，字段名 -> bool。plan 中某字段为 False 时跳过模块级校验，交给 handler 自己处理。
    enum_extras: 参考日由 referenceAssertions 固化到的额外枚举值（referenceXlsx > canonicalSnapshot）。
    status: 当前模块状态。若字段 spec 声明了 skipStates 且 status 在其中，则该字段在模块级豁免
            （交由 handler 做状态相关校验）——状态豁免一律以标准字段声明为准，代码不做私自豁免。
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
        skip_states = spec.get("skipStates") or []
        if status is not None and skip_states and status in skip_states:
            # 标准 per-state 计划豁免：该字段在此状态下不要求模块级存在/非空，交由 handler 校验。
            continue
        # P0-002：requiredCondition 门控——条件不满足则整体跳过该字段校验（含 required 失效）；
        # 满足时该字段 required 才生效，缺失/null 即 FAIL。
        if not _required_condition_met(module, spec.get("requiredCondition")):
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
        elif kind == "object":
            _validate_nested_value(val, spec, name, msgs)  # 递归消费 subFields（P0-002 单一真源）
        elif kind == "array":
            _validate_nested_value(val, spec, name, msgs)
        elif kind in ("dateString", "boolean", "numericString", "const"):
            _validate_nested_value(val, spec, name, msgs)
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
    # 参考日精确断言（INV-REF-EXACT 聚合与模块级一致，P0-001）
    details.extend(_run_reference_assertions(snapshot, standard, "marketIndex", trade_date, daily_dir, ctx))
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
        # P0-004 / INV-TURNOVER-IDENTITY：MISMATCH 必须存在 crossMethodReference 对象（非可比契约）。
        cmr = mod.get("crossMethodReference")
        if not isinstance(cmr, dict):
            details.append(_detail_gap(
                "PREVIOUS_METHOD_MISMATCH 需 crossMethodReference 对象（previous/delta/changePct/nonComparable/currentMethod/previousMethod）"))
        else:
            need = ("previous", "delta", "changePct")
            has_nums = all(_is_finite_number(cmr.get(k)) for k in need)
            if not has_nums:
                details.append(_detail_gap(
                    f"crossMethodReference 需 previous/delta/changePct 三个有限数值成组，实际 "
                    f"previous={cmr.get('previous')!r} delta={cmr.get('delta')!r} changePct={cmr.get('changePct')!r}"))
            if cmr.get("nonComparable") is not True:
                details.append(_detail_gap("crossMethodReference.nonComparable 必须严格为 true"))
            if not cmr.get("currentMethod") or not cmr.get("previousMethod"):
                details.append(_detail_gap(
                    "crossMethodReference 需 currentMethod/previousMethod 非空"))
            if has_nums:
                cprev, cdelta, cpct = float(cmr["previous"]), float(cmr["delta"]), float(cmr["changePct"])
                if _is_finite_number(today):
                    if abs(cdelta - (float(today) - cprev)) > 0.01:
                        details.append(_detail_gap(
                            "crossMethodReference 算术破坏: |delta-(today-prev)|>0.01"))
                if cprev > 0:
                    if abs(cpct - cdelta / cprev * 100.0) > 0.01:
                        details.append(_detail_gap(
                            "crossMethodReference 算术破坏: |pct - delta/prev*100|>0.01"))
        # 兼容旧标量形式 crossMethodReferencePrevious/Delta/ChangePct（标准本轮同步改为对象后此分支不再触发）。
        if not isinstance(cmr, dict) and mod.get("crossMethodReferencePrevious") is not None:
            details.append(_detail_gap(
                "crossMethodReference 应采用对象结构（previous/delta/changePct/nonComparable/currentMethod/previousMethod）"))
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
    # P0-002：复杂 handler 开头统一消费标准 fields（mode/sourceSystem/officialDisclosureCompatible 全走引擎）。
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
        # P0-003-B：OFFICIAL 分支只保留粗查（status=FINAL、qh dict、qh.status=FINAL、items 非空 list）；
        # 逐项 typed schema（shareholding/pctOfIssued/market/code/...)交由通用引擎消费标准
        # quarterlyHolding.subFields（P0-002 改动使 object/array 递归 DSL 真正生效），不再手写逐字段。
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
            # PIT：asOf/publishedAt 必存在且可解析（_parse_iso_date_strict 严格全串），且 <= tradeDate。
            for fn in ("asOf", "publishedAt"):
                v = qh.get(fn)
                parsed = _parse_iso_date_strict(v)
                if v is None or v == "" or parsed is None:
                    details.append(_detail_gap(
                        f"OFFICIAL_REPLACEMENT 需 quarterlyHolding.{fn} 存在且可解析(YYYY-MM-DD)，实际 {v!r}"))
                    continue
                if trade_date and parsed > _parse_iso_date_strict(trade_date):
                    details.append(_detail_gap(
                        f"quarterlyHolding.{fn}={v} > tradeDate {trade_date} (look-ahead)"))
        # 占位 dict（status=UNAVAILABLE/items=[]）一律 FAIL——由上方检查覆盖。
    elif mode is None:
        details.append(_detail_gap("mode 缺失"))
    # 其它 mode 值（未入标准枚举）已由 _validate_field_values 枚举校验拦截并 FAIL。

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

    # P0-002：复杂 handler 开头统一消费标准 fields。
    # margin FINAL 才需要模块级余额字段；PENDING 由标准字段声明的 skipStates（如 ["PENDING"]）
    # 或 required=false 经 per-state 计划豁免——代码不私自豁免，完全读标准。
    details.extend(_validate_field_values(mod, spec.get("fields", []), status=status))
    # 参考日精确断言（INV-REF-EXACT 聚合与模块级一致，P0-001）
    details.extend(_run_reference_assertions(snapshot, standard, "margin", trade_date, daily_dir, ctx))

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
    contract = spec.get("decisionContract") or {}
    is_v4 = bool(contract) and int(spec.get("ruleVersion", 3)) >= 4
    allowed = spec.get("allowedStatuses")
    if allowed:
        if status not in allowed:
            details.append(_detail_gap(
                f"status={status!r} 不在 allowedStatuses {allowed}"))
    elif spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))

    ref_date = standard.get("referenceDate")
    if trade_date is None:
        trade_date = snapshot.get("tradeDate")

    # P0-006 时序/区间/占位/重算。配置生效区间豁免仅当 snapshot.meta.legacy 且 tradeDate==referenceDate。
    meta = snapshot.get("meta") or {}
    is_legacy_snap = bool(meta.get("legacy"))
    exempt_eff = bool(is_legacy_snap and trade_date == ref_date)

    # P0-002：复杂 handler 开头统一消费标准 fields。
    # configVersion/effectiveFrom/effectiveTo/sourceSystem 按标准声明校验；legacy+参考日豁免区间字段。
    plan = {}
    if exempt_eff:
        plan["effectiveFrom"] = False
        plan["effectiveTo"] = False
    details.extend(_validate_field_values(mod, spec.get("fields", []), plan=plan))

    cfg_version = mod.get("configVersion")
    if cfg_version is None:
        details.append(_detail_gap("模块级 configVersion 缺失"))

    # R16 版本分支（R15 评审阻断点 G）：configVersion>=3.2 走严格 v4
    # 字段契约；3.0/3.1/2.0 等存量只做状态⇄decision 配对（显式兼容分支，
    # 不靠 optionality 偶然放行）。"legacy" 等非数值合法标记按非 strict。
    strict_v42 = False
    if isinstance(cfg_version, str):
        try:
            strict_v42 = (
                tuple(int(x) for x in cfg_version.split(".")[:2]) >= (3, 2)
            )
        except ValueError:
            strict_v42 = False

    # 生效区间覆盖 tradeDate（除 legacy+参考日豁免）——防止今天配置倒灌历史日期。
    # P0-006-A：effectiveFrom/effectiveTo 用 _parse_iso_date_strict 严格解析，任一不可解析即 FAIL（fail-closed，不再跳过比较）。
    if not exempt_eff:
        eff_from, eff_to = mod.get("effectiveFrom"), mod.get("effectiveTo")
        for fn in ("effectiveFrom", "effectiveTo"):
            if not mod.get(fn):
                details.append(_detail_gap(f"模块级 {fn} 缺失（需覆盖 tradeDate）"))
        pf = _parse_iso_date_strict(eff_from)
        pt = _parse_iso_date_strict(eff_to)
        td = _parse_iso_date_strict(trade_date)
        if eff_from is not None and pf is None:
            details.append(_detail_gap(f"effectiveFrom={eff_from!r} 不可解析为严格 ISO 日期"))
        if eff_to is not None and pt is None:
            details.append(_detail_gap(f"effectiveTo={eff_to!r} 不可解析为严格 ISO 日期"))
        if pf is not None and pt is not None and td is not None:
            if not (pf <= td <= pt):
                details.append(_detail_gap(
                    f"配置生效区间 {eff_from}..{eff_to} 未覆盖 tradeDate {trade_date}"))

    # v4 状态-判定矩阵（R14-P2-01 产品裁决；legacy 参考日豁免，
    # 由 referenceAssertions 兜底）。旧契约快照（decision 非 TRACKS_* 或
    # 缺失）不做矩阵回溯判定，交由历史覆盖 Profile 处理。
    if is_v4 and not exempt_eff:
        decision = mod.get("decision")
        cov = mod.get("coveragePct")
        readiness = mod.get("dataReadiness")
        target = float(contract.get("coverageTargetPct", 80.0))
        floor = float(contract.get("coverageHardFloorPct", 65.0))
        module_decisions = set(contract.get("moduleDecisions") or [])
        readiness_map = contract.get("readinessMap") or {}

        # 1) decision 必须存在且属于契约枚举（所有状态，无一例外）
        if decision is None:
            details.append(_detail_gap(
                f"status={status} 必须携带模块级 decision"))
        elif module_decisions and decision not in module_decisions:
            details.append(_detail_gap(
                f"模块级 decision={decision!r} 不在契约枚举"))

        # 1b) 权威版本时间表（R16-P2-01）：configVersion 是被验收事实，
        # 不得同时作为验收强度的可信依据（自证循环——未来新快照错误
        # 自报 3.0 会伪装成"历史兼容"绕过 3.2 严格契约）。快照外部的
        # tracksVersionSchedule 把旧版本绑定到既有历史日期；cutoff 之后
        # 自报低于 minConfigVersion 一律 FAIL。
        schedule = spec.get("tracksVersionSchedule") or []
        if schedule:
            rule = None
            for r in schedule:
                if not isinstance(r, dict):
                    continue
                thr = r.get("through")
                frm = r.get("from")
                if isinstance(thr, str) and trade_date <= thr:
                    rule = r
                    break
                if isinstance(frm, str) and trade_date >= frm:
                    rule = r
                    break
            if rule is not None:
                allowed_versions = rule.get("allowedConfigVersions")
                if (
                    isinstance(allowed_versions, list)
                    and cfg_version not in allowed_versions
                ):
                    details.append(_detail_gap(
                        f"configVersion={cfg_version!r} 不在 {trade_date} 的权威版本表 "
                        f"allowedConfigVersions={allowed_versions}"))
                min_ver = rule.get("minConfigVersion")
                if isinstance(min_ver, str) and isinstance(cfg_version, str):
                    try:
                        cfg_t = tuple(int(x) for x in cfg_version.split(".")[:2])
                    except ValueError:
                        cfg_t = None
                    try:
                        min_t = tuple(int(x) for x in min_ver.split(".")[:2])
                    except ValueError:
                        min_t = None
                    # R17-P2-01：cutoff 规则 fail-closed——非数值版本
                    # （legacy/3.x/损坏值）无法证明 >= 数值下限，一律 FAIL。
                    # 解析失败不再静默 pass（旧行为依赖不存在的白名单兜底，
                    # 构成 fail-open 版本降级旁路）。
                    if cfg_t is None:
                        if rule.get("numericOnly") or min_t is not None:
                            details.append(_detail_gap(
                                f"configVersion={cfg_version!r} 非严格 x.y 数值版本，"
                                f"无法满足 {trade_date} 起的权威数值下限 "
                                f"{min_ver!r}（版本降级旁路）"))
                    elif min_t is not None and cfg_t < min_t:
                        details.append(_detail_gap(
                            f"configVersion={cfg_version!r} 低于 {trade_date} 起的"
                            f"权威下限 {min_ver!r}（版本降级旁路）"))

        # 2) 穷举状态机：status ⇄ decision ⇄ coverage 区间（R15 阻断点
        #    A/B/C：PARTIAL+INSUFFICIENT、UNAVAILABLE 缺 decision/旧值、
        #    FINAL 不验 coverage 均须 FAIL）
        if decision is not None and decision in module_decisions:
            if status == "FINAL":
                if decision != "TRACKS_SUFFICIENT":
                    details.append(_detail_gap(
                        f"FINAL 仅允许 TRACKS_SUFFICIENT，实际 {decision!r}"))
                if not _is_finite_number(cov) or float(cov) < target:
                    details.append(_detail_gap(
                        f"FINAL/TRACKS_SUFFICIENT 要求 coverage>={target}，"
                        f"实际 {cov!r}"))
            elif status == "PARTIAL":
                if decision == "TRACKS_INSUFFICIENT":
                    details.append(_detail_gap(
                        "PARTIAL 不允许 TRACKS_INSUFFICIENT（该 decision 仅属于 "
                        "UNAVAILABLE；PARTIAL⇄SUFFICIENT|DEGRADED）"))
                elif decision == "TRACKS_SUFFICIENT":
                    if not _is_finite_number(cov) or float(cov) < target:
                        details.append(_detail_gap(
                            f"TRACKS_SUFFICIENT 要求 coverage>={target}，实际 {cov!r}"))
                elif decision == "TRACKS_DEGRADED":
                    if not _is_finite_number(cov) or not (floor <= float(cov) < target):
                        details.append(_detail_gap(
                            f"TRACKS_DEGRADED 要求 coverage∈[{floor},{target})，实际 {cov!r}"))
            elif status == "UNAVAILABLE":
                if decision != "TRACKS_INSUFFICIENT":
                    details.append(_detail_gap(
                        f"UNAVAILABLE 仅允许 TRACKS_INSUFFICIENT，实际 {decision!r}"))

        # 3) readinessMap（R15 阻断点 D）：strict 必填且精确一致；
        #    非 strict 存在时仍须一致（软校验），缺失不追加要求
        if decision is not None and decision in readiness_map:
            expected_r = readiness_map[decision]
            if readiness is None:
                if strict_v42:
                    details.append(_detail_gap(
                        "configVersion>=3.2 必须携带模块级 dataReadiness"
                        f"（decision={decision!r} 期望 {expected_r!r}）"))
            elif readiness != expected_r:
                details.append(_detail_gap(
                    f"dataReadiness={readiness!r} 与 decision={decision!r} 不一致"
                    f"（期望 {expected_r!r}）"))

        if strict_v42:
            # R15 阻断点 D：阈值透传字段必填且与 decisionContract 单一真源一致
            for fkey, want in (
                ("coverageTargetPct", target),
                ("coverageHardFloorPct", floor),
            ):
                val = mod.get(fkey)
                if not _is_finite_number(val):
                    details.append(_detail_gap(
                        f"configVersion>=3.2 必须携带有限 {fkey}，实际 {val!r}"))
                elif float(val) != want:
                    details.append(_detail_gap(
                        f"{fkey}={val!r} 与 decisionContract({want}) 不一致"))
            if not isinstance(mod.get("warmingUpBoards"), list):
                details.append(_detail_gap(
                    "configVersion>=3.2 必须携带模块级 warmingUpBoards 数组"))

    # items >= 4 且逐列 typed 校验
    items = mod.get("items")
    items_spec = spec.get("items") or {}
    if not isinstance(items, list):
        details.append(_detail_gap("items 不是 list"))
    else:
        # v4：UNAVAILABLE 的 items 可为空/信息性，契约由模块级矩阵约束
        skip_item_checks = is_v4 and status == "UNAVAILABLE"
        if not skip_item_checks and is_v4:
            # 正式/预热分离（R14 §5.3；R15 阻断点 E/F 修订）：
            # - formal 仅计 dataReadiness∈{READY,DEGRADED}（strict）——
            #   INSUFFICIENT/FETCH_FAILED 是诚实数据缺口，不是"正式评分项"，
            #   不得充数 minFormalItems；非 strict（3.0/3.1 存量）沿用
            #   "非 WARMING_UP 即 formal" 的旧口径（旧数据无 readiness 字段）。
            # - WARMING_UP 四字段（score/coveragePct/dimensionPass/decision）
            #   全部按生产契约校验，不得只查两项。
            if strict_v42:
                formal_items = [
                    it for it in items
                    if isinstance(it, dict)
                    and it.get("dataReadiness") in ("READY", "DEGRADED")
                ]
            else:
                formal_items = [
                    it for it in items
                    if not (isinstance(it, dict)
                            and it.get("dataReadiness") == "WARMING_UP")
                ]
            warming_items = [
                it for it in items
                if isinstance(it, dict)
                and it.get("dataReadiness") == "WARMING_UP"
            ]
            min_formal = int(contract.get("minFormalItems", 4))
            if len(formal_items) < min_formal:
                details.append(_detail_gap(
                    f"正式评分项（dataReadiness∈READY/DEGRADED）数量 "
                    f"{len(formal_items)} < {min_formal}"))
            for w in warming_items:
                if w.get("score") is not None:
                    details.append(_detail_gap(
                        f"WARMING_UP 项 {w.get('trackId')!r} 不得输出成熟 score"))
                if w.get("decision") != "数据不足":
                    details.append(_detail_gap(
                        f"WARMING_UP 项 {w.get('trackId')!r} "
                        f"decision 必须为「数据不足」，实际 {w.get('decision')!r}"))
                if w.get("coveragePct") is not None:
                    details.append(_detail_gap(
                        f"WARMING_UP 项 {w.get('trackId')!r} coveragePct 必须为 null"))
                if w.get("dimensionPass") is not None:
                    details.append(_detail_gap(
                        f"WARMING_UP 项 {w.get('trackId')!r} dimensionPass 必须为 null"))
            for it in formal_items:
                if not isinstance(it, dict):
                    continue
                tid = it.get("trackId")
                if isinstance(tid, str) and tid.startswith("dyn_"):
                    continue  # 动态候选定性列允许 fail-closed 留白
                for tf in ("coreCatalyst", "earningsRealization"):
                    tv = it.get(tf)
                    if not (isinstance(tv, str) and len(tv.strip()) >= 2):
                        details.append(_detail_gap(
                            f"非动态项 {tid!r}.{tf} 必填非空（≥2 字），"
                            f"实际 {tv!r}"))
            if status == "FINAL":
                # FINAL=全就绪契约：正式项必须携带成熟 score（v4 标准里
                # score 因 WARMING_UP/INSUFFICIENT 项降级为可选，FINAL 态
                # 在代码层恢复强制）。
                for it in formal_items:
                    if isinstance(it, dict) and not _is_finite_number(it.get("score")):
                        details.append(_detail_gap(
                            f"FINAL 态正式项 {it.get('trackId')!r} 缺成熟 score"))
        if not skip_item_checks:
            if not is_v4 and len(items) < 4:
                details.append(_detail_gap(f"items 长度 {len(items)} < 4"))
            enum_extras = {}
            ra = ctx.get("reference_assertions_for") if ctx else None
            if trade_date == ref_date:
                enum_extras = _tracks_reference_enum_extras(standard)
            eff_items_spec = items_spec
            eff_item_plan = _tracks_item_plan(cfg_version == "legacy")
            if is_v4:
                # v4：minFormalItems（代码层）取代总量 minItems；定性双列
                # 改由条件必填门禁（动态候选允许留白），绕过 declarative 检查
                eff_items_spec = {
                    k: v for k, v in items_spec.items() if k != "minItems"
                }
                eff_item_plan = {
                    **eff_item_plan,
                    "coreCatalyst": False,
                    "earningsRealization": False,
                }
            details.extend(_validate_items(mod, eff_items_spec, enum_extras=enum_extras,
                                           item_plan=eff_item_plan))
            # trackId 集合与 referenceAssertions/模块定义一致
            #（v4：仅约束 legacy 参考日；动态池逐日变化，不做集合固化）
            ref_track_ids = _reference_track_ids(standard)
            ids = []
            for it in items:
                if isinstance(it, dict) and it.get("trackId") is not None:
                    ids.append(it["trackId"])
            if ref_track_ids and (not is_v4 or trade_date == ref_date):
                if set(ids) != set(ref_track_ids):
                    details.append(_detail_gap(
                        f"trackId 集合 {sorted(set(ids))} 与 referenceAssertions 集合 {sorted(ref_track_ids)} 不一致"))
            # P0-006：item.date 必须存在且 == tradeDate；文本占位检查；redStockRatio 0~100；score/decision 重算。
            rejected = set(standard.get("rejectedPlaceholders") or [])
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                item_date = it.get("date")
                if not item_date or item_date != trade_date:
                    details.append(_detail_gap(
                        f"tracks.items[{i}] date 缺失或 != tradeDate {trade_date}，实际 {item_date!r}"))
                for text_field in ("coreCatalyst", "earningsRealization", "ladderCompleteness"):
                    tv = it.get(text_field)
                    if isinstance(tv, str):
                        for ph in rejected:
                            if ph in tv:
                                details.append(_detail_gap(
                                    f"tracks.items[{i}].{text_field} 含占位词 {ph!r}: {tv!r}"))
                            break
                pr = _parse_percent(it.get("redStockRatio"))
                if pr is not None and not (0.0 <= pr <= 100.0):
                    details.append(_detail_gap(
                        f"tracks.items[{i}].redStockRatio 解析值 {pr} 超出 0~100"))
            # 非 legacy 且 status=FINAL：重算 score/decision（参考日 legacy 跳过，由 reference assertions 兜底）。
            if (not is_legacy_snap) and status == "FINAL" and isinstance(items, list) and items:
                _recalc_tracks(items, snapshot, details)

    details.extend(_run_reference_assertions(snapshot, standard, "tracks", trade_date, daily_dir, ctx))
    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: items>=4；逐列 typed 校验通过"))
    return _result(rule, ok, details, status)


def _is_iso_date(value):
    """十分量级 check：str 且形如 YYYY-MM-DD（用于生效区间覆盖手比较）。"""
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _parse_percent(value):
    """把 '85%'/'85.5%' 解析为 0~100 数值；解析失败返回 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)%", str(value).strip())
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _recalc_tracks(items, snapshot_holder, details):
    """非 legacy FINAL 的 tracks：用 collector.calculators.tracks.score_tracks 重算 score/decision。
    输入不完整/窗口未成熟（INSUFFICIENT）而快照却给出 FINAL 值 -> FAIL。
    无法加载计算器或重算失败是执行侧缺口 -> FAIL（fail-closed）。"""
    try:
        from collector.calculators.tracks import score_tracks
    except Exception as exc:  # noqa: BLE001
        details.append(_detail_gap(f"无法加载 score_tracks 计算器: {type(exc).__name__}: {exc}"))
        return
    try:
        recomputed = score_tracks(list(items))
    except Exception as exc:  # noqa: BLE001
        details.append(_detail_gap(f"score_tracks 重算失败: {type(exc).__name__}: {exc}"))
        return
    if not isinstance(recomputed, list):
        details.append(_detail_gap("score_tracks 重算未返回 list"))
        return
    # P0-006-B：重算后强制 set(recomputed trackId) == set(snapshot trackId) 且数量相等；不等或为空 -> FAIL。
    rec_ids = {str(r.get("trackId")) for r in recomputed
               if isinstance(r, dict) and r.get("trackId") is not None}
    snap_ids = {str(it.get("trackId")) for it in items
                if isinstance(it, dict) and it.get("trackId") is not None}
    if rec_ids != snap_ids or len(rec_ids) == 0:
        details.append(_detail_gap(
            f"重算 trackId 集合 {sorted(rec_ids)} 与快照 {sorted(snap_ids)} 不一致"))
        return
    by_id = {}
    for it in items:
        if isinstance(it, dict) and it.get("trackId") is not None:
            by_id[str(it["trackId"])] = it
    for r in recomputed:
        if not isinstance(r, dict):
            continue
        tid = r.get("trackId")
        snap_it = by_id.get(str(tid))
        if snap_it is None:
            continue
        rec = r.get("decision")
        rec_score = r.get("score")
        snap_score = snap_it.get("score")
        snap_dec = snap_it.get("decision")
        # 快照是 FINAL 判定值而重算结果为 INSUFFICIENT -> 数据侧提供超出可推导范围的 FINAL，FAIL。
        if rec == "INSUFFICIENT" and snap_dec not in (None, "INSUFFICIENT"):
            details.append(_detail_gap(
                f"tracks[{tid}] 重算 INSUFFICIENT 但快照为 FINAL 判定 {snap_dec!r}（输入不完整却给完整判定）"))
            continue
        if rec != "INSUFFICIENT":
            if _is_finite_number(snap_score) and _is_finite_number(rec_score):
                if abs(float(snap_score) - float(rec_score)) > 0.1:
                    details.append(_detail_gap(
                        f"tracks[{tid}] score 重算 {rec_score} 与快照 {snap_score} 不一致(容差0.1)"))
            if snap_dec is not None and str(snap_dec) != str(rec):
                details.append(_detail_gap(
                    f"tracks[{tid}] decision 重算 {rec!r} 与快照 {snap_dec!r} 不一致"))


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



def _run_summary_facts(sf_cfg, mod, snapshot, standard):
    """P0-007：按标准 summary.summaryFacts 机读配置执行事实锚点检查（无则调用方回退硬编码）。
    配置含 marketEnvironment / margin / northbound / trackConclusion 四个 anchor。返回 gap detail 列表。"""
    modules = snapshot.get("modules") or {}
    msgs = []
    me_cfg = sf_cfg.get("marketEnvironment")
    if isinstance(me_cfg, dict):
        to_mod = modules.get("turnover") or {}
        me = mod.get("marketEnvironment") or ""
        if isinstance(to_mod, dict) and to_mod.get("comparisonStatus") == "COMPARABLE":
            for w in me_cfg.get("forbiddenWords", []):
                if w and w in me:
                    msgs.append(_detail_gap(f"turnover COMPARABLE 但 marketEnvironment 含 {w!r}"))
            vs = to_mod.get("volumeState")
            vwm = me_cfg.get("volumeWordMap") or {}
            want = vwm.get(vs)
            if want and want not in me:
                msgs.append(_detail_gap(f"turnover volumeState={vs} 但 marketEnvironment 未提及 {want!r}"))
            num = {
                "turnoverToday": int(to_mod["turnoverToday"]) if _is_finite_number(to_mod.get("turnoverToday")) else None,
                "turnoverPrevious": int(to_mod["turnoverPrevious"]) if _is_finite_number(to_mod.get("turnoverPrevious")) else None,
                "turnoverDelta": int(abs(float(to_mod["turnoverDelta"]))) if _is_finite_number(to_mod.get("turnoverDelta")) else None,
            }
            for anchor_name in me_cfg.get("numericAnchors", []):
                av = num.get(anchor_name)
                if av is None:
                    continue
                if str(av) not in me:
                    msgs.append(_detail_gap(f"marketEnvironment 数值锚 {anchor_name}={av} 未出现"))
    mg_cfg = sf_cfg.get("margin")
    if isinstance(mg_cfg, dict):
        mg_mod = modules.get("margin") or {}
        mseg = mod.get("margin") or ""
        if isinstance(mg_mod, dict):
            mg_status = mg_mod.get("status")
            if mg_status == "FINAL":
                change = mg_mod.get("marginBalanceChange")
                if _is_finite_number(change):
                    if float(change) < 0:
                        words = mg_cfg.get("negativeWords", ["减少", "下降", "回落", "减仓", "净偿还"])
                        if not any(w in mseg for w in words):
                            msgs.append(_detail_gap(f"margin FINAL marginBalanceChange<0 但 margin 段未含下降词 {words}"))
                    elif float(change) > 0:
                        words = mg_cfg.get("positiveWords", ["增加", "上升", "净买入"])
                        if not any(w in mseg for w in words):
                            msgs.append(_detail_gap(f"margin FINAL marginBalanceChange>0 但 margin 段未含上升词 {words}"))
            elif mg_status == "PENDING":
                words = mg_cfg.get("pendingWords", ["待披露", "待次日", "暂缺", "参考", "T+1"])
                if not any(w in mseg for w in words):
                    msgs.append(_detail_gap(f"margin PENDING 但 margin 段未含待披露词 {words}"))
    nb_cfg = sf_cfg.get("northbound")
    if isinstance(nb_cfg, dict):
        nb_mod = modules.get("northbound") or {}
        nbseg = mod.get("northbound") or ""
        if isinstance(nb_mod, dict):
            legacy = nb_mod.get("legacyImportedFields")
            if isinstance(legacy, dict):
                tin = legacy.get("totalNetInflow")
                if _is_finite_number(tin) and float(tin) < 0 and (nb_cfg.get("outflowWord") not in nbseg):
                    msgs.append(_detail_gap("northbound totalNetInflow<0 但 northbound 段未含净流出"))
                elif _is_finite_number(tin) and float(tin) > 0 and (nb_cfg.get("inflowWord") not in nbseg):
                    msgs.append(_detail_gap("northbound totalNetInflow>0 但 northbound 段未含净流入"))
            mode = nb_mod.get("mode") or ""
            if "OFFICIAL_REPLACEMENT" in mode:
                # P0-007/评审：OFFICIAL 组合约束——每组词至少命中一个（停发语义 + 季度/PIT 语义），
                # 且禁止虚构"官方日度净流入"类相反断言。
                groups = nb_cfg.get("mustContainAnyGroups") or []
                for g in groups:
                    words = g if isinstance(g, list) else [g]
                    if not any(w in nbseg for w in words):
                        msgs.append(_detail_gap(f"northbound OFFICIAL 但 northbound 段未含任一词 {words}"))
                for w in nb_cfg.get("mustNotContain", []):
                    if w and w in nbseg:
                        msgs.append(_detail_gap(f"northbound OFFICIAL 但 northbound 段含禁词 {w!r}"))
    tc_cfg = sf_cfg.get("trackConclusion")
    if isinstance(tc_cfg, dict):
        trackmod = modules.get("tracks") or {}
        concl = mod.get("trackConclusion") or ""
        if isinstance(trackmod, dict) and trackmod.get("status") == "FINAL"                 and isinstance(trackmod.get("items"), list) and len(trackmod["items"]) >= 4:
            track_names = [it.get("trackName") for it in trackmod["items"] if isinstance(it, dict)]
            frags = []
            for tn in track_names:
                if not isinstance(tn, str):
                    continue
                core = re.split(r"[（(]", tn)[0].strip()
                frag = core[:2] if len(core) >= 2 else core
                frags.append(frag)
            missing_frag = [f for f in frags if f and f not in concl]
            if missing_frag:
                msgs.append(_detail_gap(f"trackConclusion 未覆盖全部赛道前2字子串，缺 {missing_frag}"))
            decs = [str(it.get("decision")) for it in trackmod["items"] if isinstance(it, dict) and it.get("decision")]
            mention_count = sum(1 for d in dict.fromkeys(decs) if d and d in concl)
            if mention_count < 2:
                msgs.append(_detail_gap(f"trackConclusion 需至少提及 2 条赛道判定字符串，实际 {mention_count}"))
    return msgs


def check_summary(snapshot, standard=None, trade_date=None, manifest=None, daily_dir=None, ctx=None):
    standard = standard if standard is not None else _load_standard()
    mod = _module(snapshot, "summary")
    status = mod.get("status")
    details = []
    spec = _lookup_module(standard, "summary")
    rule = spec.get("ruleId") or "summary_V2"
    if spec.get("requiredStatus") and status != spec.get("requiredStatus"):
        details.append(_detail_gap(f"status={status!r} 期望 {spec.get('requiredStatus')}"))

    # P0-002：复杂 handler 开头统一消费标准 fields（8 段 string/minChars/cjk）。
    details.extend(_validate_field_values(mod, spec.get("fields", [])))

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

    # P0-007（summaryFacts 驱动）：若标准声明 summary.summaryFacts 机读配置则按配置执行事实锚点；
    # 否则回退既有硬编码事实锚点（向后兼容）。summaryFacts 缺失时保持旧逻辑不变。
    modules = snapshot.get("modules") or {}
    summary_facts = spec.get("summaryFacts")
    if isinstance(summary_facts, dict):
        details.extend(_run_summary_facts(summary_facts, mod, snapshot, standard))
    else:
        # marketEnvironment <-> turnover
        to_mod = modules.get("turnover") or {}
        me = mod.get("marketEnvironment") or ""
        if isinstance(to_mod, dict) and to_mod.get("comparisonStatus") == "COMPARABLE":
            no_words = ["暂无", "不可比", "无可比较"]
            for w in no_words:
                if w in me:
                    details.append(_detail_gap(
                        f"turnover COMPARABLE 但 marketEnvironment 含 {w!r}（应为可比文案）"))
                    all_ok = False
            vs = to_mod.get("volumeState")
            want = {"EXPANSION": "放量", "CONTRACTION": "缩量", "FLAT": "平量"}.get(vs)
            if want and want not in me:
                details.append(_detail_gap(
                    f"turnover volumeState={vs} 但 marketEnvironment 未提及 {want!r}"))
                all_ok = False

        # trackConclusion <-> tracks（FINAL 且 items>=4）
        trackmod = modules.get("tracks") or {}
        concl = mod.get("trackConclusion") or ""
        if isinstance(trackmod, dict) and trackmod.get("status") == "FINAL"             and isinstance(trackmod.get("items"), list) and len(trackmod["items"]) >= 4:
            track_names = [it.get("trackName") for it in trackmod["items"] if isinstance(it, dict)]
            # 每个 item 取 trackName 去除括号部分后的前 2 字符子串，逐一要求出现在 trackConclusion。
            frags = []
            for tn in track_names:
                if not isinstance(tn, str):
                    continue
                core = re.split(r"[（(]", tn)[0].strip()
                frag = core[:2] if len(core) >= 2 else core
                frags.append(frag)
            missing_frag = [f for f in frags if f and f not in concl]
            if missing_frag:
                details.append(_detail_gap(
                    f"trackConclusion 未覆盖全部赛道前2字子串，缺 {missing_frag}"))
                all_ok = False
            # 判定字符串（decision 值）至少出现 2 个
            decs = [str(it.get("decision")) for it in trackmod["items"] if isinstance(it, dict) and it.get("decision")]
            mention_count = sum(1 for d in dict.fromkeys(decs) if d and d in concl)
            if mention_count < 2:
                details.append(_detail_gap(
                    f"trackConclusion 需至少提及 2 条赛道判定字符串，实际 {mention_count}"))
                all_ok = False

        # margin段 <-> margin
        mg_mod = modules.get("margin") or {}
        mseg = mod.get("margin") or ""
        if isinstance(mg_mod, dict):
            mg_status = mg_mod.get("status")
            if mg_status == "FINAL":
                if not any(w in mseg for w in ("融资", "两融")):
                    details.append(_detail_gap("margin FINAL 但 margin 段未含『融资/两融』"))
                    all_ok = False
            elif mg_status == "PENDING":
                if not any(w in mseg for w in ("待披露", "未披露", "参考", "T+1")):
                    details.append(_detail_gap("margin PENDING 但 margin 段未含『待披露/未披露/参考/T+1』"))
                    all_ok = False

        # northbound段 <-> northbound
        nb_mod = modules.get("northbound") or {}
        nbseg = mod.get("northbound") or ""
        if isinstance(nb_mod, dict):
            nb_mode = nb_mod.get("mode")
            if nb_mode == "POST_20240819_LEGACY_IMPORTED"                 and nb_mod.get("status") == "FINAL":
                if "北向" not in nbseg:
                    details.append(_detail_gap("northbound legacy FINAL 但 northbound 段未含『北向』"))
                    all_ok = False
                if not any(w in nbseg for w in ("净流入", "净流出")):
                    details.append(_detail_gap("northbound legacy FINAL 但 northbound 段未含『净流入/净流出』"))
                    all_ok = False
            elif nb_mode == "POST_20240819_OFFICIAL_REPLACEMENT":
                if not any(w in nbseg for w in ("停发", "季度", "披露", "不再")):
                    details.append(_detail_gap("northbound OFFICIAL 但 northbound 段未含『停发/季度/披露/不再』"))
                    all_ok = False

    # 存在任一模块 status 非 FINAL 时，summary 至少一段含缺口词
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

    # 参考日 summary referenceAssertions（segmentCount / riskWarningMustContain）逐条执行（P0-001）。
    details.extend(_run_reference_assertions(snapshot, standard, "summary", trade_date, daily_dir, ctx))

    ok = not any(not d["passed"] for d in details)
    if ok and not details:
        details.append(_detail_ok(f"{rule}: 8 段中文摘要 + 风险提示 + 依赖完整性通过"))
    return _result(rule, ok, details, status)


# ---------------------------------------------------------------- referenceAssertions


def _count_assertion_leaves(node):
    """统计 referenceAssertions 展开后的叶子断言条目数（P0-001 coverage）。

    规则：dict 的叶子=对每个值递归；list 的每项每个字段=叶子；标量=1。
    因此一个 {name:{close,changePct}} 会产生 2*len 条叶子；一个
    {list:[{f1,f2},...]} 的叶子数 = sum(每项字段数)。
    """
    if isinstance(node, dict):
        return sum(_count_assertion_leaves(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_assertion_leaves(item) for item in node)
    return 1


def _run_reference_assertions(snapshot, standard, module_name, trade_date, daily_dir, ctx):
    """参考日逐条精确断言：fail-closed 全量消费 + 覆盖率自检（P0-001）。

    每个 expected 的 name/key/item 字段都必须被实际比对：缺失即 _detail_gap（禁止 continue 跳过）。
    返回 detail 列表（不匹配则 fail）。非参考日返回 []。

    ctx 可选：若提供 dict，则把该模块的 (declared, consumed) 写入
    ctx["assertion_coverage"][module_name] 供参考日聚合统计。
    """
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
        msgs, consumed = _ref_match_items_by_name(mod, expected, "close", "changePct", "items")
    elif module_name == "turnover":
        msgs, consumed = _ref_match_fields(mod, expected)
    elif module_name == "sentiment":
        msgs, consumed = _ref_match_fields(mod, expected)
    elif module_name in ("sectorPerformance", "fundFlow"):
        msgs, consumed = _ref_match_lists(mod, expected)
    elif module_name == "northbound":
        msgs, consumed = _ref_match_northbound(mod, expected)
    elif module_name == "margin":
        msgs, consumed = _ref_match_fields(mod, expected)
    elif module_name == "tracks":
        msgs, consumed = _ref_match_tracks(mod, expected)
    elif module_name == "summary":
        msgs, consumed = _ref_match_summary(mod, expected, standard)
    else:
        return []

    declared = _count_assertion_leaves(expected)
    consumed = consumed if isinstance(consumed, set) else set(consumed)
    if declared != len(consumed):
        msgs.append(_detail_gap(
            f"assertion coverage declared={declared} consumed={len(consumed)}（存在未消费的参考断言）"))
    if ctx is not None:
        ctx.setdefault("assertion_coverage", {})[module_name] = (declared, len(consumed))
    return msgs


def _ref_match_fields(mod, expected, numeric_fields_without_change=()):
    """字段级精确匹配（P0-001 fail-closed）。返回 (msgs, consumed_paths)。"""
    msgs = []
    consumed = set()
    for field, exp in expected.items():
        consumed.add(f"f.{field}")
        if field in numeric_fields_without_change:
            # 已由 marginBalanceChange 环比校验，此处仅确保存在
            if field not in mod:
                msgs.append(_detail_gap(f"referenceAssertion[{field}] 缺失"))
            continue
        actual = mod.get(field)
        if (
            _is_number(exp)
            and isinstance(actual, dict)
            and "value" in actual
        ):
            # 嵌套质量对象（如 {"value": -450.0, "quality": "LEGACY"}）取 value 比对
            actual = actual["value"]
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
    return msgs, consumed


def _ref_match_items_by_name(mod, expected, num_field, pct_field, items_key):
    """按 name 匹配 items（P0-001 fail-closed）。expected 每个 name 都必须存在。返回 (msgs, consumed)。"""
    items = mod.get(items_key) or []
    msgs = []
    consumed = set()
    by_name = {}
    for it in items:
        if isinstance(it, dict):
            by_name[str(it.get("name"))] = it
    for name, exp in expected.items():
        actual = by_name.get(name)
        if actual is None:
            # fail-closed：期望名称缺失即 FAIL，禁止 continue 跳过。
            msgs.append(_detail_gap(f"referenceAssertion 缺期望项 {name!r}"))
            # 该 name 下所有声明字段仍作为“已消费未命中”计入 consumed，保证 coverage 自检只盯消费不足。
            for fn in (num_field, pct_field):
                if fn in exp:
                    consumed.add(f"it.{name}.{fn}")
            continue
        for fn in (num_field, pct_field):
            if fn not in exp:
                continue
            consumed.add(f"it.{name}.{fn}")
            e = exp[fn]
            a = actual.get(fn)
            if _is_number(e):
                if not _is_finite_number(a):
                    msgs.append(_detail_gap(
                        f"referenceAssertion[{name}.{fn}] 期望数值 {e}，实际 {a!r}"))
                elif abs(float(a) - float(e)) > 0.01:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[{name}.{fn}] 期望 {e}，实际 {float(a):.2f}"))
    return msgs, consumed


def _ref_match_lists(mod, expected):
    """列表逐项 + 每项字段精确匹配（P0-001 fail-closed）。返回 (msgs, consumed)。"""
    msgs = []
    consumed = set()
    for list_name, exp_items in expected.items():
        actual = mod.get(list_name)
        if not isinstance(actual, list):
            msgs.append(_detail_gap(f"referenceAssertion[{list_name}] 非 list"))
            for i, eitem in enumerate(exp_items or []):
                if isinstance(eitem, dict):
                    for k in eitem:
                        consumed.add(f"list.{list_name}.{i}.{k}")
            continue
        if len(actual) != len(exp_items):
            msgs.append(_detail_gap(
                f"referenceAssertion[{list_name}] 长度 {len(actual)} 期望 {len(exp_items)}"))
        for i, (eitem, aitem) in enumerate(zip(exp_items, actual)):
            if not isinstance(eitem, dict):
                mg = _detail_gap(f"referenceAssertion[{list_name}][{i}] 期望对象")
                if mg not in msgs:
                    msgs.append(mg)
                continue
            if not isinstance(aitem, dict):
                msgs.append(_detail_gap(f"referenceAssertion[{list_name}][{i}] 实际非对象"))
                for k in eitem:
                    consumed.add(f"list.{list_name}.{i}.{k}")
                continue
            for k, ev in eitem.items():
                consumed.add(f"list.{list_name}.{i}.{k}")
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
                else:
                    if av != ev:
                        msgs.append(_detail_gap(
                            f"referenceAssertion[{list_name}][{i}].{k}] 期望 {ev!r} 实际 {av!r}"))
    return msgs, consumed


def _ref_match_northbound(mod, expected):
    """northbound 参考金标：三净流入标量 + netBuyTop10/netSellTop10 列表逐项（P0-001 全量消费）。返回 (msgs, consumed)。"""
    msgs = []
    consumed = set()
    # 三净流入标量（legacyImportedFields）与 netBuyTop10/netSellTop10 列表逐项比较。
    legacy = mod.get("legacyImportedFields")
    if not isinstance(legacy, dict):
        for fn in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow"):
            if fn in expected:
                consumed.add(f"northbound.{fn}")
        msgs.append(_detail_gap("referenceAssertion[northbound] legacyImportedFields 非 dict"))
    else:
        for fn in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow"):
            if fn not in expected:
                continue
            consumed.add(f"northbound.{fn}")
            e = expected[fn]
            a = legacy.get(fn)
            if _is_number(e):
                if not _is_finite_number(a):
                    msgs.append(_detail_gap(
                        f"referenceAssertion[northbound.{fn}] 期望数值 {e} 实际 {a!r}"))
                elif abs(float(a) - float(e)) > 0.01:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[northbound.{fn}] 期望 {e} 实际 {float(a):.2f}"))
    # legacy netBuyTop10/netSellTop10 逐项比较（消费 expected 中声明的这些列表）。
    for lname in ("netBuyTop10", "netSellTop10"):
        if lname not in expected:
            continue
        exp_items = expected[lname]
        actual = legacy.get(lname) if isinstance(legacy, dict) else None
        if not isinstance(actual, list):
            msgs.append(_detail_gap(f"referenceAssertion[northbound.{lname}] 非 list"))
            for i, eitem in enumerate(exp_items or []):
                if isinstance(eitem, dict):
                    for k in eitem:
                        consumed.add(f"northbound.{lname}.{i}.{k}")
            continue
        if len(actual) != len(exp_items):
            msgs.append(_detail_gap(
                f"referenceAssertion[northbound.{lname}] 长度 {len(actual)} 期望 {len(exp_items)}"))
        for i, (eitem, aitem) in enumerate(zip(exp_items, actual)):
            if not isinstance(eitem, dict):
                continue
            if not isinstance(aitem, dict):
                msgs.append(_detail_gap(f"referenceAssertion[northbound.{lname}][{i}] 实际非对象"))
                for k in eitem:
                    consumed.add(f"northbound.{lname}.{i}.{k}")
                continue
            for k, ev in eitem.items():
                consumed.add(f"northbound.{lname}.{i}.{k}")
                av = aitem.get(k)
                if _is_number(ev):
                    if not _is_finite_number(av):
                        msgs.append(_detail_gap(
                            f"referenceAssertion[northbound.{lname}][{i}].{k}] 期望 {ev} 实际 {av!r}"))
                    elif abs(float(av) - float(ev)) > 0.01:
                        msgs.append(_detail_gap(
                            f"referenceAssertion[northbound.{lname}][{i}].{k}] 期望 {ev} 实际 {float(av):.2f}"))
                elif isinstance(ev, str):
                    if str(av) != ev:
                        msgs.append(_detail_gap(
                            f"referenceAssertion[northbound.{lname}][{i}].{k}] 期望 {ev!r} 实际 {av!r}"))
    return msgs, consumed


def _ref_match_tracks(mod, expected):
    """tracks 参考金标：按 trackId 逐项、每列精确匹配 + fail-closed。返回 (msgs, consumed)。"""
    items = mod.get("items") or []
    msgs = []
    consumed = set()
    by_id = {}
    for it in items:
        if isinstance(it, dict) and it.get("trackId") is not None:
            by_id[it["trackId"]] = it
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
    for track_id, exp in expected.items():
        actual = by_id.get(track_id)
        if actual is None:
            msgs.append(_detail_gap(f"referenceAssertion[tracks] 缺赛道 {track_id!r}"))
            for exp_key in exp:
                consumed.add(f"tracks.{track_id}.{exp_key}")
            continue
        if not isinstance(exp, dict):
            msgs.append(_detail_gap(f"referenceAssertion[tracks.{track_id}] 期望非对象"))
            consumed.add(f"tracks.{track_id}")
            continue
        for exp_key, exp_val in exp.items():
            consumed.add(f"tracks.{track_id}.{exp_key}")
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
            else:
                if av != exp_val:
                    msgs.append(_detail_gap(
                        f"referenceAssertion[tracks.{track_id}.{exp_key}] 期望 {exp_val!r} 实际 {av!r}"))
    return msgs, consumed


def _ref_match_summary(mod, expected, standard):
    """summary 参考金标：segmentCount=8 段齐全 + riskWarningMustContain 子串（P0-001）。
    返回 (msgs, consumed)。其余标准声明的 summary 断言逐条执行。"""
    msgs = []
    consumed = set()
    if not isinstance(expected, dict):
        msgs.append(_detail_gap("referenceAssertion[summary] 期望非对象"))
        return msgs, {"summary"}
    seg = expected.get("segmentCount")
    if seg is not None:
        consumed.add("summary.segmentCount")
        seg_spec = _lookup_module(standard, "summary").get("fields", [])
        seg_names = [f.get("name") for f in seg_spec if f.get("required")]
        present = sum(
            1 for fn in seg_names
            if isinstance(mod.get(fn), str) and mod.get(fn).strip()
        )
        if present != seg:
            msgs.append(_detail_gap(
                f"summary segmentCount 期望 {seg} 实际 {present}（segmentCount 语义=必需段齐全数）"))
    rw = expected.get("riskWarningMustContain")
    if rw is not None:
        consumed.add("summary.riskWarningMustContain")
        rw_val = mod.get("riskWarning") or ""
        if not isinstance(rw, str) or rw not in rw_val:
            msgs.append(_detail_gap(
                f"summary.riskWarning 需包含 {rw!r}，实际 {rw_val!r}"))
    # 其余标准声明的 summary 断言：*MustContain（子串）/ *MustNotContain（禁词表）
    # 通用执行；*Reason 为文档性说明（consumed 但无检查）；未知键 fail-closed。
    handled = {"segmentCount", "riskWarningMustContain"}
    for k, ev in expected.items():
        if k in handled:
            continue
        if k.endswith("Reason"):
            consumed.add(f"summary.{k}")  # 文档性说明：consumed 但无检查
            continue
        if k.endswith("MustContain"):
            consumed.add(f"summary.{k}")
            section = k[: -len("MustContain")]
            text = str(mod.get(section) or "")
            want = ev if isinstance(ev, str) else ""
            if not want or want not in text:
                msgs.append(_detail_gap(
                    f"summary.{section} 需包含 {want!r}，实际 {text[:80]!r}"))
        elif k.endswith("MustNotContain"):
            section = k[: -len("MustNotContain")]
            text = str(mod.get(section) or "")
            words = ev if isinstance(ev, list) else [ev]
            bad = [w for w in words if isinstance(w, str) and w in text]
            if bad:
                msgs.append(_detail_gap(
                    f"summary.{section} 不得含 {bad!r}，实际 {text[:80]!r}"))
            # 叶子粒度与 _count_assertion_leaves 对齐：list 的每个词各计 1 条
            for _i in range(len(words)):
                consumed.add(f"summary.{k}[{_i}]")
        else:
            consumed.add(f"summary.{k}")
            msgs.append(_detail_gap(f"未识别的 summary 参考断言 {k!r}"))
    return msgs, consumed


# ---------------------------------------------------------------- crossModuleInvariants


def _check_date_le(trade_date, path, value, details):
    """若 value 是 ISO 日期字符串且晚于 tradeDate，追加 look-ahead gap 并返回 False。"""
    if value is None:
        return True
    tr = _parse_iso_date_strict(trade_date) if isinstance(trade_date, str) else None
    v = _parse_iso_date_strict(value) if isinstance(value, str) else None
    if tr is None or v is None:
        return True
    if v > tr:
        details.append(_detail_gap(f"INV-DATE-LOOKAHEAD: {path}={value} 晚于 tradeDate {trade_date}"))
        return False
    return True



def _invariant_spec(standard, inv_id):
    """按 id 取标准 crossModuleInvariants 的 spec 对象（P0-008 各 invariant 直接消费其 spec/config）。"""
    for inv in standard.get("crossModuleInvariants") or []:
        if isinstance(inv, dict) and inv.get("id") == inv_id:
            return inv.get("spec") or {}
    return {}


def run_cross_module_invariants(snapshot, standard, trade_date, daily_dir=None):
    """9 条跨模块不变式一一实现（按 id），全部产出 results key（P0-008）。返回 (inv_results, detail_msgs)。"""
    daily_dir = daily_dir or DAILY_DIR
    modules = snapshot.get("modules") or {}
    ref_date = standard.get("referenceDate")
    details = []
    results = {}

    # INV-DATE-LOOKAHEAD：递归扫描顶层 dataDate/asOf/publishedAt，以及
    # tracks.items.date、margin.latestPublishedReference.dataDate、northbound.quarterlyHolding.asOf/publishedAt。
    b = True
    for mname, m in modules.items():
        if not isinstance(m, dict):
            continue
        for fn in ("dataDate", "asOf", "publishedAt"):
            if not _check_date_le(trade_date, f"{mname}.{fn}", m.get(fn), details):
                b = False
        if mname == "margin":
            ref = m.get("latestPublishedReference")
            if isinstance(ref, dict):
                if not _check_date_le(trade_date, "margin.latestPublishedReference.dataDate", ref.get("dataDate"), details):
                    b = False
        if mname == "tracks":
            for it in (m.get("items") or []):
                if isinstance(it, dict):
                    if not _check_date_le(trade_date, "tracks.items.date", it.get("date"), details):
                        b = False
        if mname == "northbound":
            qh = m.get("quarterlyHolding")
            if isinstance(qh, dict):
                if not _check_date_le(trade_date, "northbound.quarterlyHolding.asOf", qh.get("asOf"), details):
                    b = False
                if not _check_date_le(trade_date, "northbound.quarterlyHolding.publishedAt", qh.get("publishedAt"), details):
                    b = False
    results["INV-DATE-LOOKAHEAD"] = b

    # INV-UNIT-亿元（P0-008-A）：读标准 spec.modules 清单；对清单内每个模块若其标准 fields 声明了 required 的
    # unit 字段，则该模块 unit 缺失或 !=亿元 即 false（unit 缺失不再放行）。未声明 unit 的模块不要求。
    unit_spec = _invariant_spec(standard, "INV-UNIT-亿元")
    unit_modules = unit_spec.get("modules") or []
    b = True
    for mname in unit_modules:
        m = modules.get(mname) or {}
        mod_fields = _lookup_module(standard, mname).get("fields") or []
        declared_unit = None
        for f in mod_fields:
            if f.get("name") == "unit" and f.get("required"):
                declared_unit = f
                break
        if declared_unit is None:
            continue
        u = m.get("unit") if isinstance(m, dict) else None
        if u is None or u != "亿元":
            b = False
            details.append(_detail_gap(f"INV-UNIT-亿元: {mname}.unit 缺失或非亿元: {u!r}"))
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

    # INV-MARGIN-IDENTITY（P0-008-D）：读标准 spec.changeIdentity/changeTolerance/referenceDateExemption。
    # 恒等(tol 0.05) + change 环比；参考日且 referenceDateExemption=true 时环比由 INV-REF-EXACT 兜底跳过；
    # 否则前一 FINAL margin 缺失 -> false（不再 note 放行）。
    mg_id_spec = _invariant_spec(standard, "INV-MARGIN-IDENTITY")
    mg = modules.get("margin") or {}
    b = True
    if isinstance(mg, dict) and mg.get("status") == "FINAL":
        fin, sec, bal = mg.get("financingBalance"), mg.get("securitiesLendingBalance"), mg.get("marginBalance")
        if all(_is_finite_number(v) for v in (fin, sec, bal)):
            if abs(float(bal) - (float(fin) + float(sec))) > 0.05:
                b = False
        change = mg.get("marginBalanceChange")
        if _is_finite_number(change):
            if trade_date == ref_date and mg_id_spec.get("referenceDateExemption"):
                pass  # 参考日以 referenceAssertions(INV-REF-EXACT) 为金标，环比兜底由其校验
            else:
                prev_bal = _prev_trading_day_margin_balance(trade_date, daily_dir)
                if prev_bal is None:
                    b = False
                    details.append(_detail_gap("INV-MARGIN-IDENTITY: 前一 FINAL margin 缺失，环比无法校验"))
                else:
                    tol = mg_id_spec.get("changeTolerance", 0.01)
                    if abs(float(change) - (float(bal) - prev_bal)) > tol:
                        b = False
                        details.append(_detail_gap(
                            f"INV-MARGIN-IDENTITY: change 环比差异 |{change} - {float(bal)-prev_bal:.2f}|>{tol}"))
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

    # INV-SENTIMENT-WIDTH（P0-008-B）：status==FINAL 时 spec.fields 三字段任一缺失/非有限 -> false（不只检查 sum），
    # 且 sum>=sumMin。
    se_w_spec = _invariant_spec(standard, "INV-SENTIMENT-WIDTH")
    se_fields = se_w_spec.get("fields") or ["riseCount", "fallCount", "flatCount"]
    se = modules.get("sentiment") or {}
    b = True
    if isinstance(se, dict):
        req_status = spec_required_status(standard, "sentiment")
        if se.get("status") == req_status:
            vals = [se.get(k) for k in se_fields]
            if not all(_is_finite_number(v) for v in vals):
                b = False
                details.append(_detail_gap("INV-SENTIMENT-WIDTH: sentiment 三计数任一缺失/非有限"))
            elif float(vals[0]) + float(vals[1]) + float(vals[2]) < (se_w_spec.get("sumMin") or 4000):
                b = False
                details.append(_detail_gap("INV-SENTIMENT-WIDTH: rise+fall+flat < sumMin"))
    results["INV-SENTIMENT-WIDTH"] = b

    # INV-ENUM-SOURCE-METHOD（P0-008-C）：直接读标准 spec.allowedEnums——路径格式 "<模块>.<顶层字段>" 与
    # tracks 的 item 字段 "<模块>.items.<字段>"（maAlignment/excessReturn20d/decision）。值缺失时仅当该字段
    # required（标准 fields/items.fields required=true）才 false；值存在但不在枚举即 false。未声明路径不检查。
    en_cfg = _invariant_spec(standard, "INV-ENUM-SOURCE-METHOD").get("allowedEnums") or {}
    # P1-002：状态作用域由 spec.applyWhenStatus 声明（machine-readable），
    # 执行器不再硬编码 FINAL；标准未声明时退化为仅 FINAL（与 P1-001 行为一致）。
    apply_when = _invariant_spec(standard, "INV-ENUM-SOURCE-METHOD").get("applyWhenStatus") or ["FINAL"]
    b = True
    for mname, field_enums in en_cfg.items():
        m = modules.get(mname) or {}
        # 模块 status 不在 spec 声明的作用域内 → fail-closed 语义下数据缺失是预期，
        # 枚举必填检查不应触发。
        if not isinstance(m, dict) or m.get("status") not in apply_when:
            continue
        for fpath, enum_vals in field_enums.items():
            if fpath.startswith("items."):
                fname = fpath[len("items."):]
                mi_fields = (_lookup_module(standard, mname).get("items") or {}).get("fields") or []
                item_req = False
                for f in mi_fields:
                    if f.get("name") == fname:
                        item_req = bool(f.get("required"))
                        break
                items = m.get("items") if isinstance(m, dict) else None
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    v = it.get(fname)
                    if v is None:
                        if item_req:
                            b = False
                            details.append(_detail_gap(f"INV-ENUM-SOURCE-METHOD: {mname}.items.{fname} 缺失(required)"))
                        continue
                    if v not in enum_vals:
                        b = False
                        details.append(_detail_gap(f"INV-ENUM-SOURCE-METHOD: {mname}.items.{fname}={v!r} 不在枚举 {enum_vals}"))
            else:
                mod_fields = _lookup_module(standard, mname).get("fields") or []
                req = False
                for f in mod_fields:
                    if f.get("name") == fpath:
                        req = bool(f.get("required"))
                        break
                v = m.get(fpath) if isinstance(m, dict) else None
                if v is None:
                    if req:
                        b = False
                        details.append(_detail_gap(f"INV-ENUM-SOURCE-METHOD: {mname}.{fpath} 缺失(required)"))
                    continue
                # source 等多值字段以字符串数组存储时逐项校验；标量直接比对。
                values = v if isinstance(v, list) and all(isinstance(x, str) for x in v) else [v]
                bad = [x for x in values if x not in enum_vals]
                if bad:
                    b = False
                    details.append(_detail_gap(f"INV-ENUM-SOURCE-METHOD: {mname}.{fpath}={v!r} 含不在枚举的值 {bad}"))
    results["INV-ENUM-SOURCE-METHOD"] = b

    # INV-REF-EXACT：参考日精确断言
    b = True
    if trade_date == ref_date:
        ra = standard.get("referenceAssertions") or {}
        day = ra.get(ref_date) or {}
        from_fields = check_reference_modules(snapshot, standard, trade_date, daily_dir)
        if from_fields:
            b = False
    results["INV-REF-EXACT"] = b

    # INV-NORTHBOUND-PIT：OFFICIAL 分支点时间强制（asOf/publishedAt 必存在、可解析、<=tradeDate）。
    nb2 = modules.get("northbound") or {}
    b = True
    if isinstance(nb2, dict) and nb2.get("mode") == "POST_20240819_OFFICIAL_REPLACEMENT":
        qh = nb2.get("quarterlyHolding")
        if not isinstance(qh, dict):
            details.append(_detail_gap("INV-NORTHBOUND-PIT: OFFICIAL 分支需 quarterlyHolding 为 dict"))
            b = False
        else:
            for fn in ("asOf", "publishedAt"):
                v = qh.get(fn)
                vparsed = _parse_iso_date_strict(v) if isinstance(v, str) else None
                if v is None or v == "" or vparsed is None:
                    details.append(_detail_gap(f"INV-NORTHBOUND-PIT: quarterlyHolding.{fn} 缺失/不可解析: {v!r}"))
                    b = False
                elif not _check_date_le(trade_date, f"northbound.quarterlyHolding.{fn}", v, details):
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
    """P0-002 自检（fail-closed 路由契约）+ P0-008 invariant 集合相等。

    1) version==2；9 模块 ruleId 均在 dispatch 表（复杂 handler 或通用引擎）。
    2) 复杂 handler 按标准 ruleVersion 绑定：ruleVersion 不在 supportedVersions -> 失败（退出码 3）。
    3) 标准 crossModuleInvariants id 集合 == 代码 _INVARIANT_IDS 集合。
    """
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
        rule_id = spec.get("ruleId")
        rule_version = spec.get("ruleVersion")
        if not rule_id:
            errors.append(f"模块 {name} 缺 ruleId")
            continue
        if not rule_version:
            errors.append(f"模块 {name} 缺 ruleVersion")
        if rule_id in _COMPLEX_HANDLERS:
            entry = _COMPLEX_HANDLERS[rule_id]
            handler_name = entry["handler"]
            if not callable(globals().get(handler_name)):
                errors.append(f"handler {handler_name!r} (ruleId={rule_id}) 未实现")
            supported = entry.get("supportedVersions") or []
            if int(rule_version) not in supported:
                errors.append(
                    f"模块 {name} ruleId={rule_id} ruleVersion={rule_version} 不受支持 {supported}")
        elif rule_id in _GENERIC_HANDLERS:
            # P0-002-A：通用引擎同样校验 ruleVersion 是否在 supportedVersions（不在 -> errors -> 退出码 3）。
            gen_entry = _GENERIC_HANDLERS[rule_id]
            gen_handler = gen_entry.get("handler")
            gfn = globals().get(gen_handler)
            if not callable(gfn):
                errors.append(f"通用引擎 handler {gen_handler!r} (ruleId={rule_id}) 未实现")
            gen_supported = gen_entry.get("supportedVersions") or []
            if int(rule_version) not in gen_supported:
                errors.append(
                    f"模块 {name} ruleId={rule_id} ruleVersion={rule_version} 不受通用引擎支持 {gen_supported}")
        else:
            errors.append(f"模块 {name} ruleId={rule_id} 不在 dispatch 表（未知规则）")
    # invariant id 集合相等：标准声明的 crossModuleInvariants.id == 代码 _INVARIANT_IDS。
    std_inv = set()
    for inv in standard.get("crossModuleInvariants") or []:
        if isinstance(inv, dict) and inv.get("id"):
            std_inv.add(inv["id"])
    if std_inv != set(_INVARIANT_IDS):
        errors.append(
            f"invariant 集合不等: 标准 {sorted(std_inv)} vs 代码 {sorted(_INVARIANT_IDS)}")
    return errors


MODULE_ORDER = [
    "marketIndex", "turnover", "sentiment", "sectorPerformance",
    "fundFlow", "northbound", "margin", "tracks", "summary",
]

# 通用引擎 handler：标准声明了 ruleId 但无复杂 handler 的模块走字段/items/lists 通用校验。
_GENERIC_HANDLERS = {
    # P0-002-A：通用引擎同样做 ruleId -> {supportedVersions, handler} 版本绑定。
    "marketIndex_V2": {"supportedVersions": [2], "handler": "check_marketindex"},
    "sectorPerformance_V2": {"supportedVersions": [1], "handler": "check_sectors"},
    "fundFlow_V2": {"supportedVersions": [1], "handler": "check_fundflow"},
}


def _build_checkers(standard):
    """由 dispatch 表（复杂 handler + 通用引擎）构造 模块名 -> handler 校验函数，无硬编码旁路。"""
    out = {}
    for name, spec in (standard.get("modules") or {}).items():
        rule_id = spec.get("ruleId")
        entry = _COMPLEX_HANDLERS.get(rule_id)
        if entry:
            fn = globals().get(entry["handler"])
            out[name] = fn
        elif rule_id in _GENERIC_HANDLERS:
            out[name] = globals().get(_GENERIC_HANDLERS[rule_id].get("handler"))
        else:
            out[name] = None  # startup_self_check 已拦截。
    return out


# 兼容接口：以默认标准构造全局 CHECKERS（供外围直接引用）；evaluate_modules 每轮用实际 standard 重新构造。
def _default_checkers():
    try:
        return _build_checkers(_load_standard())
    except Exception:  # noqa: BLE001
        return {}


CHECKERS = _default_checkers()


# ---------------------------------------------------------------- 主流程


def evaluate_modules(snapshot, standard, trade_date, manifest, daily_dir=None, ctx=None):
    """对单个快照执行 9 模块验收。返回 (modules_out, all_pass)。"""
    ctx = ctx or {}
    ctx["manifest"] = manifest
    checkers = _build_checkers(standard)
    checks = {
        m: checkers[m](snapshot, standard=standard, trade_date=trade_date,
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


def _validate_manifest_latest_identity(manifest, daily_dir=None):
    """校验 manifest/latest/daily 顶层身份闭合（R13-P3-02）。

    返回 gap 字符串列表；空列表表示通过。
    """
    daily_dir = daily_dir or DAILY_DIR
    gaps = []

    if not isinstance(manifest, dict):
        return ["manifest 不是 object"]

    available = manifest.get("availableDates")
    if not isinstance(available, list) or not all(
        isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
        for v in available
    ):
        return ["manifest.availableDates 非严格 YYYY-MM-DD 字符串数组"]

    if len(available) != len(set(available)):
        gaps.append("manifest.availableDates 存在重复日期")

    if available != sorted(available):
        gaps.append("manifest.availableDates 必须按日期升序排列")

    captured = manifest.get("latestCapturedDate")
    close_complete = manifest.get("latestCloseCompleteDate")
    final = manifest.get("latestFinalDate")
    latest_alias = manifest.get("latestDate")

    if available:
        if captured != available[-1]:
            gaps.append(
                "manifest.latestCapturedDate "
                f"{captured!r} != availableDates 最大日期 {available[-1]!r}"
            )
    elif captured is not None:
        gaps.append("availableDates 为空时 latestCapturedDate 必须为 null")

    if latest_alias != captured:
        gaps.append(
            f"manifest.latestDate {latest_alias!r} "
            f"!= latestCapturedDate {captured!r}"
        )

    for name, value in (
        ("latestCapturedDate", captured),
        ("latestCloseCompleteDate", close_complete),
        ("latestFinalDate", final),
    ):
        if value is None:
            continue
        if value not in available:
            gaps.append(f"manifest.{name}={value!r} 不在 availableDates 中")

    non_null_chain = [
        value for value in (final, close_complete, captured) if value is not None
    ]
    if non_null_chain != sorted(non_null_chain):
        gaps.append(
            "manifest 三指针顺序必须满足 "
            "latestFinalDate <= latestCloseCompleteDate <= latestCapturedDate"
        )

    # R14-P3-02：指针存在性单调（阶段蕴含：FINAL ⇒ CLOSE_COMPLETE ⇒ CAPTURED）。
    # 先过滤 None 再排序会丢失蕴含关系——例如 final!=null 且
    # close_complete=null 的非法状态必须报 gap，不得放行。
    if final is not None and close_complete is None:
        gaps.append(
            "manifest.latestFinalDate 非 null 但 latestCloseCompleteDate 为 null "
            "（FINAL 隐含 CLOSE_COMPLETE，指针链断裂）"
        )
    if close_complete is not None and captured is None:
        gaps.append(
            "manifest.latestCloseCompleteDate 非 null 但 latestCapturedDate 为 null "
            "（CLOSE_COMPLETE 隐含 CAPTURED，指针链断裂）"
        )

    if captured is None:
        if os.path.exists(LATEST_PATH):
            gaps.append("latestCapturedDate=null 但 latest.json 仍存在")
        return gaps

    if not os.path.exists(LATEST_PATH):
        gaps.append(f"latest.json 缺失: {LATEST_PATH}")
        return gaps

    try:
        with open(LATEST_PATH, "r", encoding="utf-8") as fh:
            latest_snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        gaps.append(f"latest.json 无法读取/解析: {exc}")
        return gaps

    latest_trade_date = (
        latest_snapshot.get("tradeDate") if isinstance(latest_snapshot, dict) else None
    )
    if latest_trade_date != captured:
        gaps.append(
            f"latest.json.tradeDate={latest_trade_date!r} "
            f"!= manifest.latestCapturedDate={captured!r}"
        )

    daily_path = os.path.join(daily_dir, captured[:4], f"{captured}.json")
    if not os.path.exists(daily_path):
        gaps.append(f"latestCapturedDate 对应 daily 文件缺失: {daily_path}")
        return gaps

    try:
        with open(daily_path, "r", encoding="utf-8") as fh:
            daily_snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        gaps.append(f"latestCapturedDate 对应 daily 文件无法读取/解析: {exc}")
        return gaps

    daily_trade_date = (
        daily_snapshot.get("tradeDate") if isinstance(daily_snapshot, dict) else None
    )
    if daily_trade_date != captured:
        gaps.append(f"{daily_path}.tradeDate={daily_trade_date!r} != {captured!r}")

    return gaps


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
    try:
        with open(path, "r", encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        for name in MODULE_ORDER:
            modules_out[name] = _result(
                "_", False, [_detail_gap(f"FILE_INVALID: {exc}")], "_"
            )
        return {
            "gap": "FILE_INVALID",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }
    # R13-P3-02：文件名日期与快照根 tradeDate 身份必须一致
    actual_trade_date = (
        snapshot.get("tradeDate") if isinstance(snapshot, dict) else None
    )
    if actual_trade_date != trade_date:
        msg = (
            "SNAPSHOT_IDENTITY_MISMATCH: "
            f"pathDate={trade_date!r}, "
            f"snapshot.tradeDate={actual_trade_date!r}"
        )
        for name in MODULE_ORDER:
            modules_out[name] = _result("_", False, [_detail_gap(msg)], "_")
        return {
            "gap": "SNAPSHOT_IDENTITY_MISMATCH",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }
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
    # P0-009 provenance：two-commit 法（先提交输入树 A，clean 上跑，报告单独提交 B）。
    evaluated_commit = _repo_commit()
    dirty = _git_dirty()
    report = {
        "reportCommitSemantics": "two-commit：先提交输入树后运行验收，报告单独提交。evaluatedCommit=被验收输入树(HEAD)所在提交；dirty=true 表示未提交改动存在，输入树未完全固化。",
        "provenance": {
            # repoCommit 语义 = evaluatedCommit（被验收输入树所在提交）；报告自身 commit 以 external commit 记录。
            "repoCommit": evaluated_commit,
            "evaluatedCommit": evaluated_commit,
            "dirty": dirty if isinstance(dirty, bool) else False,
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
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"manifest 无法读取/解析: {exc}\n")
        sys.exit(2)

    # R13-P3-02：manifest/latest/daily 顶层身份闭合预检（退出码 4）
    identity_errors = _validate_manifest_latest_identity(manifest, DAILY_DIR)
    if identity_errors:
        for error in identity_errors:
            sys.stderr.write(f"身份自检失败: {error}\n")
        sys.exit(4)

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
