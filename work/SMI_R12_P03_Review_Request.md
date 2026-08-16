# SMI R12 P0.3 复审：P0.2 五项 NOT_CLOSED 的收口交付

- 轮次：R12 P0.3（对 R12 P0.2 HOLD 的第三修订轮）
- 送审输入 commit：c9e2782（单分支 feat/p1-collector-revamp，两提交溯源：基线报告 2f955f0 仅改 baseline-report.json）
- 前置复核链：P0 → HOLD(9) → P0.1 → HOLD(9) → P0.2 → HOLD(5：P0-002/003/006/007/008) → 本轮
- 基线 provenance：evaluatedCommit=c9e2782、dirty=false

## 一、逐项收口（对照 P0.2 报告 FIX）

| 编号 | 收口内容 | 证据 |
|---|---|---|
| P0-002 单一真源 | ① generic 模块（marketIndex/sectorPerformance/fundFlow）同样走 ruleId→{supportedVersions, handler} 版本绑定，ruleVersion 不受支持即启动退出 3；② 通用引擎新增嵌套 DSL 递归消费：kind 支持 object(subFields 递归)/array(itemFields)/dateString/boolean/numericString/const，spec.requiredCondition（{"whenField","equals"}）门控 required；③ summaryFacts 由 check_summary 读取执行（标准为机读结构）；④ northbound quarterlyHolding 经通用引擎 subFields 递归 typed 校验 | accept.py::_validate_nested_value / startup_self_check / check_summary；standard northbound.fields |
| P0-003 北向 strict PIT | ① _parse_iso_date_strict 严格化：len=10 全串 date.fromisoformat / 含 T 全串 datetime.fromisoformat，任何垃圾后缀（如 "2026-08-14THIS_IS_NOT_ISO"）解析失败即 FAIL，禁止截断前 10 字符；② quarterlyHolding.items 逐项 typed（shareholding=numericString 如 "4,401,900"、pctOfIssued=percentString 如 "0.93%"、market 枚举 ["sh","sz"]——按真实 HKEX 数据修正原标准错误枚举）；③ OFFICIAL 分支经 requiredCondition 强制 quarterlyHolding 存在 | accept.py::_parse_iso_date_strict / check_northbound |
| P0-006 tracks fail-closed | ① effectiveFrom/effectiveTo 改 dateString 严格解析，不可解析即 FAIL（不再跳过比较），解析后校验覆盖区间；② _recalc_tracks 强制 set(recomputed.trackId)==set(snapshot.trackId) 且数量相等，缺失/多余/为空均 FAIL；③ 标准 notes 对齐：legacy 参考日以 referenceAssertions 为唯一金标、不做重算（原"legacy 同样重算"表述已删） | accept.py::check_tracks / _recalc_tracks；standard tracks.notes |
| P0-007 summary 方向事实 | ① check_summary 读取标准 summaryFacts 机读配置执行：marketEnvironment↔turnover（COMPARABLE 禁词 + volumeState 量能词 + turnoverToday/turnoverPrevious/turnoverDelta 整数数值锚）；margin↔marginBalanceChange 方向词（<0 须含 减少/下降/回落/减仓/净偿还，>0 须含 增加/上升/净买入，PENDING 须含 待披露/暂缺/参考/T+1）；northbound↔totalNetInflow 方向（<0 须含净流出、>0 须含净流入；OFFICIAL 须含 停发/季度/披露）；trackConclusion↔tracks 全赛道名前缀+判定词 | accept.py::check_summary；standard summary.summaryFacts |
| P0-008 invariant enforce 语义 | ① INV-UNIT-亿元：unit 缺失即 false（按标准 spec.modules=["turnover","fundFlow","margin"]，且只对标准声明 unit 字段的模块强制）；② INV-SENTIMENT-WIDTH：任一计数缺失/非有限即 false；③ INV-ENUM-SOURCE-METHOD：直接读标准 spec.allowedEnums（含 tracks items 的 maAlignment/excessReturn20d/decision），required 字段缺失或值越枚举即 false（枚举表已按 21 个快照实测值并集修正：turnover.method 增补 SH_SZ_A_NO_B_NO_BJ_V1、sectorPerformance 增补 THS/THS_HISTORICAL_INDEX 等）；④ INV-MARGIN-IDENTITY：FINAL 且 marginBalanceChange 存在时，前一 FINAL margin 缺失即 false（参考日经 spec.referenceDateExemption=true 由 INV-REF-EXACT 兜底）；⑤ 每模块 ruleVersion 与被改模块同步 +1 且 dispatch 表同步支持 | accept.py::run_cross_module_invariants；standard crossModuleInvariants |

## 二、新基线（evaluatedCommit=c9e2782，accept.py P0.3）

- **2026-07-17：PASS（9/9 模块 + 9/9 不变量）**；
- 2026-08-14：FAIL={sentiment(缺 limitSealRatePct/maxLimitUpStreak), northbound(mode/publishedAt 待 P1 数据), tracks(未实现), summary(marketEnvironment 缺 25538/4115 数值锚——P1 重生成文案)}；
- 2026-07-20：FAIL={turnover(缺 crossMethodReference), sentiment, sectorPerformance, fundFlow, northbound, tracks, summary}；
- 2026-07-21~08-13：FAIL={sentiment, sectorPerformance, fundFlow, northbound, tracks, summary}；
- 模块失败日期数：marketIndex 0 / turnover 1 / sentiment 20 / sectorPerformance 19 / fundFlow 19 / northbound 20 / margin 0 / tracks 20 / summary 20。

## 三、测试与验证（主控本地执行）

- py_compile PASS；tools/acceptance/test_accept.py + collector/tests/test_sectors_history.py = 26 passed；collector/tests/test_core.py = 86 passed；合计 112 全绿；
- 08-14 期望失败集已同步更新为 {sentiment, northbound, summary, tracks}（summary 方向/数值锚门禁的诚实拒绝，P1 重生成文案后恢复）。

## 四、请复核

1. 上轮 5 项（P0-002/003/006/007/008）是否可判 CLOSED；如有新变体按新编号登记；
2. 若收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
