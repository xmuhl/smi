# -*- coding: utf-8 -*-
"""范本效果自动验收器（数据侧）。

对 SMI 每日快照执行基于 docs/acceptance/template-standard.json 的逐模块
数据侧自动验收，并对跨日基线给出差距报告。

CLI:
  python tools/acceptance/accept.py --date 2026-07-17
  python tools/acceptance/accept.py --all [--report work/acceptance/baseline-report.json]

验收口径（与任务规范一致）：
  - 每个日期独立判定，overall = 9 个模块全 pass 且 schemaValid -> PASS，否则 FAIL；
  - 缺失文件/规则未定义模块 -> 记 gap，且模块 fail；
  - 纯标准库实现，无第三方依赖。

产出 JSON 结构：
  {
    "generatedAt": <iso>,
    "standard": "docs/acceptance/template-standard.json",
    "dates": { <date>: { ... } },
    "summary": { "passDates": [...], "failDates": [...],
                 "moduleFailCounts": [ {"module": ..., "failDates": n}, ... ] }
  }
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime

# 项目根目录约定：脚本在 smi 目录下以相对路径运行（PYTHONPATH='.'）。
# 数据与标准文件均按项目根（当前工作目录）下的固定相对路径解析。
STANDARD_PATH = os.path.join("docs", "acceptance", "template-standard.json")
MANIFEST_PATH = os.path.join("web", "public", "data", "manifest.json")
DEFAULT_REPORT = os.path.join("work", "acceptance", "baseline-report.json")

# 必须验收的模块（与标准及快照 schema 一致的顺序）。
MODULE_NAMES = [
    "marketIndex",
    "turnover",
    "sentiment",
    "sectorPerformance",
    "fundFlow",
    "northbound",
    "margin",
    "tracks",
    "summary",
]

# 规则名常量（见任务规范逐模块规则）。
RULE_MARKETINDEX = "RULE_MARKETINDEX"
RULE_TURNOVER = "RULE_TURNOVER"
RULE_SENTIMENT = "RULE_SENTIMENT"
RULE_SECTORS = "RULE_SECTORS"
RULE_FUNDFLOW = "RULE_FUNDFLOW"
RULE_NORTHBOUND = "RULE_NORTHBOUND"
RULE_MARGIN = "RULE_MARGIN"
RULE_TRACKS = "RULE_TRACKS"
RULE_SUMMARY = "RULE_SUMMARY"

# 必需核心指数代码。
REQUIRED_INDEX_CODES = {"000001", "399001", "399006", "000688", "000300", "899050"}


def is_finite_number(value):
    """数值有限性判断：int/float 且非 bool 且 math.isfinite。"""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


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
    """返回模块 dict，缺省返回 {}。"""
    modules = snapshot.get("modules")
    if isinstance(modules, dict):
        return modules.get(name, {})
    return {}


# ---------------------------------------------------------------- 各模块规则


def check_marketindex(snapshot):
    mod = _module(snapshot, "marketIndex")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    items = mod.get("items")
    if not isinstance(items, list):
        ok = False
        details.append(_detail_gap("items 不是 list"))
        return _result(RULE_MARKETINDEX, ok, details, status)
    if len(items) < 6:
        ok = False
        details.append(_detail_gap(f"items 长度 {len(items)} < 6"))
    codes = []
    for it in items:
        if isinstance(it, dict):
            codes.append(str(it.get("code")))
    present = set(codes)
    missing = REQUIRED_INDEX_CODES - present
    if missing:
        ok = False
        details.append(_detail_gap(f"缺失核心指数: {sorted(missing)}"))
    # 判各必需指数之 close/changePct 是否有限
    by_code = {}
    for it in items:
        if isinstance(it, dict):
            by_code[str(it.get("code"))] = it
    for code in sorted(REQUIRED_INDEX_CODES):
        it = by_code.get(code)
        if it is None:
            continue  # 已在上方记缺指数
        if not is_finite_number(it.get("close")):
            ok = False
            details.append(_detail_gap(f"{code} close 非有限数值: {it.get('close')!r}"))
        if not is_finite_number(it.get("changePct")):
            ok = False
            details.append(_detail_gap(f"{code} changePct 非有限数值: {it.get('changePct')!r}"))
    if ok and not details:
        details.append(_detail_ok("FINAL；>=6 项；6 个核心指数 close/changePct 均有限"))
    return _result(RULE_MARKETINDEX, ok, details, status)


def check_turnover(snapshot):
    mod = _module(snapshot, "turnover")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    today = mod.get("turnoverToday")
    if not is_finite_number(today):
        ok = False
        details.append(_detail_gap(f"turnoverToday 非有限数值: {today!r}"))
    legacy = bool((snapshot.get("meta") or {}).get("legacy", False))
    if not legacy:
        fields = {
            "turnoverPrevious": mod.get("turnoverPrevious"),
            "turnoverDelta": mod.get("turnoverDelta"),
            "turnoverChangePct": mod.get("turnoverChangePct"),
        }
        for name, val in fields.items():
            if not is_finite_number(val):
                ok = False
                details.append(_detail_gap(f"{name} 非有限数值: {val!r}（非 legacy 必需）"))
        vs = mod.get("volumeState")
        if vs not in {"EXPANSION", "CONTRACTION", "FLAT"}:
            ok = False
            details.append(_detail_gap(f"volumeState={vs!r} 不在 {{EXPANSION,CONTRACTION,FLAT}}"))
    else:
        details.append(_detail_ok("legacy=True 例外：仅要求 turnoverToday 有限"))
    if ok and not details:
        details.append(_detail_ok("FINAL；turnoverToday 有限（legacy 口径）"))
    return _result(RULE_TURNOVER, ok, details, status)


def check_sentiment(snapshot):
    mod = _module(snapshot, "sentiment")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    counts = {
        k: mod.get(k)
        for k in (
            "riseCount", "fallCount", "flatCount",
            "nonStLimitUpCount", "stLimitUpCount", "nonStLimitDownCount",
        )
    }
    for name, val in counts.items():
        if not is_finite_number(val):
            ok = False
            details.append(_detail_gap(f"{name} 非有限数值: {val!r}"))
    rise = counts.get("riseCount")
    fall = counts.get("fallCount")
    flat = counts.get("flatCount")
    if all(is_finite_number(v) for v in (rise, fall, flat)):
        if float(rise) + float(fall) + float(flat) < 4000:
            ok = False
            details.append(
                _detail_gap(f"rise+fall+flat={float(rise)+float(fall)+float(flat)} < 4000")
            )
    else:
        details.append(_detail_gap("rise/fall/flat 不全为有限，无法校验总数"))
        ok = False
    bc = mod.get("brokenLimitCount")
    if bc is not None and not is_finite_number(bc):
        ok = False
        details.append(_detail_gap(f"brokenLimitCount 必须有限或 None: {bc!r}"))
    sd = mod.get("stLimitDownCount")
    if sd is None:
        details.append(_detail_ok("stLimitDownCount 缺失（note，不算 fail）"))
    else:
        details.append(_detail_ok(f"stLimitDownCount={sd!r} 存在"))
    # 任何 passed=False 的 gap 都使 ok=False（stLimitDownCount 缺失只是 note）
    if any(not d["passed"] for d in details):
        ok = False
    return _result(RULE_SENTIMENT, ok, details, status)


def _check_items_list(mod, groups, min_len):
    """通用榜单校验：groups 为字段名列表，每项须 name 非空 str 且 changePct/netInflowYi 有限。"""
    ok = True
    details = []
    for name, field in groups:
        val = mod.get(name)
        if not isinstance(val, list):
            ok = False
            details.append(_detail_gap(f"{name} 不是 list"))
            continue
        if len(val) < min_len:
            ok = False
            details.append(_detail_gap(f"{name} 长度 {len(val)} < {min_len}"))
        for i, item in enumerate(val):
            if not isinstance(item, dict):
                ok = False
                details.append(_detail_gap(f"{name}[{i}] 不是对象"))
                continue
            nm = item.get("name")
            if not (isinstance(nm, str) and nm.strip()):
                ok = False
                details.append(_detail_gap(f"{name}[{i}] name 为空"))
            if not is_finite_number(item.get(field)):
                ok = False
                details.append(_detail_gap(f"{name}[{i}].{field} 非有限数值: {item.get(field)!r}"))
    return ok, details


def check_sectors(snapshot):
    mod = _module(snapshot, "sectorPerformance")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    groups = [
        ("industryTop5", "changePct"),
        ("industryBottom5", "changePct"),
        ("conceptTop5", "changePct"),
        ("conceptBottom5", "changePct"),
    ]
    sub_ok, sub_details = _check_items_list(mod, groups, 5)
    ok = ok and sub_ok
    details.extend(sub_details)
    if ok and not any(not d["passed"] for d in details):
        details.append(_detail_ok("FINAL；四类榜单均 >=5 且 name/changePct 有效"))
    return _result(RULE_SECTORS, ok, details, status)


def check_fundflow(snapshot):
    mod = _module(snapshot, "fundFlow")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    groups = [
        ("industryInflowTop10", "netInflowYi"),
        ("industryOutflowTop10", "netInflowYi"),
        ("conceptInflowTop10", "netInflowYi"),
        ("conceptOutflowTop10", "netInflowYi"),
        ("stockInflowTop10", "netInflowYi"),
        ("stockOutflowTop10", "netInflowYi"),
    ]
    sub_ok, sub_details = _check_items_list(mod, groups, 10)
    ok = ok and sub_ok
    details.extend(sub_details)
    if ok and not any(not d["passed"] for d in details):
        details.append(_detail_ok("FINAL；六类榜单均 >=10 且 name/netInflowYi 有效"))
    return _result(RULE_FUNDFLOW, ok, details, status)


def check_northbound(snapshot):
    mod = _module(snapshot, "northbound")
    status = mod.get("status")
    details = []
    # 分支 1：legacy 口径 —— status FINAL 且 legacyImportedFields 含三项有限
    legacy = mod.get("legacyImportedFields")
    if (
        status == "FINAL"
        and isinstance(legacy, dict)
        and all(
            is_finite_number(legacy.get(f))
            for f in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow")
        )
    ):
        details.append(_detail_ok("legacy 口径：三项净流入有限数值"))
        return _result(RULE_NORTHBOUND, True, details, status)
    if status == "FINAL" and isinstance(legacy, dict):
        bad = [f for f in ("totalNetInflow", "shanghaiNetInflow", "shenzhenNetInflow")
               if not is_finite_number(legacy.get(f))]
        details.append(_detail_gap(f"legacyImportedFields 存在但字段非有限: {bad}"))
        return _result(RULE_NORTHBOUND, False, details, status)
    # 分支 2：季度口径 —— 必须 status=FINAL 且 items 非空（真实数据），
    # 占位对象（status=UNAVAILABLE/items=[]）不得算通过。
    holding = mod.get("quarterlyHolding")
    holding_nonempty = (
        isinstance(holding, dict)
        and holding.get("status") == "FINAL"
        and isinstance(holding.get("items"), list)
        and len(holding["items"]) > 0
    ) or (
        isinstance(holding, list) and len(holding) > 0
    )
    mode = str(mod.get("mode") or "")
    if holding_nonempty and "POST_20240819" in mode:
        details.append(_detail_ok("季度口径，日度停发，需页面诚实标注"))
        return _result(RULE_NORTHBOUND, True, details, status)
    details.append(_detail_gap(
        f"status={status!r} 且非 legacy 口径；quarterlyHolding 为空或 mode={mode!r} 不含 POST_20240819"
    ))
    return _result(RULE_NORTHBOUND, False, details, status)


def check_margin(snapshot, manifest):
    mod = _module(snapshot, "margin")
    status = mod.get("status")
    details = []
    if (
        status == "FINAL"
        and is_finite_number(mod.get("financingBalance"))
        and is_finite_number(mod.get("securitiesLendingBalance"))
        and is_finite_number(mod.get("marginBalance"))
    ):
        details.append(_detail_ok("FINAL；三项余额均为有限数值"))
        return _result(RULE_MARGIN, True, details, status)
    # D0 规则：PENDING + latestPublishedReference + 日期 == 最新采集日
    ref = mod.get("latestPublishedReference")
    trade_date = snapshot.get("tradeDate")
    latest = None
    if isinstance(manifest, dict):
        latest = manifest.get("latestCapturedDate")
    if (
        status == "PENDING"
        and isinstance(ref, dict)
        and trade_date is not None
        and trade_date == latest
    ):
        details.append(_detail_ok(
            f"D0 规则：PENDING 且 latestPublishedReference(dataDate={ref.get('dataDate')}) "
            f"== manifest.latestCapturedDate={latest}"
        ))
        return _result(RULE_MARGIN, True, details, status)
    details.append(_detail_gap(
        f"status={status!r}，三项余额非全有限，且不满足 D0 PENDING 最新采集日规则"
    ))
    return _result(RULE_MARGIN, False, details, status)


def check_tracks(snapshot):
    mod = _module(snapshot, "tracks")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    items = mod.get("items")
    if not isinstance(items, list):
        ok = False
        details.append(_detail_gap("items 不是 list"))
        return _result(RULE_TRACKS, ok, details, status)
    if len(items) < 4:
        ok = False
        details.append(_detail_gap(f"items 长度 {len(items)} < 4"))
    required_keys = [
        "trackId", "trackName", "positioning", "turnoverRank", "mainNetInflow",
        "continuousInflowDays", "maAlignment", "rps60", "excessReturn20d",
        "limitUpCount", "ladderCompleteness", "redStockRatio", "coreCatalyst",
        "earningsRealization", "score", "decision",
    ]
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            ok = False
            details.append(_detail_gap(f"items[{i}] 不是对象"))
            continue
        for key in required_keys:
            if key not in item:
                ok = False
                details.append(_detail_gap(f"items[{i}] 缺 {key}"))
        if not is_finite_number(item.get("mainNetInflow")):
            ok = False
            details.append(_detail_gap(f"items[{i}] mainNetInflow 非有限数值: {item.get('mainNetInflow')!r}"))
        if item.get("score") is None:
            ok = False
            details.append(_detail_gap(f"items[{i}] score 为 None"))
        if item.get("decision") is None:
            ok = False
            details.append(_detail_gap(f"items[{i}] decision 为 None"))
    if ok and not any(not d["passed"] for d in details):
        details.append(_detail_ok(f"FINAL；>=4 条赛道；全部必备键存在，mainNetInflow/score/decision 有效"))
    return _result(RULE_TRACKS, ok, details, status)


def check_summary(snapshot):
    mod = _module(snapshot, "summary")
    status = mod.get("status")
    details = []
    ok = True
    if status != "FINAL":
        ok = False
        details.append(_detail_gap(f"status={status!r} 期望 FINAL"))
    fields = [
        "indexAndTurnover", "sentiment", "fundFlow", "trackConclusion",
        "marketEnvironment", "northbound", "margin", "riskWarning",
    ]
    for f in fields:
        val = mod.get(f)
        if not (isinstance(val, str) and len(val.strip()) >= 10):
            ok = False
            details.append(_detail_gap(f"{f} 缺失/过短: {val!r}"))
    if ok and not any(not d["passed"] for d in details):
        details.append(_detail_ok("FINAL；8 个总结字段均非空 str 且 >=10 字符"))
    return _result(RULE_SUMMARY, ok, details, status)


OP_COUNT_FIELDS = 6  # 其余模块计数（供 summary.moduleFailCounts 累加）


def run_acceptance_date(snapshot, trade_date, manifest):
    """对单个已加载快照执行 9 模块验收。返回 dict。"""
    modules_out = {}
    all_pass = True
    # schema 校验
    schema_valid = True
    schema_error = ""
    try:
        from collector.validators.schema import validate_snapshot
        validate_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001
        schema_valid = False
        first = str(exc).splitlines()[0] if str(exc).splitlines() else str(exc)
        schema_error = first

    checks = {
        "marketIndex": check_marketindex(snapshot),
        "turnover": check_turnover(snapshot),
        "sentiment": check_sentiment(snapshot),
        "sectorPerformance": check_sectors(snapshot),
        "fundFlow": check_fundflow(snapshot),
        "northbound": check_northbound(snapshot),
        "margin": check_margin(snapshot, manifest),
        "tracks": check_tracks(snapshot),
        "summary": check_summary(snapshot),
    }
    for name in MODULE_NAMES:
        modules_out[name] = checks[name]
        if not checks[name]["pass"]:
            all_pass = False
    overall_pass = bool(all_pass and schema_valid)
    overall = "PASS" if overall_pass else "FAIL"
    return {
        "schemaValid": schema_valid,
        "schemaError": schema_error,
        "modules": modules_out,
        "overall": overall,
        "pass": overall_pass,
    }


def load_snapshot(trade_date):
    """从 daily/YYYY/YYYY-MM-DD.json 载入快照。返回 (snapshot, filepath)。"""
    yyyy = trade_date[:4]
    path = os.path.join("web", "public", "data", "daily", yyyy, f"{trade_date}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh), path


def build_entry(trade_date, manifest):
    """处理单个日期。"""
    modules_out = {}
    try:
        snapshot, path = load_snapshot(trade_date)
    except FileNotFoundError:
        for name in MODULE_NAMES:
            modules_out[name] = _result("_", False, [_detail_gap("FILE_MISSING")], "_")
        return {
            "gap": "FILE_MISSING",
            "schemaValid": False,
            "schemaError": "",
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }
    result = run_acceptance_date(snapshot, trade_date, manifest)
    return result


def console_line(trade_date, entry):
    mods = entry.get("modules", {})
    parts = []
    for name in MODULE_NAMES:
        parts.append(f"{ 'P' if mods.get(name, {}).get('pass') else 'F' }:{name}")
    flag = entry["overall"]
    gap = entry.get("gap")
    suffix = f" gap={gap}" if gap else ""
    return f"{flag:<4} {trade_date}  " + " ".join(parts) + suffix


def main(argv=None):
    parser = argparse.ArgumentParser(description="范本效果自动验收器（数据侧）")
    parser.add_argument("--date", dest="date", help="验收单个日期 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="验收 manifest 全部 availableDates")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="报告输出路径")
    args = parser.parse_args(argv)

    if not os.path.exists(STANDARD_PATH):
        sys.stderr.write(f"验收标准缺失: {STANDARD_PATH}\n")
        sys.exit(2)

    with open(STANDARD_PATH, "r", encoding="utf-8") as fh:
        standard = json.load(fh)

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
        entries[trade_date] = build_entry(trade_date, manifest)
        print(console_line(trade_date, entries[trade_date]))

    pass_dates = [d for d in dates if entries[d]["pass"]]
    fail_dates = [d for d in dates if not entries[d]["pass"]]

    # 模块失败日期数
    module_fail = {}
    for name in MODULE_NAMES:
        n = 0
        affected = []
        for d in dates:
            mod = entries[d].get("modules", {}).get(name, {})
            if not mod.get("pass"):
                n += 1
                affected.append(d)
        module_fail[name] = {"failDates": n, "dates": affected}
    module_fail_counts = [
        {"module": name, "failDates": module_fail[name]["failDates"]}
        for name in MODULE_NAMES
    ]

    print()
    print(f"汇总：PASS={len(pass_dates)}  FAIL={len(fail_dates)}  共 {len(dates)} 个日期")
    print(f"passDates: {pass_dates}")
    print(f"failDates: {fail_dates}")
    print("各模块失败日期数：")
    for name in MODULE_NAMES:
        print(f"  {name:<16} failDates={module_fail[name]['failDates']}")
        if module_fail[name]["dates"]:
            print(f"    dates: {module_fail[name]['dates']}")

    report = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "standard": STANDARD_PATH,
        "dates": {},
        "summary": {
            "passDates": pass_dates,
            "failDates": fail_dates,
            "moduleFailCounts": module_fail_counts,
        },
    }
    for d in dates:
        entry = entries[d]
        report["dates"][d] = {
            "schemaValid": entry.get("schemaValid"),
            "schemaError": entry.get("schemaError"),
            "gap": entry.get("gap"),
            "overall": entry["overall"],
            "modules": {
                name: {
                    "status": entry["modules"][name]["status"],
                    "pass": entry["modules"][name]["pass"],
                    "rule": entry["modules"][name]["rule"],
                    "details": entry["modules"][name]["details"],
                }
                for name in MODULE_NAMES
            },
        }

    report_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(report_dir, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print()
    print(f"报告已写入: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
