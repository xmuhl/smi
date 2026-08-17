# SMI R12 P1 复审：历史数据回补与验收

- 轮次：R12 P1（19 个历史交易日全量回补 + archive seed + 验收 INV 闭合）
- 送审输入 commit：a8b3a31（功能代码）+ 01224c9（数据/报告）
- 前置复核链：…→ P0.5（已 ChatGPT 裁决收敛）

## 一、本轮改动清单

### 代码（commit a8b3a31）
1. collector/modules/sectors.py：_THS_HIST_CONCURRENCY 10→6（2026-08-16 实测 THS 主机级封禁 SSL EOF，回落防封）
2. docs/acceptance/template-standard.json：crossModuleInvariants.INV-ENUM-SOURCE-METHOD.allowedEnums.fundFlow.method 加入 EASTMONEY_PUSH2HIS_HISTORICAL（fundFlow 历史回补分支新口径）
3. tools/acceptance/accept.py：INV-ENUM-SOURCE-METHOD 在模块 status != FINAL 时跳过枚举必填检查（fail-closed 语义下 null 字段是预期，不应触发必填枚举）

### 数据/报告（commit 01224c9）
- backfill_loop pwsh-48 (cache 版)：07-20~08-13 共 18 日 WRITTEN + 08-13 NO_CHANGE（首日 THS 短暂受限）
- archive seed pwsh-53：track-board-close 100+ 笔、limit-up-pool 15 笔（覆盖 07-27~08-13）
- 07-20~08-13 snapshot 含 THS 板块指数 + 涨停池真实数据
- work/SMI_R12_P0*_Review_*: P0.5 复审材料存档
- work/acceptance/p1_post_*.json: 三次验收报告（首版 + 枚举修复 + INV 修复后）

## 二、验收结果（21 个日期全量）

### INV-跨模块不变量（9 条）
- 21/21 日期全部 INV 闭合 ✅（修复前因 tracks UNAVAILABLE 时枚举必填检查触发所有日 NOT_CLOSED）

### 模块通过情况
| 模块 | 通过 | 失败 | 失败日期 | 原因 |
|---|---|---|---|---|
| marketIndex | 21/21 | 0 | — | ✅ |
| turnover | 20/21 | 1 | 07-20 | PREVIOUS_METHOD_MISMATCH 缺 crossMethodReference |
| sentiment | 1/21 | 20 | 19 日回补日 + 08-14 | PARTIAL（涨跌家数无免费源）+ 早期 5 日 UNAVAILABLE（涨停池早期窗口外）+ 08-14 缺 limitSealRatePct |
| sectorPerformance | 9/21 | 12 | 07-23/27/29/31/08-03-07/10-12 | 12 日 Bottom5[0].changePct 不为负（数据采集异常） |
| fundFlow | 1/21 | 19 | 19 日回补日 | push2his 主机级封禁持续，EASTMONEY_PUSH2HIS_HISTORICAL 唯一历史接口被封；探测器每 5 分钟探测解封 |
| northbound | 21/21 | 0 | — | ✅ |
| margin | 21/21 | 0 | — | ✅ |
| tracks | 1/21 | 20 | 19 日回补日 + 08-14 | archive 底座限制（board-flow/membership 仅当日无历史，excessReturn20d/redStockRatio 无源） |
| summary | 21/21 | 0 | — | ✅ |

## 三、已知诚实缺口（待 ChatGPT 裁决）

1. fundFlow 19 日 UNAVAILABLE：东财 push2his 主机级封禁（2026-08-16 实测，从 08-15 晚持续约 3+ 小时）；唯一历史资金流免费接口；push2delay 仅返回最近 1 个交易日（不提供历史）；THS 历史资金流无 AJAX 接口。
2. sentiment 涨跌家数缺：riseCount/fallCount/flatCount 无免费源（诚实的 SPEC 限制，不伪造）。
3. sentiment 早期 5 日（07-20~07-24）涨停池 UNAVAILABLE：东财涨停池只保留近期窗口（~07-27 起）。
4. tracks 主流量化指标缺：mainNetInflow/continuousInflowDays 仅当日（archive 不支持历史），excessReturn20d（缺 HS300 archive 源），redStockRatio（缺当日行情源）。
5. tracks 早期 5 日（07-20~07-24）涨停池缺：同上东财保留窗口限制。
6. turnover 07-20：缺 crossMethodReference 字段（手动跨口径参考未补）。
7. sectorPerformance 12 日 Bottom5 异常：部分板块涨跌幅数据采集异常（top 排名但 bottom 取到正值），需诊断板块指数序列质量。

## 四、请复核

1. P1-001（spec 加 EASTMONEY_PUSH2HIS_HISTORICAL）是否可判 CLOSED；
2. P1-002（accept.py INV-ENUM-SOURCE-METHOD 跳过非 FINAL）逻辑漏洞修复是否可判 CLOSED；
3. 上文七大诚实缺口是否归类正确、是否需要补充说明或调整送审口径；
4. push2his 封禁期间的 fundFlow 缺口是否需要标记为临时缺口（待解封后补）/ 或调整验收标准（接受当前 1/21 fundFlow PASS）；
5. 若本轮可收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
