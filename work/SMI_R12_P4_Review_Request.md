# SMI R12 P4 复审：P3 四项修复闭环送审

- 轮次：R12 P4
- 送审输入 commit：`576a8ba`（main，clean，含 P3-001/002/003 全部修复）→ 已推送 origin/main（当前 HEAD=`c30e742` = P3-004 报告 commit，输入树=`576a8ba`）
- 前置：R12 P3 = HOLD（4 NOT_CLOSED：P3-001/002/003/004）

## 一、P3 四项修复逐项闭环

### P3-001（P1）— profile 应用器模块级因果接受 ✅
- 重写 `tools/acceptance/apply_profile.py` v2：
  - 从 source snapshot 判断 missingFields 真实缺失（不再从验收结果对象猜）
  - 模块级因果接受：仅当该日所有 FAIL 模块都属合法接受的 profile 边界才移除该日
  - **禁止 date-level 先 discard**（不再掩盖非 profile 失败）
  - 日期适用范围：`appliesToRanges`/appliesThrough=08-14（历史 profile 不扩张到新交易日）
  - unrecoverable range-local（逐 range 用各自 affectedModules）
- **验证**：v2 结果 remainingFail=['2026-08-14','2026-08-17']
  - 08-14 sentiment（FINAL 缺 sealRate）→ 不再被 rise/fall/flat profile 误豁免（status_not_allowed）
  - 08-17 northbound/summary（not_in_profile）→ 诚实保留
  - 08-17 超 appliesThrough → outside_applicability
- **回归**：已随 v2 输出 rejectedModuleDetail 逐模块可复验

### P3-002（P1）— 08-14 margin D0/D+1 生命周期 ✅
- 根因：08-14 margin 保持 PENDING，08-17 到来后未回补；GitHub Actions 的 t1-reconcile 曾运行失败（把 margin 置 ERROR）
- 修复：`t1_reconcile --date 2026-08-14` 手动回补 → margin=FINAL，marginBalance=26655.01，revision=9
- 同时 merge 保留了本机正确 FINAL（覆盖 remote 的 ERROR）
- **验证**：08-14 margin failDates=0，验收 PASS

### P3-003（P2）— 前端历史边界 UI notice 落地 ✅
- `web/src/modules/SentimentPanel.vue`：rise/fall/flatCount 全 null 且 status∈{PARTIAL,UNAVAILABLE,PENDING} 时显示
  『市场宽度（涨跌家数）无历史源，仅显示可采集指标（历史覆盖 Profile 已知边界）』
- `web/src/modules/TrackMonitorPanel.vue`：status=UNAVAILABLE 时显示
  『赛道量化指标历史不可用（输入底座不足），仅展示可用归档数据（历史覆盖 Profile 已知边界）』
- FundFlowPanel 已有『暂无数据（历史免费源不可用）』（P3 评审确认基本符合）
- **验证**：`npm run build` 通过，生产已部署 `index-BmPoS2I9.js`（含 UI notice）

### P3-004（P2）— 部署 provenance 证据绑定 ✅
- 最终 clean 输入树：`576a8ba`（main，前=9553169 后的全部 P1-P4 + P3 修复）
- `work/acceptance/p1_r8_final_clean.json`：
  - repoCommit=evaluatedCommit=576a8ba，dirty=false，22 日全量
- `work/acceptance/p1_r8_final_profile_applied.json`：v2 profile 应用（remainingFail=['2026-08-14','2026-08-17']）
- 报告单独提交：`c30e742`
- 生产双域已部署 `index-BmPoS2I9.js`，22 日数据

## 二、当前诚实验收状态（p1_r8_final_clean.json，dirty=false）

| 模块 | 失败日 | 性质 |
|---|---|---|
| marketIndex / turnover / sectorPerformance / margin | 0 | ✅ 全过 |
| sentiment / tracks | 21 | 结构性边界（profile 接受） |
| fundFlow | 19 | push2his 封禁+结构（profile 接受） |
| northbound / summary | 1（08-17） | 新交易日数据质量（诚实保留，非边界） |

- profile v2 应用后：19 个历史日（07-20~08-13）按已知边界接受；remainingFail=['2026-08-14','2026-08-17'] 诚实保留
- 08-14：sentiment FINAL 缺 sealRate + tracks 结构性 → 非完全 profile 边界，保留
- 08-17：northbound/summary 非 profile + sentiment 缺 sealRate → 保留

## 三、请复核

1. P3-001 profile v2 是否满足"模块级因果接受"且不再假阳性（可 CLOSED）；
2. P3-002 08-14 margin FINAL 是否闭环（可 CLOSED）；
3. P3-003 前端 UI notice 是否满足显式降级语义（可 CLOSED）；
4. P3-004 最终 clean SHA 证据（576a8ba，dirty=false + 单独报告 commit）是否可 CLOSED；
5. remainingFail（08-14/08-17）作为诚实保留的非边界缺口是否需立即处理，还是可标注为每日链路待修清单；
6. 若全部闭环请写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"，否则列剩余项。
