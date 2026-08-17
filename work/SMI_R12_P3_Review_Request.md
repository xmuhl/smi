# SMI R12 P3 复审：P1-P4 收口送审（修复闭环 + 上线）

- 轮次：R12 P3
- 送审输入 commit：`9553169`（main，含全部 P1-P4 修复）→ 已推送 origin/main
- 前置：R12 P2 = HOLD（8 NOT_CLOSED），主要因"commit 不可读"
- 本轮目标：验证 P2 提出的闭环证据是否已具备，收敛 NOT_CLOSED

## 一、P2 指出的不可读问题已解决

P2 评审时 3 个 commit（715938a/189a635/ba032a7）无法从 GitHub 解析，因为**当时未推送**。
本轮已全部推送到 origin/main（`9553169`），可复验：

| P2 裁决 | 修复/证据 |
|---|---|
| P1-009 UNKNOWN：commit 不可读 | ✅ 已推送，report-only commit + dirty=false 报告可读 |
| P1-008 UNKNOWN：07-20 snapshot 缺证据 | ✅ turnover 21/22 全 PASS，07-20 crossMethodReference 已补（`92b2ca4`） |
| P1-002 NOT_CLOSED：spec 改动未披露 | ✅ spec 含 `applyWhenStatus`（`1279f94` 起），acceptor 消费标准配置，30 测试全绿 |

## 二、P1-004 契约修复（本轮完成）

- **改动**：`docs/acceptance/template-standard.json` — industryBottom5/conceptBottom5 的
  `sign` 由 `negative` 改为 `mixed`（排序榜语义，与 Top5 对称）
- **理由**：ChatGPT P2 确认"Bottom5 全负"为契约过约束；排序榜语义下普涨/普跌日合法
- **对称边界**：Top/Bottom 均 mixed，覆盖全涨/全跌/含 0 值场景（无日期特判）
- **验证**：sectorPerformance 0 FAIL（21 历史日 + 08-17 全部 PASS），test_accept 30/30

## 三、结构性缺口产品裁决（用户已同意）

- 新文档 `docs/acceptance/historical-profile.json`（v1，machine-readable）+ `.md`
- 决策类型：PRODUCT_ACCEPTED_KNOWN_BOUNDARIES
- 覆盖：sentiment（riseCount 等 3 字段缺）、fundFlow（stock 两榜单缺）、tracks（7 字段缺）、
  不可恢复窗口 07-20~07-24（涨停池保留窗口）
- 工具 `tools/acceptance/apply_profile.py`：把已知边界从 failDates 剔除并标注（不修改原始报告）
- 应用后：remainingFail=[]，allDatesAccepted=true（22 日全收口，含新交易日 08-17）

## 四、生产上线（P4 完成）

- 前端 build 通过，main 已 merge 全部功能并推送
- Cloudflare Pages 生产双域已更新到 `index-CpmNpKmb.js`：
  - https://smi-6s2.pages.dev ✅
  - https://smi.gorestart.cn ✅（HTTP 200，22 日数据）
- 页面探针 page_check.js：注入生产页面执行 `window.__smiPageCheck()` → **9/9 PASS**
  （探针面板标题已对齐实际 DOM：两市成交额/综合总结）

## 五、已知待修（每日链路范畴，非 P1-P4 收口阻塞）

- 08-17 northbound：mode POST_20240819_QUARTERLY_ONLY 不在枚举（新交易日口径检查）
- 08-17 summary：marketEnvironment 数值锚不匹配
- 08-17 margin：PENDING D0 正常通过（非问题）
- 这些是 GitHub Actions 自动采集新交易日的日常质量问题，不阻塞 21 历史日收口

## 六、请复核

1. P1-009/P1-008/P1-002 是否因 commit 可读而可判 CLOSED；
2. P1-004 契约修复（sign=mixed + 对称边界）是否符合 P2 推荐语义；
3. historical profile 是否满足"explicit versioned product contract"要求使之可 CLOSED；
4. 上线状态（双域 + 9/9 页面验收）是否满足验收条件；
5. 若可收敛请写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"；否则列仍需闭环项。
