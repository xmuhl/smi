#!/usr/bin/env python3
"""SMI 历史覆盖 Profile 应用工具 v2（R12 P3-001 修复：模块级因果接受）。

读取验收报告 + historical-profile.json + source snapshots，生成"已知边界收口视图"：

- 模块级因果接受：对每个验收失败模块独立判断是否属于 profile 且满足豁免条件；
  只有该日所有 FAIL 模块都属于被合法接受的 profile 边界时，才把该日从 remainingFailDates 移除。
  禁止 date-level 先 discard（旧版缺陷：掩盖非 profile 失败）。
- 字段真实性：从 source snapshot（web/public/data/daily/<yyyy>/<date>.json 的 modules.x）
  判断 profile 声明的 missingFields 是否真实缺失，不从验收结果对象猜。
- 日期范围：仅当日期落在 profile.appliesToRanges（或缺省 earliestSupportedDate..appliesThrough）
  内才应用；profile 不自动扩张到未来新交易日。
- unrecoverable range-local：每个 unrecoverable range 只豁免其自身 affectedModules。
"""
import argparse
import json
import os

DEFAULT_REPORT = "work/acceptance/baseline-report.json"
DEFAULT_PROFILE = os.path.join("docs", "acceptance", "historical-profile.json")
DEFAULT_DATA_ROOT = os.path.join("web", "public", "data")
REFERENCE_DATE = "2026-07-17"


def _parse_iso(s):
    return tuple(int(x) for x in s.split("-")) if isinstance(s, str) and len(s.split("-")) == 3 else None


def _in_range(d, a, b):
    da = _parse_iso(d)
    pa = _parse_iso(a)
    pb = _parse_iso(b)
    if not (da and pa and pb):
        return False
    return pa <= da <= pb


def _load_snapshot(date, data_root):
    p = os.path.join(data_root, "daily", date[:4], date + ".json")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh).get("modules")
    except Exception:
        return None


def _status_allowed(entry_module, profile_module):
    status = (entry_module or {}).get("status") or ""
    allowed = profile_module.get("acceptedStatuses") or ["PARTIAL", "UNAVAILABLE", "PENDING"]
    return status in allowed


def _field_missing(snap_modules, module_name, field):
    if snap_modules is None:
        return False  # 快照读不到：保守不豁免
    mod = snap_modules.get(module_name)
    if not isinstance(mod, dict):
        return False
    if field in mod:
        v = mod.get(field)
        if v is None:
            return True
        if isinstance(v, list) and len(v) == 0:
            return True
        if isinstance(v, str) and v == "":
            return True
        return False
    items = mod.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        v = items[0].get(field)
        return v is None or (isinstance(v, list) and len(v) == 0) or (isinstance(v, str) and v == "")
    return False


