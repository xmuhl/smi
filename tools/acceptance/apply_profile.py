#!/usr/bin/env python3
"""SMI 历史覆盖 Profile 应用工具（R12 P2 产品裁决落地）。

读取验收报告 + historical-profile.json，生成"已知边界收口视图"：
- 按 profile 声明的历史能力范围，把历史日已知边界模块从 failDates 剔除并标注 accepted；
- 参考日（07-17）不豁免，仍按完整标准；
- 不修改原始验收报告（fail-closed 诚实），只产出收口视图。

用法：
  python tools/acceptance/apply_profile.py --report work/acceptance/p1_r3_sector_fix_full.json
      [--profile docs/acceptance/historical-profile.json]
      [--out work/acceptance/<name>_profile_applied.json]
"""
import argparse
import json
import os
import sys

DEFAULT_REPORT = "work/acceptance/baseline-report.json"
DEFAULT_PROFILE = os.path.join("docs", "acceptance", "historical-profile.json")
REFERENCE_DATE = "2026-07-17"


def main(argv=None):
    parser = argparse.ArgumentParser(description="SMI 历史覆盖 Profile 应用")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="验收报告路径")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="历史 profile JSON")
    parser.add_argument("--out", default=None, help="输出收口视图路径")
    args = parser.parse_args(argv)

    with open(args.report, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    with open(args.profile, "r", encoding="utf-8") as fh:
        profile = json.load(fh)

    reference_date = profile.get("referenceDate", REFERENCE_DATE)
    modules_def = profile.get("modules", {})
    unrecoverable = profile.get("unrecoverableRanges", [])

    # 收集不可恢复区间（日期闭区间列表）
    forced_boundaries = []  # 始终作为已知边界的日期区间
    for r in unrecoverable:
        if r.get("status") == "UNRECOVERABLE":
            a, b = r["range"]
            forced_boundaries.append((a, b))

    applied = {
        "schemaVersion": "1.0",
        "sourceReport": args.report,
        "sourceProfile": args.profile,
        "profileVersion": profile.get("profileVersion") or profile.get("profile_version"),
        "referenceDate": reference_date,
        "semantics": profile.get("semantics"),
        "acceptedBoundaries": {},
        "summary": {},
    }

    dates = list(report.get("dates", {}).keys())
    fail_dates = set(report.get("summary", {}).get("failDates", []))
    accepted_boundaries = {}  # module -> list of dates accepted
    overall_remaining = []    # still failing after profile
    accepted_modules = set(modules_def.keys())

    for d in dates:
        if d == reference_date:
            # 参考日不豁免
            if d in fail_dates:
                overall_remaining.append(d)
            continue
        entry = report["dates"].get(d, {})
        mods = entry.get("modules", {})
        for mname, mdef in modules_def.items():
            mod = mods.get(mname)
            if mod is None:
                continue
            if mod.get("pass"):
                continue  # already pass
            # 检查该日是否命中不可恢复区间（该日周期内该模块受影响）
            in_unrecoverable = False
            for (a, b) in forced_boundaries:
                if a <= d <= b and mname in _unrecoverable_modules(unrecoverable):
                    in_unrecoverable = True
            # 检查最晚支持日：d < earliestSupportedDate => 不在承诺范围, 视为边界外
            esd = mdef.get("earliestSupportedDate")
            out_of_promise = esd and d < esd
            if in_unrecoverable or out_of_promise:
                accepted_boundaries.setdefault(mname, []).append(d)
                fail_dates.discard(d)
                continue
            # 结构性缺字段（missingFields 全部或部分缺失）→ 已知边界
            missing = mdef.get("missingFields", [])
            if missing and all(_field_missing(mod, f) for f in missing):
                accepted_boundaries.setdefault(mname, []).append(d)
                fail_dates.discard(d)
                continue
            overall_remaining.append(d)

    # remaining fails that are not module-level boundaries still count
    for fd in sorted(fail_dates):
        if fd != reference_date and fd not in [
            x for lst in accepted_boundaries.values() for x in lst
        ]:
            overall_remaining.append(fd)

    applied["acceptedBoundaries"] = accepted_boundaries
    module_fail_map = {}
    for mname in modules_def:
        module_fail_map[mname] = report.get("summary", {}).get("moduleFailCounts", [])
    accepted_count = sum(len(v) for v in accepted_boundaries.values())

    applied["summary"] = {
        "originalFailDates": report.get("summary", {}).get("failDates", []),
        "originalPassDates": report.get("summary", {}).get("passDates", []),
        "acceptedBoundaryDates": sorted({d for v in accepted_boundaries.values() for d in v}),
        "acceptedBoundaryCount": accepted_count,
        "remainingFailDates": sorted(set(overall_remaining)),
        "remainingFailCount": len(set(overall_remaining)),
        "allDatesAccepted": len(set(overall_remaining)) == 0 and not fail_dates,
        "result": "PROFILE_APPLIED"
    }

    rv = report.copy()
    rv["profileApplied"] = applied

    out = args.out or args.report.replace(".json", "_profile_applied.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rv, fh, ensure_ascii=False, indent=2)

    print(f"profile applied: acceptedBoundaryDates={applied['summary']['acceptedBoundaryDates']}")
    print(f"remainingFail={sorted(set(overall_remaining))}")
    print(f"written: {out}")
    return 0


def _unrecoverable_modules(unrecoverable):
    out = set()
    for r in unrecoverable:
        out.update(r.get("affectedModules", []))
    return out


def _field_missing(mod, field):
    """mod 为模块 dict；判断指定字段是否缺失/null/为空列表。"""
    if isinstance(mod, dict):
        v = mod.get(field)
        if v is None:
            return True
        if isinstance(v, list) and len(v) == 0:
            return True
        if isinstance(v, str) and v == "":
            return True
        # 嵌套 items
    # tracks 场景：字段在 items[0] 里
    items = mod.get("items") if isinstance(mod, dict) else None
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict) and first.get(field) is None:
            return True
    return True if mod is None else False


if __name__ == "__main__":
    raise SystemExit(main())
