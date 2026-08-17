# SMI 项目任务交接手册

> 生成时间：2026-08-17 10:30
> 来源会话：多Agent修订项目至范本效果 (session-46a0e77b-3927-4ac2-aa07-1c1551cb340f)
> Git 分支：feat/p1-collector-revamp
> 工作目录：C:\Users\huangl\Desktop\SMI\smi

---

## 1. 项目总览

**目标**：A股收盘全景 Web 看板（Vue3+Vite+TS + Python/AKShare 采集 + Cloudflare Pages），**从当前状态自动推进 P1-P4 直至网站上线**：完成全部历史数据回补与验收 → 前端对齐范本 → Cloudflare Pages 部署（双域 smi-6s2.pages.dev + smi.gorestart.cn）→ 每日链路硬化 → **通知用户进行人工验收**。

**架构**：Python(AKShare) 采集 → web/public/data/daily/YYYY/YYYY-MM-DD.json 快照（9 大模块）→ Vue3 前端 → Cloudflare Pages（smi-6s2.pages.dev / smi.gorestart.cn 双域）。

**9 大模块**：marketIndex / turnover / sentiment / sectorPerformance / fundFlow / northbound / margin / tracks / summary

---

## 2. 已完成的工作

### 2.1 P0 验收平台（已收敛送审完毕）

- 验收器 `tools/acceptance/accept.py` v2（~125KB）
- 验收标准 `docs/acceptance/template-standard.json`（version=2，311 条 referenceAssertions + 9 条 crossModuleInvariants）
- 30 个测试（`tools/acceptance/test_accept.py`）
- ChatGPT 6 轮送审（P0→P0.5），P0.5 裁决"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"
- 范本参考日 07-17 永久 PASS

### 2.2 P1-P3 采集器代码（全部完成并提交 git）

| 模块 | 代码文件 | 关键特性 |
|---|---|---|
| sentiment | `collector/modules/sentiment.py` | 封板率/最高连板/ST 拆分，东财涨停池（push2ex） |
| fundFlow | `collector/modules/fund_flow.py` | 历史回补分支 push2his daykline（6 并发，12 连续失败熔断） |
| northbound | `collector/modules/northbound.py` | OFFICIAL_REPLACEMENT 季度持仓 PIT（5 交易日延迟） |
| marketIndex | `collector/modules/market_index.py` | 并发 6 拉取 |
| sectors | `collector/modules/sectors.py` | THS 板块历史指数 + 跨日缓存（`_THS_HIST_CACHE`） |
| tracks | `collector/modules/tracks.py` | archive 计算 MA/RPS60/连续流入日等 |
| summary | `collector/calculators/summary.py` | 8 段文案生成器 |
| 前端面板 | `web/src/modules/*.vue` | TrackMonitorPanel(16列)/SentimentPanel/NorthboundPanel 等 |

### 2.3 P1 数据回补与修复（已提交 5 个 commit）

| 修复项 | 状态 | Commit | 说明 |
|---|---|---|---|
| P1-002: INV-ENUM 状态豁免写回 spec | ✅ CLOSED | 1279f94 | `applyWhenStatus` machine-readable，accept.py 消费配置 |
| P1-003: fundFlow 历史缺个股榜单改 PARTIAL | ✅ CLOSED | 1279f94 | 不再伪造 FINAL + schema validator 支持 |
| P1-004: THS 板块历史并发修复 | ✅ CLOSED | 47b3c3d + 53246d9 | 根因：akshare mini_racer.dll 并发崩溃，改串行（`_THS_HIST_CONCURRENCY=1`） |
| P1-008: 07-20 turnover 补 crossMethodReference | ✅ CLOSED | 92b2ca4 | 07-20 turnover 首日 PASS |
| P1-009: 测试断言更新 | ✅ CLOSED | 4e1ce61 | test_accept 30/30 全绿 |

### 2.4 关键数据回补成果

- 19 个历史交易日（07-20~08-13）全量回补完成（cache 版 backfill_loop）
- archive seed 完成：track-board-close 100+ 笔、limit-up-pool 15 笔（07-27~08-13）
- 07-20~08-13 snapshot 含 THS 板块指数 + 涨停池真实数据

---

## 3. 当前验收状态（21 个日期全量）

```
PASS: 2026-07-17（范本参考日 — 永久 PASS）
FAIL: 其余 20 个日期

模块通过情况：
  marketIndex      21/21 ✅（全 PASS）
  turnover         21/21 ✅（全 PASS — P1-008 修复后）
  northbound       21/21 ✅（全 PASS）
  margin           21/21 ✅（全 PASS）
  summary          21/21 ✅（全 PASS）
  sectorPerformance 19/21 ✅（12→2，P1-004 修复，剩 2 日全市场普涨）
  sentiment         1/21 ❌（结构性缺口）
  fundFlow          1/21 ❌（push2his 封禁 + 结构性缺口）
  tracks            1/21 ❌（结构性缺口）
```

---

## 4. 待处理的工作（完整范围：P1-P4，直到上线）

