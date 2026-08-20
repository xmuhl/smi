# SMI — Stock Market Intelligence

## 项目概述

A股收盘全景 Web 看板。Python 采集 + Vue3 前端 + Cloudflare Pages 托管。
每日自动采集 9 大模块收盘数据，生成 JSON 快照，构建部署到 Pages。
R12 起（2026-08-20）主赛道按每日全市场板块数据动态筛选（范本第 8 表口径）。

## 环境铁律（踩坑必读）

- **采集前必须清代理**：`$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'`（否则 v2rayN 代理导致挂起）
- **THS/mini_racer 接口禁重试并发**：akshare 内部 py_mini_racer.dll 并发会进程级崩溃；所有 THS 路径的 netguard 必须 `retries=0`（历史拉取串行，`_THS_HIST_CONCURRENCY=1`）
- **联网采集一律走 net_guard**：`from collector.netguard import net_guard` 装饰（单线程 + future 超时 + 孤儿线程 daemon 化）；无护栏的 akshare 直调可能 60 分钟静默挂起（2026-08-18 事故根因）
- **部署环境 Node 必须 ≥22**：wrangler 4.122.0 的 engines 硬要求；Node 20 下 `npm ci` 仅 EBADENGINE 警告但运行时退出（2026-08-17~20 部署全失败的根因）
- **git 两提交法**：先提交代码/数据（输入树），再单独提交验收报告（report-only commit）
- 全量 pytest 现可安全直跑（~6s）：`python -m pytest collector/tests/ -q`（R12 修复了 test_core 的 sys.modules["akshare"] 泄漏——此前该泄漏使后续测试真实联网 16 分钟/个）

## 架构

```
Python(AKShare) 采集 → web/public/data/daily/YYYY/YYYY-MM-DD.json (9 大模块)
→ Vue3 前端 → Cloudflare Pages (smi-6s2.pages.dev / smi.gorestart.cn 双域)
```

9 大模块：marketIndex / turnover / sentiment / sectorPerformance / fundFlow / northbound / margin / tracks / summary

### 主赛道（tracks，R12 动态化）

- **数据底座**：`industry-universe-snapshot` 归档（每日 THS 行业汇总全市场 ~90 板块的成交额/净流入/涨跌家数 + 东财 BK 代码映射）；close-snapshot 在 tracks 采集前预写当日 universe（破解 cron 时序），archive-raw 阶段 5 幂等去重（`ALREADY_ARCHIVED`）、冲突降级 SKIP
- **选池**（`config/tracks.yaml` v3.0 selection）：近 5 日成交额全市场排名 ≤8 且当日净流入>0 的行业板块 = 动态候选；与 4 条种子赛道（高股息中特估/电力/医药生物/半导体AI算力，无评分特权）合并去重（名称精确/规范化匹配，禁子串）
- **指标口径**：资金类（排名/净流入/连续净流入天数/红盘占比/涨停率分母）优先 universe；close 序列类（MA/RPS/60日收益）用 track-board-close 归档（候选首次入选由 archive-raw 阶段 6 回补 THS 历史，幂等）
- **评分与判定**：`config/track-scoring.yaml` 四维度权重 25/35/25/15（资金/趋势/情绪/逻辑）；`calculators/tracks._decide_four` 四级判定 CORE_MAIN/SECONDARY_MAIN/SHORT_LINE/PULSE_AVOID；定性双列（催化/业绩）无枚举分级前不计 coverage 分母（信息性展示）
- **元数据**：boardMetadata 字典（8 板块定性文案+aliases）；未配置候选定性留空（fail-closed）

## 生产域

| 域名 | 用途 | 状态 |
|------|------|------|
| `smi-6s2.pages.dev` | Cloudflare Pages 默认域 | ✅ 生产 |
| `smi.gorestart.cn` | 自定义域名（阿里云 CNAME） | ✅ 生产 |

## 自动更新链路（GitHub Actions，全部 Node 22）

