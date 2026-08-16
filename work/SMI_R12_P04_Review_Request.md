# SMI R12 P0.4 复审：P0.3 四项 NOT_CLOSED 的收口交付

- 轮次：R12 P0.4（对 R12 P0.3 HOLD 的第四修订轮）
- 送审输入 commit：25b1629（含代码 commit d688777；单分支 feat/p1-collector-revamp）
- 基线报告提交：ece8874（仅改 baseline-report.json；evaluatedCommit=25b1629、dirty=false，两提交溯源）
- 前置复核链：P0 → P0.1 → P0.2 → P0.3（HOLD：P0-003/007/008 + P03-001）→ 本轮

## 一、逐项收口（对照 P0.3 报告 FIX）

| 编号 | 收口内容 | 证据 |
|---|---|---|
| P0-003 nested typed 漏洞 | ① percentString 正则修正为 \d+(\.\d+)?% 全串匹配并加 0~100 数值范围（"dd.dd%" 拒、"0.93%" 过）；② numericString 增加 finite + 非负判定（NaN/Infinity/-5 拒、"4,401,900" 过）；③ 非法 ISO 后缀（如 "2026-06-30THIS_IS_NOT_ISO"）解析失败即 FAIL | accept.py::_validate_nested_value；test_p04_pct_of_issued_garbage / test_p04_shareholding_nan_and_negative / test_p04_asof_garbage_suffix / test_p04_official_nb_positive |
| P0-007 OFFICIAL 语义可说反 | summaryFacts.northbound 升级为机读组合约束：mustContainAnyGroups=[["停发","不再"],["季度","point-in-time","时点"]]（两组各须命中一词）+ mustNotContain=["官方日度净流入","连续净流入","今日北向净流入"]（禁止虚构日度净流入）；_run_summary_facts 执行三类键 | accept.py::_run_summary_facts；standard summaryFacts；test_p04_official_summary_fabricates_daily |
| P0-008 unit 假阳性 | 采用方案 A：turnover.fields / margin.fields 显式声明 {"name":"unit","kind":"enum","required":true,"enumValues":["亿元"]}（fundFlow 已有），INV-UNIT-亿元 经通用字段校验强制；INV-UNIT desc/enforce/spec.modules 口径统一（三模块，不再提 northbound）；相关模块 ruleVersion+1 并同步 dispatch 表支持版本（turnover [2,3]、margin [1,2,3]、summary [2,3,4]） | standard turnover/margin fields + crossModuleInvariants；test_p04_unit_deleted_invariant |
| P03-001 缺专项回归 | test_accept.py 新增 9 个专项测试：OFFICIAL 合法正向样本（真实 HKEX 形态 4,401,900/0.93%/sh/sz）PASS、百分比垃圾/NaN/负值/ISO 后缀 FAIL、unit 删除 invariant false、OFFICIAL 虚构日度净流入 FAIL、generic ruleVersion 999 自检失败、tracks effectiveFrom 垃圾 FAIL、recalc trackId 集合不一致 FAIL（单元级） | test_accept.py P0.4 段（9 个），全套 29 测试通过 |

## 二、新基线（evaluatedCommit=25b1629）

- **2026-07-17：PASS（9/9 模块 + 9/9 不变量）**；
- 2026-08-14：FAIL={sentiment, northbound, tracks, summary}（均为 P1/P2 数据工作范围：sentiment 补封板率/连板字段、northbound 改 OFFICIAL 枚举+publishedAt 回填、tracks 未实现、summary 旧文案缺数值锚）；
- 2026-07-20~08-13：FAIL（历史回补范围，P1）；
- 测试：tools/acceptance/test_accept.py 29/29（20 旧 + 9 新专项）；collector 92 项此前全绿（本轮未改 collector）。

## 三、请复核

1. 上轮 4 项（P0-003/007/008/P03-001）是否可判 CLOSED；如有新变体按新编号登记；
2. 若收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
