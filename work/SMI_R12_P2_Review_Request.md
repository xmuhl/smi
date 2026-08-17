# SMI R12 P2 复审：历史数据回补收口与剩余缺口裁决

- 轮次：R12 P2（P1 剩余缺口分类 + provenance 收口 + 送审裁决）
- 送审输入 commit：`715938a`（干净输入树，含 page_check.js 探针/交接文档/P1 复审材料）
- 送审报告 commit：`189a635`（21 日全量验收，dirty=false）+ `ba032a7`（canonical baseline 恢复）
- 前置复核链：…→ P0.5（收敛）→ R12 P1（HOLD，8 NOT_CLOSED）

## 一、本轮改动清单

### 代码/工具（commit 715938a）
1. `tools/acceptance/page_check.js`：页面侧验收探针（P4 部署后执行 `window.__smiPageCheck()`）
2. `work/SMI_HANDOVER.md`：任务交接手册（含第 7 节新对话目标模板）
3. `work/SMI_R12_P1_Review_Request.md` / `SMI_R12_P1_Review_Report.md`：P1 复审材料归档

### 报告（commits 189a635 / ba032a7）
- `work/acceptance/p1_r2_clean_full.json`：**干净输入树 21 日全量验收，dirty=false**（P1-009 收口）
- `work/acceptance/baseline-report.json`：恢复 canonical 为 21 日全量报告（不再被单日报告污染）

## 二、P1-009 provenance 收口完成情况

| 要求 | 状态 |
|---|---|
| 输入树固定为干净 commit | ✅ HEAD=`715938a`（代码+数据+工具全部提交） |
| 工作区 clean 后运行 | ✅ `git status --porcelain` 为空 |
| `repoCommit == evaluatedCommit == 固定输入 commit` | ✅ 均为 `715938a4439701d5db0b11a3c64a4cf2403a089a` |
| `dirty == false` | ✅ |
| 报告含 21 日 | ✅ |
| 报告单独提交 | ✅ `189a635` |
| canonical baseline 恢复 | ✅ `ba032a7` |

## 三、验收结果（21 个日期全量，权威 report: p1_r2_clean_full.json）

| 模块 | PASS | FAIL | 失败日期 | 缺口性质 |
|---|---|---|---|---|
| marketIndex | 21/21 | 0 | — | ✅ |
| turnover | 21/21 | 0 | — | ✅（P1-008 已修） |
| northbound | 21/21 | 0 | — | ✅ |
| margin | 21/21 | 0 | — | ✅ |
| summary | 21/21 | 0 | — | ✅ |
| sectorPerformance | 19/21 | 2 | 07-27, 07-31 | **普涨日契约边界**（Bottom5 符号） |
| sentiment | 1/21 | 20 | 19 回补日 + 08-14 | 结构性诚实缺口（涨跌家数无免费源） |
| fundFlow | 1/21 | 19 | 19 回补日 | push2his 封禁 + 结构性缺个股榜单 |
| tracks | 1/21 | 20 | 19 回补日 + 08-14 | 结构性（量化输入底座） |

## 四、剩余缺口分类（请 ChatGPT 裁决）

### A. sectorPerformance 2 日 —— 普涨日 Bottom5 符号契约（非数据质量问题）
- 日期：2026-07-27、2026-07-31
- **实测证据**（读快照 `web/public/data/daily/2026/...`）：
  - 07-27 industryBottom5 = [油气开采-3.12, 保险-0.69, **银行+0.33, 证券+0.71, 港口航运+0.95**]，conceptBottom5 全为正
  - 07-31 industryBottom5[4]=+0.15，conceptBottom5[2]=+0.0、[3]=+0.21
  - 当日为全市场普涨日，THS 板块指数历史数据真实
- 结论：Bottom5 全负符号契约在普涨日**自然不可满足**，非采集质量问题
- 建议裁决：标注为已知边界（普涨日豁免）或调整标准

### B. sentiment 市场宽度 —— P1-006 结构性诚实缺口
- 20 日 PARTIAL/UNAVAILABLE，`riseCount/fallCount/flatCount` 为 null
- 根因：涨跌家数无免费历史源（诚实缺口，不伪造）
- 建议裁决：缩短承诺历史范围 / 引入 historical profile / 保持 UNAVAILABLE

### C. fundFlow —— P1-003 push2his 封禁 + 结构性缺个股榜单
- **2026-08-17 实测**：push2ex=OK，push2his=ERR（连接被断），push2=ERR → push2his 主机级封禁**仍持续**
- 即使解封：历史路径仍缺 `stockInflowTop10/stockOutflowTop10`（无可用历史批量源），半成品标 FINAL 会违反六榜单标准
- 当前实现历史状态为 UNAVAILABLE/PARTIAL（fail-closed，符合 P1-003 裁决方向）
- 建议裁决：接受 PARTIAL/UNAVAILABLE 语义，作为已知边界

### D. tracks —— P1-007 结构性缺口
- 20 日 UNAVAILABLE，缺 mainNetInflow / continuousInflowDays / excessReturn20d / redStockRatio / effectiveFrom / effectiveTo / sourceSystem
- 根因：跨度量化输入底座不完整（board-flow/membership 仅当日无历史，excessReturn20d 缺 HS300 archive 源）
- 建议裁决：明确 historical profile / 最早支持日 / 保持 UNAVAILABLE

## 五、请复核

1. P1-009 provenance 收口是否满足两提交纪律（可 CLOSED）；
2. P1-002（INV-ENUM-SOURCE-METHOD applyWhenStatus 写回 spec）是否可 CLOSED；
3. sectorPerformance 2 日是否为普涨日已知边界（而非数据质量）；
4. 结构性缺口 B/C/D 是否可接受"已知边界/产品裁决"标注，还是必须补源/缩短历史承诺；
5. 若本轮可收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"或列出仍需闭环项。