| 工作流 | 触发 | 功能 |
|--------|------|------|
| `close-snapshot.yml` | Cron 工作日 16:23 CST | 采集（含 universe 预写+动态选池）→ commit → build → Pages 部署 → 站点新鲜度自检 |
| `archive-raw.yml` | Cron 工作日 16:35 CST | 归档 universe/涨停池 + 候选 THS 历史回补 → 部署 → jsonl md5 自检 |
| `t1-reconcile.yml` | Cron 工作日 10:17/18:17 CST | 补昨日两融（T+1）→ 部署 → 自检 |
| `manual-backfill.yml` | 手动 | 回补指定日 → 部署 → 自检 |
| `ci.yml` | Push to main | 类型检查 + 测试 + 构建验证 |

- 自检口径：改写 latest.json 的 workflow 断言 `updatedAt ≥ JOB_START_UTC`；archive-raw（不改写 latest.json）比对站点与 dist 的 jsonl md5
- 全部数据写入 workflow 共用 concurrency group `smi-data-write` 串行；提交冲突（rebase conflict）用再次 dispatch 化解
- 部署失败会打红 workflow（GitHub 默认通知）——连续红 = 发布链路断，人工介入

## 关键命令速查

```powershell
# 清代理 + 全量验收
$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'; $env:PYTHONPATH='.'
python tools/acceptance/accept.py --all --report work/acceptance/report.json

# 单日验收
python tools/acceptance/accept.py --date YYYY-MM-DD

# 全量测试（~6s，零联网）
python -m pytest collector/tests/ -q

# 回补单日
python -m collector.jobs.backfill_loop --start YYYY-MM-DD --end YYYY-MM-DD --force

# 两融回补
python -m collector.jobs.t1_reconcile --date YYYY-MM-DD

# 强制重新部署（数据无变化时；deploy 失败恢复用）
# GitHub → Actions → close-snapshot → Run workflow → deploy=true
```

## 验收

- 验收器：`tools/acceptance/accept.py`（读标准 `docs/acceptance/template-standard.json`）
- 历史覆盖 Profile：`docs/acceptance/historical-profile.json`（产品裁决已知边界）
- 最新 clean 报告：`work/acceptance/p1_r9_final_c7.json`（dirty=false，绑定 c7de51b）
- 页面探针：`tools/acceptance/page_check.js`（`window.__smiPageCheck()`）

## 已知边界（产品裁决 v1 + R12 运行时观察项）

| 模块 | 历史缺口 | 状态 |
|------|----------|------|
| sentiment | riseCount/fallCount/flatCount 等无免费历史源 | PARTIAL/UNAVAILABLE |
| fundFlow | stockInflowTop10/OutflowTop10 无历史源；push2his 封禁 | UNAVAILABLE/PARTIAL |
| tracks | universe 底座已修复资金/红盘输入；excessReturn20d 无 HS300 归档源（诚实缺口）；动态候选 close 历史自入选次日起累积；涨停池分子（东财）与 universe 分母（THS 家数）命名体系混合，未对齐时情绪维 fail-closed | 首日 UNAVAILABLE→逐步 PARTIAL |
| 07-20~07-24 | 涨停池保留窗口外不可恢复 | UNRECOVERABLE |

R12 后待观察（均有 fail-closed 兜底）：archive-raw 阶段 5 `ALREADY_ARCHIVED` 命中与 md5 自检首轮通过情况；动态候选回补后 tracks coverage 能否 ≥80 转 PARTIAL；coverage 常态 82.4% 对阈值 80 余量仅 2.4 个百分点（fail-fast 设计）。

## 深入文档

| 文档 | 说明 |
|------|------|
| `docs/SMI-V1-Design-V1.1.md` | 完整设计文档（架构、数据源、验收标准） |
| `docs/acceptance/template-standard.md` | 验收标准（人类可读版） |
| `docs/acceptance/template-standard.json` | 验收标准（机器可读，单一真源） |
| `docs/acceptance/historical-profile.md` | 历史覆盖合同（产品裁决 v1） |
| `docs/acceptance/historical-profile.json` | 历史覆盖合同（机器可读） |
| `work/SMI_HANDOVER.md` | 任务交接手册（含完整命令速查） |
| `work/SMI_R12_Implementation_Report.md` | R12 实施报告（部署链路修复+主赛道动态化，f56e28d） |
| `work/acceptance/*.json` | 验收报告存档 |