def _in_unrecoverable_for_module(date, module_name, unrecoverable):
    for r in unrecoverable:
        if r.get("status") != "UNRECOVERABLE":
            continue
        a, b = r["range"]
        if module_name in (r.get("affectedModules") or []) and _in_range(date, a, b):
            return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="SMI 历史覆盖 Profile 应用 v2")
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--out", default=None)
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    args = parser.parse_args(argv)

    with open(args.report, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    with open(args.profile, "r", encoding="utf-8") as fh:
        profile = json.load(fh)

    reference_date = profile.get("referenceDate", REFERENCE_DATE)
    modules_def = profile.get("modules", {})
    unrecoverable = profile.get("unrecoverableRanges", [])
    applies_to_ranges = profile.get("appliesToRanges")
    applies_through = profile.get("appliesThrough")
    earliest = profile.get("earliestSupportedDate")

    def _in_applicability(d):
        if d == reference_date:
            return False
        if applies_to_ranges:
            return any(_in_range(d, a, b) for a, b in applies_to_ranges)
        if applies_through and _parse_iso(d) and _parse_iso(applies_through) and _parse_iso(d) > _parse_iso(applies_through):
            return False
        if earliest and _parse_iso(d):
            return _parse_iso(d) >= _parse_iso(earliest)
        return True

    dates = list(report.get("dates", {}).keys())
    original_fail = set(report.get("summary", {}).get("failDates", []))
    accepted = {}   # date -> {module: reason}
    rejected = {}   # date -> module list

    for d in dates:
        entry = report["dates"].get(d, {})
        mods_entry = entry.get("modules", {})
        snap_modules = _load_snapshot(d, args.data_root)
        failed = {}
        for mname, m_mod in mods_entry.items():
            if not (isinstance(m_mod, dict) and m_mod.get("pass")):
                failed[mname] = m_mod
        if not failed:
            continue
        acc_here = {}
        rej_here = {}
        for mname, m_mod in failed.items():
            if mname not in modules_def:
                rej_here[mname] = "not_in_profile"
                continue
            pmod = modules_def[mname]
            if not _in_applicability(d):
                rej_here[mname] = "outside_applicability"
                continue
            if not _status_allowed(m_mod, pmod):
                rej_here[mname] = "status_not_allowed:" + str(m_mod.get("status"))
                continue
            if _in_unrecoverable_for_module(d, mname, unrecoverable):
                acc_here[mname] = "unrecoverable_range"
                continue
            missing = pmod.get("missingFields") or []
            if not missing:
                rej_here[mname] = "no_missing_fields_declared"
                continue
            real = []
            for f in missing:
                if _field_missing(snap_modules, mname, f):
                    real.append(f)
            if not real:
                rej_here[mname] = "declared_missing_not_absent_in_snapshot"
                continue
            # P3-001 v3：验证模块的全部失败细节都能被 profile 解释
            # 从验收报告读取该模块的 failure details，检查是否有非 profile 字段的失败
            entry_mod = failed.get(mname)
            if entry_mod and isinstance(entry_mod, dict):
                details = entry_mod.get("details") or []
                unreconciled = []
                for det in details:
                    dtext = det.get("detail") if isinstance(det, dict) else str(det)
                    # 如果 detail 提到缺失字段，检查是否在 profile 声明中
                    if any(f in dtext for f in missing):
                        continue  # 归因于 profile 字段
                    # 如果提到 status 期望 FINAL 但实际是 PARTIAL/UNAVAILABLE → profile 允许
                    if "期望 FINAL" in dtext and entry_mod.get("status") in ("PARTIAL", "UNAVAILABLE", "PENDING"):
                        continue
                    unreconciled.append(dtext)
                if unreconciled:
                    rej_here[mname] = "unreconciled_details:" + ";".join(unreconciled[:3])
                    continue
            acc_here[mname] = "missing_fields:" + ",".join(real)
        if acc_here and not rej_here:
            accepted[d] = acc_here
        else:
            rejected[d] = {**acc_here, **rej_here}

    applied = {
        "schemaVersion": "2.0",
        "sourceReport": args.report,
        "sourceProfile": args.profile,
        "profileVersion": profile.get("profileVersion"),
        "referenceDate": reference_date,
        "acceptedModuleBoundaries": accepted,
        "rejectedModuleDetail": rejected,
        "summary": {
            "originalFailDates": sorted(original_fail),
            "acceptedBoundaryDates": sorted(accepted.keys()),
            "acceptedModuleCount": sum(len(v) for v in accepted.values()),
            "remainingFailDates": sorted(original_fail - set(accepted.keys())),
            "remainingFailCount": len(original_fail - set(accepted.keys())),
            "allDatesAccepted": len(original_fail - set(accepted.keys())) == 0,
            "result": "PROFILE_APPLIED_V2"
        }
    }
    rv = report.copy()
    rv["profileApplied"] = applied
    out = args.out or args.report.replace(".json", "_profile_applied.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rv, fh, ensure_ascii=False, indent=2)
    print("acceptedBoundaryDates=" + str(applied["summary"]["acceptedBoundaryDates"]))
    print("remainingFail=" + str(applied["summary"]["remainingFailDates"]))
    print("acceptedModuleCount=" + str(applied["summary"]["acceptedModuleCount"]))
    print("written: " + out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
