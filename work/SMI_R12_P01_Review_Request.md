# SMI R12 P0.1 复审：9 项问题修复交付（送审 commit ac1963c）

- 轮次：R12 P0.1（对 R12 P0 HOLD 的修订轮）
- 送审 commit：ac1963c（分支 feat/p0-acceptance-baseline，基于 3306ba7 增量修订）
- 前置复核链：R12 P0 → HOLD（P1×3/P2×5/P3×1，报告 SMI_R12_P0_Review_Report.md）

## 一、本轮修订内容（对照 9 项问题逐条交付）

| 编号 | 修复 | 证据 |
|---|---|---|
| P0-001 参考基线假阳性 | ① 标准优先级锁定 referenceXlsx > canonicalSnapshot > rawLegacy；② 新增 referenceAssertions（311 条，07-17 按 XLSX 精确值断言：turnover 26549.58/24035.65/+2513.93/+10.46/EXPANSION、sentiment 482/5001/40/25/**10**/180/**32**/45/43.75/2连板、northbound -156.32/-68.54/-87.78、margin 28139.01 恒等、tracks 4×16 列等）；③ 07-17 快照已按 XLSX 校正（revision 4）：turnover 四字段回填+COMPARABLE、ST 计数 10/32、新增 limitSealRatePct/maxLimitUpStreak、rawLegacy 溯源块、summary.trackConclusion 与 4 赛道一致 | accept.py check_reference_modules；test 7/14/17 |
| P0-002 标准/执行器漂移 | accept.py 重写为单一真源驱动：通用字段/items/lists 规则全部从 template-standard.json 读取（kind/enum/min/max/minChars/cjkRequired/uniqueBy/sortedBy/sign），复杂规则经 ruleId/ruleVersion 绑定显式 handler，启动自检校验 version/ruleId/handler 注册一致性（不一致退出码 3）；20 个负向变异测试证明每个门禁真的能拒绝坏数据 | startup_self_check + test_accept.py 20/20 |
| P0-003 北向看未来 | mode 严格枚举（POST_20240819_LEGACY_IMPORTED / POST_20240819_OFFICIAL_REPLACEMENT）；OFFICIAL_REPLACEMENT 分支要求模块 FINAL + quarterlyHolding FINAL + items 逐项 schema + asOf<=selectedDate + publishedAt<=selectedDate（防 look-ahead）；占位 dict 一律 FAIL；INV-NORTHBOUND-PIT 不变量兜底 | check_northbound + test 13 |
| P0-004 跨口径 | turnover 通用方法边界状态机（COMPARABLE/PREVIOUS_UNAVAILABLE/PREVIOUS_METHOD_MISMATCH），无日期特判；COMPARABLE 强制 method==previousMethod+算术恒等（|delta-(today-prev)|<=0.01、|pct-delta/prev*100|<=0.01）；MISMATCH 允许独立 crossMethodReference* 字段（nonComparable=true） | check_turnover + test 4/5/6 |
| P0-005 情绪校正 | canonical 六计数+炸板+limitSealRatePct+maxLimitUpStreak 入标准与验收；参考日精确断言（ST 10/32、封板率 43.75、2连板）；correctionReason=LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX；rawLegacy 保留原始重复值溯源 | test 7/8 |
| P0-006 tracks 过松 | 16 列逐列 typed 校验（turnoverRank>0、mainNetInflow finite、continuousInflowDays 非负整数、maAlignment/excessReturn20d 枚举、rps60 0~100、limitUpCount 非负整数、ladderCompleteness 非空、redStockRatio 百分比串、催化/业绩兑现非空中文禁占位、score 0~100、decision 枚举）；模块级 configVersion/effectiveFrom/effectiveTo 必填；displayRules 改为最终 16 列网页目标；trackId 集合与标准一致 | check_tracks + test 16 |
| P0-007 summary | 8 段中文占比（分母=CJK+拉丁字母，数字不稀释）+minChars+禁占位词；riskWarning 必含"不构成投资建议"；依赖完整性：tracks FINAL 时 trackConclusion 必须提及 ≥2 条赛道名；任一模块非 FINAL 时至少一段含"不可用/缺失/部分/未覆盖/待披露/未实现"之一 | check_summary + test 17/18 |
| P0-008 语义完整性 | 9 条跨模块不变量全实现：INV-DATE-LOOKAHEAD（dataDate/asOf/publishedAt<=tradeDate）、INV-UNIT-亿元、INV-LIST-SORT-SIGN（榜单排序/唯一/符号）、INV-MARGIN-IDENTITY（|total-(fin+lend)|<=0.05+环比差额）、INV-TURNOVER-IDENTITY、INV-SENTIMENT-WIDTH（≥4000）、INV-ENUM-SOURCE-METHOD、INV-REF-EXACT、INV-NORTHBOUND-PIT | run_cross_module_invariants + test 2/10/11/12/15 |
| P0-009 溯源 | 报告新增 provenance：repoCommit、standardSha256、acceptorSha256、manifestSha256、perDateSnapshotSha256、pythonVersion、generatedAt | baseline-report.json.provenance |

## 二、新基线（accept.py v2 + 校正后数据）

- **07-17：PASS（9/9）**——参考日按 referenceAssertions 精确断言通过；
- 08-14：FAIL，失败集合={sentiment（缺 limitSealRatePct/maxLimitUpStreak，P1 补）、northbound（mode 需改 OFFICIAL_REPLACEMENT+publishedAt 回填，P1）、tracks（UNAVAILABLE 未实现，P2）}；margin PENDING 走 D0 分支 PASS；summary 依赖完整性 PASS；
- 07-20~08-13：FAIL，缺口= sentiment/sectorPerformance/fundFlow/northbound/tracks（P1/P2 回补目标）；
- 测试：tools/acceptance/test_accept.py 20/20 绿（18 负向变异+2 正向）。

## 三、本轮请复核

1. 上述 9 项是否可判定 CLOSED；如有新变体请按新编号登记；
2. 修订后的验收口径是否已可等价表达"任意日期达到 07-17 范本效果"（数据侧）；
3. 若收敛（0 NOT_CLOSED），请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。

## 四、附：当前基线明细（摘要）

07-17 PASS；07-20~08-13 每日期失败模块={sentiment,sectorPerformance,fundFlow,northbound,tracks}；08-14 失败模块={sentiment,northbound,tracks}。marketIndex/turnover/margin 全 21 日 PASS。