### 最终完成条件（全部达成后通知用户人工验收）
1. 21 个历史日期全量验收通过（或所有缺口已明确标注为已知边界/产品裁决）
2. 前端 9 大模块面板正确展示所有数据（含跨口径标注、季度持仓分支、封板率/连板等新字段）
3. Cloudflare Pages 构建成功，smi-6s2.pages.dev + smi.gorestart.cn 双域可访问
4. 每日链路硬化（daily_update.ps1 定时任务就绪）
5. **通知用户进行人工验收并确认**

### P1 级（数据回补验收）

**P1-005：07-20~07-24 涨停池历史覆盖缺口**
- 影响模块：sentiment、tracks
- 原因：东财涨停池保留窗口 ~07-27 起，之前 5 日无数据
- 建议方案：备选数据源或产品裁决

**P1-006：sentiment 历史市场宽度不完整**
- 影响：20 日 FAIL（riseCount/fallCount/flatCount 全部为 null）
- 根因：涨跌家数无免费历史源（诚实缺口），需产品裁决

**P1-007：tracks 历史量化输入底座仍不完整**
- 影响：20 日 FAIL（mainNetInflow/continuousInflowDays/excessReturn20d/redStockRatio 等缺）
- 根因：结构性，需产品裁决

**P1-004 遗留：sectorPerformance 2 日 Bottom5 契约冲突**
- 日期：2026-07-27, 2026-07-31，全市场普涨日无法满足 Bottom5 全负
- 建议：调整标准或标注已知边界

**P1-009 provenance：验收报告干净输入树绑定**
- 当前 dirty=true，需在干净工作区重新跑验收并提交

### P2 级（ChatGPT 送审 + 迭代修复）

- P1 剩余缺口送 ChatGPT P2 复审（含诚实缺口分类）
- 按复审结果修复 P2 发现问题
- 迭代直至 ChatGPT 收敛

### P3 级（前端面板对齐范本）

- 前端 9 大模块面板代码已基本完成，需确认所有新字段正确展示
- 跨口径标注（COMPARABLE/PREVIOUS_METHOD_MISMATCH）
- 北向 OFFICIAL_REPLACEMENT 季度持仓分支展示
- 封板率/连板数展示、赛道监测 16 列
- 页面侧验收探针 window.__smiPageCheck()（tools/acceptance/page_check.js）

### P4 级（部署上线）

- web 目录下 npm run build 构建验证
- Cloudflare Pages 部署（Wrangler 或 Pages Dashboard）
- 双域：smi-6s2.pages.dev（默认）+ smi.gorestart.cn（自定义域名）
- 自定义域名绑定：Cloudflare + 阿里云云解析 DNS（CNAME 记录）
- 微信风控规避（自定义域名 smi.gorestart.cn 已被实测可通过）
- 每日链路硬化：ops/daily_update.ps1（清代理 + close_snapshot + 验收）
- **部署完成后通知用户进行人工验收**## 5. 核心技术踩坑（必读）

### 5.1 环境铁律
- **跑采集前必须清代理**：`$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'`（否则 v2rayN 代理挂起）
- 组合 pytest 可能挂起（含网络测试），按文件单独跑

### 5.2 数据源连通性

| 数据源 | 主机 | 状态 | 说明 |
|---|---|---|---|
| 东财涨停池 | push2ex.eastmoney.com | ✅ 可用 | `stock_zt_pool_em` 历史窗口内可用（~07-27 起） |
| 东财历史资金流 | push2his.eastmoney.com | ❌ 封禁 | 主机级封禁（连接被断），8+ 小时未解封 |
| 东财延迟行情 | push2delay.eastmoney.com | ✅ 可用 | 仅最近 1 个交易日，无历史 |
| 东财实时行情 | push2.eastmoney.com | ❌ 封禁 | 同 push2his |
| 同花顺指数 | q.10jqka.com.cn / d.10jqka.com.cn | ✅ 可用 | 板块历史指数，但**必须串行**（见下文） |
| 新浪行情 | hq.sinajs.cn | ✅ 可用 | |
| 腾讯行情 | qt.gtimg.cn | ✅ 可用 | |

### 5.3 THS 关键踩坑（最重要！）

**```diff
- 错误认知：THS 板块历史指数在并发下拉取是"限流/SSL EOF"
- 真实根因：akshare 内部用 py_mini_racer（V8 JS 引擎）解析服务端数据，
  多线程并发调用导致 mini_racer.dll 进程级崩溃
- 修复：并发度必须设为 1（串行）
```**

串行实测：~1.3s/板块，465 板块 ≈ 13 分钟/日，完全稳定。

### 5.4 回补循环

- 缓存版：`collector/jobs/backfill_loop.py`（单进程降序）
- 启用 THS 跨日缓存（`_THS_HIST_USE_CACHE=True`），首日全窗口拉取后后续日命中缓存
- 但 fundFlow 每日本身独立拉取（无缓存），无 push2his 无法回补

### 5.5 涨停池保留窗口

东财涨停池（`stock_zt_pool_em`）只保留近期数据（~07-27 起），早期日期返回 0 行。这是东财服务端限制，不可绕过。

### 5.6 API 枚举验收

验收器的 `INV-ENUM-SOURCE-METHOD` 检查各模块枚举字段：
- fundFlow.method 允许值：`TONGDAXIN_LEGACY` / `EASTMONEY_MAIN_FORCE` / `THS_MAIN_FORCE` / `EASTMONEY_PUSH2HIS_HISTORICAL`
- sectorPerformance.method 允许值：`TONGDAXIN_LEGACY` / `EASTMONEY` / `THS` / `THS_HISTORICAL_INDEX`
- 修改枚举需同步更新 `docs/acceptance/template-standard.json` 的 allowedEnums

---

## 6. Git 仓库状态

```
分支: feat/p1-collector-revamp
基础: 60617f9 perf(p1): 板块历史跨日缓存+单进程降序回补循环
领先 5 commits:
  1279f94  P1-002 + P1-003（INV-ENUM spec + fundFlow PARTIAL）
  4e1ce61  P1-009 测试断言更新
  47b3c3d  P1-004 THS 串行修复（并发=1）
  53246d9  P1-004 12 日 sector 修复数据
  92b2ca4  P1-008 07-20 turnover crossMethodReference
Remote: github.com/xmuhl/smi（已推送）
```

**未提交的修改**：`work/acceptance/p1_post_sector_fix.json`（最新验收报告）

---

## 7. 新对话目标模板

在新对话中，读取此文档后，用以下内容创建 goal：

```
create_goal
objective: "SMI 项目 P1-P4 全自动推进直至网站上线并通知用户人工验收。工作目录 C:\Users\huangl\Desktop\SMI\smi，git 分支 feat/p1-collector-revamp（已领先 5 commits）。当前验收状态：marketIndex/turnover/northbound/margin/summary 5 模块全 PASS（21/21），sectorPerformance 19/21，sentiment 1/21、fundFlow 1/21、tracks 1/21。剩余任务（按顺序）：(1) P1 剩余缺口修复（涨停池覆盖/P1-006/P1-007/P1-004 普涨日/P1-009 provenance 绑定）→ (2) 全量验收通过后送 ChatGPT P2 复审 + 迭代修复直至收敛 → (3) P3 前端确认对齐范本（page_check.js 探针验收）→ (4) P4 构建+部署 npm run build → Cloudflare Pages（smi-6s2.pages.dev + smi.gorestart.cn）→ 域名绑定 → 每日链路硬化 → (5) 部署完成后通知用户人工验收。环境铁律：清代理、THS 必须串行（并发=1）、组合 pytest 按文件单独跑、git 两提交法。每轮自主执行：按清单派发 flash 子 agent（≤4 项改动，禁验证/网络）、主控后台验证并收割、ChatGPT 送审、git 提交推送。"
max_goal_rounds: 80
```

> 注意：创建 goal 后系统会自动接收 goal_round 通知推进。如果推进停滞或用户询问进度，应如实汇报当前阶段和阻挡原因，不要假装完成。## 8. 关键命令速查

```powershell
# 清代理 + 全量验收
$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'; $env:PYTHONPATH='.'
python tools/acceptance/accept.py --all --report work/acceptance/report.json

# 单日验收
python tools/acceptance/accept.py --date 2026-07-27

# 回补单日（--force 强制重采）
python -m collector.jobs.backfill_loop --start 2026-07-27 --end 2026-07-27 --force

# 单文件测试（避免组合挂起）
python -m pytest tools/acceptance/test_accept.py -q
python -m pytest collector/tests/test_core.py -q
python -m pytest collector/tests/test_fundflow_history.py -q

# 提交规范（两提交法）
git add <code files> && git commit -m "fix(p1): 说明"
git add <data files> && git commit -m "data(p1): 说明"
```

---

## 9. 文件索引

| 路径 | 说明 |
|---|---|
| `docs/acceptance/template-standard.json` | 验收标准单一真源 |
| `tools/acceptance/accept.py` | 验收器 v2 |
| `tools/acceptance/test_accept.py` | 验收器测试（30 个） |
| `collector/jobs/backfill_loop.py` | 回补循环 |
| `collector/modules/sectors.py` | THS 板块历史（串行，`_THS_HIST_CONCURRENCY=1`） |
| `collector/modules/fund_flow.py` | 资金流（push2his 被封） |
| `collector/modules/sentiment.py` | 情绪（涨停池 push2ex 可用） |
| `collector/modules/tracks.py` | 赛道监测（archive 底座） |
| `collector/adapters/eastmoney_delay.py` | 东财延迟行情适配器 |
| `work/SMI_R12_P1_Review_Request.md` | P1 送审请求 |
| `work/SMI_R12_P1_Review_Report.md` | ChatGPT P1 复审报告（HOLD） |
| `work/acceptance/p1_post_sector_fix.json` | 最新验收报告 |
| `tmp/run_archive_seed.ps1` | archive 种子脚本 |
| `tmp/p1_post_backfill_flow2.ps1` | 回补后收尾流水线 |
