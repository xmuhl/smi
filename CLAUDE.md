# SMI — Stock Market Intelligence

## 项目概述

A股收盘全景 Web 看板。Python 采集 + Vue3 前端 + Cloudflare Pages 托管。
每日自动采集 9 大模块收盘数据，生成 JSON 快照，构建部署到 Pages。
主赛道自 R22-R28（2026-08-23）按**监测口径前 5 逐日直选**（范本第 8 表
严格口径；configVersion 3.5），经 ChatGPT 七轮评审迭代收敛（0 NOT_CLOSED）。

## 环境铁律（踩坑必读）

- **采集前必须清代理**：`$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'`（否则 v2rayN 代理导致挂起）
- **THS/mini_racer 接口禁重试并发**：akshare 内部 py_mini_racer.dll 并发会进程级崩溃；所有 THS 路径的 netguard 必须 `retries=0`（历史拉取串行，`_THS_HIST_CONCURRENCY=1`）
- **联网采集一律走 net_guard**：`from collector.netguard import net_guard` 装饰（单线程 + future 超时 + 孤儿线程 daemon 化）；无护栏的 akshare 直调可能 60 分钟静默挂起（2026-08-18 事故根因）
- **部署环境 Node 必须 ≥22**：wrangler 4.122.0 的 engines 硬要求；Node 20 下 `npm ci` 仅 EBADENGINE 警告但运行时退出（2026-08-17~20 部署全失败的根因）
- **git 两提交法**：先提交代码/数据（输入树），再单独提交验收报告（report-only commit）
- 全量 pytest 现可安全直跑（~6s）：`python -m pytest collector/tests/ -q`（R12 修复了 test_core 的 sys.modules["akshare"] 泄漏——此前该泄漏使后续测试真实联网 16 分钟/个）
- **本机 v2rayN 路由已定制**（2026-08-22）：`gorestart.cn→proxy`、`pages.dev→direct`（代理出口掐断浏览器到 pages.dev 的 TLS，直连通畅）；勿回改
- **网络源可用性**（2026-08-23 实测）：东财 push2/push2his 经代理与直连均封（fundFlow 概念资金流不可得的根因）；THS 概念指数 `stock_board_concept_index_ths` 经代理可用（含成交额历史）；GitHub API 走 `curl --proxy http://127.0.0.1:10808` + token（`git credential fill`）
- **ChatGPT 送审**：常驻 CDP relay（`tmp/cwa/cdp_relay.py`，心跳 tmp/cwa/relay_alive.json <15s 即活）持有单条 Chrome 调试连接，轮次脚本（tmp/cwa/cwa_rNN.py）经文件队列复用——不弹调试确认框；relay 死亡时轮次脚本自动回退直连（会弹一次框）。本机手跑 net_guard 采集脚本必须写成 .py 文件执行（spawn 模式不支持 stdin 脚本）
- **语义修订重生成数据**：manual-backfill 加 `--replace-modules tracks`（workflow 输入同名）可豁免 R8-P1-01 PARTIAL 历史保护整体替换；默认保护不变

## 架构

```
Python(AKShare) 采集 → web/public/data/daily/YYYY/YYYY-MM-DD.json (9 大模块)
→ Vue3 前端 → Cloudflare Pages (smi-6s2.pages.dev / smi.gorestart.cn 双域)
```

9 大模块：marketIndex / turnover / sentiment / sectorPerformance / fundFlow / northbound / margin / tracks / summary

### 主赛道（tracks，3.5 · R22-R28 收敛语义）

- **数据底座**：`industry-universe-snapshot` 归档（每日 THS 行业汇总 ~90 板块成交额/净流入/涨跌家数 + 东财 BK 代码映射）；**概念资格腿注入**（R23-P2-03）：board_type=concept 赛道以 THS 概念指数逐日成交额（元/1e8→亿，仅行业证据日）插入行业 universe **联合排名**——同源同单位可比（如高股息中特估→同花顺中特估100，boardCode 309062，归档 154 日）
- **选池**（`config/tracks.yaml` v3.5 selection）：
  - 准入=**当日前 5 直接入池**（entryRankMax=5，每日范本真理源，无确认门槛；原 2/3 入池确认与净流入>0 硬门均已退役——"排名决定监测资格，资金流决定评分/评级"）
  - 出池=连续 exitConfirmDays(2) 日排名>exitRankMax(12)；防抖完全由出池确认承担
  - 两层资格：`poolQualification` = QUALIFIED_TODAY（rank≤5）/ RETAINED_OBSERVATION（rank>5 未满出池确认，含观察区与出池宽限）
  - `rankScope` 口径元数据三分：INDUSTRY_UNIVERSE / CONCEPT_INJECTED / INDUSTRY_LEG（复合赛道资格按显式 qualification 主腿，评分按复合结构；主腿排名不得误称复合排名）
  - 种子=状态机初始在池成员（grandfather 承继资格），与动态成员同规则出池；无 universe 数据日/当日快照不过完整性门禁（≥max(45, 峰值×0.5)）→ 空池 fail-closed；未映射种子以 module errors 披露不静默消失
- **指标口径**：资金类优先 universe（概念腿净流入/涨跌家数为诚实缺列，正式项 mainNetInflow 条件必填）；close 序列类用 track-board-close 归档
- **评分与判定**：`config/track-scoring.yaml` 四维度 25/35/25/15；四级判定 CORE_MAIN/SECONDARY_MAIN/SHORT_LINE/PULSE_AVOID；coverage 三态门禁（target 80 / floor 65）
- **验收防线**（R23-P3-01/R24-P3-01）：cfg≥3.4 正式项 poolQualification 必填枚举；cfg≥3.5 rankScope 必填 + 资格层与 turnoverRank 交叉校验（标签写反即 FAIL）
- **前端**：观察保留徽标（板块名列）；空表两分支文案（UNAVAILABLE=上游不可用 / 完整无合格=无符合条件主赛道）；预热徽标；监测表按当日 turnoverRank 升序统一排序（种子与动态候选混排，acceptance sortedBy 强制；Legacy 范本日 07-17 豁免——产品裁决 2026-08-23）

## 生产域

| 域名 | 用途 | 状态 |
|------|------|------|
| `smi-6s2.pages.dev` | Cloudflare Pages 默认域 | ✅ 生产 |
| `smi.gorestart.cn` | 自定义域名（阿里云 CNAME） | ✅ 生产 |

## 当前状态（2026-08-23 · 验收修复基线，人工验收通过）

- **评审收敛**：R22→R28 七轮迭代全部 CLOSED（R28：0 NOT_CLOSED）；起因为人工验收发现种子池无条件占位（R22-DEF-01）；R22 假设清单机制升级出 4 项规格问题并全部修复（3.3→3.4→3.5）
- **tracks 3.5 已上线**：08-21 监测表=当日前5（半导体①通信②元件③高股息中特估④[概念注入]化学制药⑤，turnoverRank 全局升序）；07-20~08-19 历史日诚实空池；acceptance PASS=3（07-17/08-20/08-21）；测试 313 绿
- **人工验收修复轮（08-23，验收通过）**：turnover 08-18 回补 ERROR→FINAL + 08-19 链条重算（1272e5f）；tracks 监测表 turnoverRank 全局升序统一排序 + sortedBy 强制/Legacy 豁免（b2be8ed）；margin 08-17 T+1 回补 FINAL + 08-18 balanceChange 联动（f371c26）；margin 两融成交额行 UNAVAILABLE 隐藏（0590126）；全量审计报告 work/DATA_AUDIT_20260823.md（dba0a91）。turnover/summary/margin 模块级 failDates 全部清零，残余仅 sentiment 22 日 + fundFlow 21 日结构性缺口
- **提交链**：e0c0db6(3.3)→6171484(--replace-modules)→d77cdd7(3.4)→58e89c1(3.5)→8bf7d03/95a9ed6/ce60d38/e90f940(R28 收口)→094bf3b(上下文)→1272e5f/b2be8ed/f371c26/dba0a91/0590126(验收修复轮)→1444621(付费源裁决)
- **待观察**：① 周一 2026-08-24 首个 3.5 自动滚动日（close-snapshot 应自动产出当日前5，无确认延迟）② 方案 A（完整概念 universe=375 概念逐日采集+taxonomy 去重）为留档产品增强，当前方案 B（监测口径命名）已收敛 ③ fundFlow push2his 替代源长期跟踪（免费源实测确认无替代——两个 _hist 接口底层同为 push2his；付费源暂不考虑——产品裁决 2026-08-23）
- **送审材料**：work/SMI_R2[2-8]_Fix_Notes.md + zip；评审报告在 ~/Downloads；对话页固定 g-p-69b6697161988191bd88eeeadca58000

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
- 最新 clean 报告：`work/acceptance/baseline-report.json`（验收修复轮后，08-23）；常态 PASS=3（07-17/08-20/08-21），模块级残余仅 sentiment 22 日 + fundFlow 21 日（结构性无历史源）——turnover/summary/margin failDates 已于 08-23 清零
- 页面探针：`tools/acceptance/page_check.js`（`window.__smiPageCheck()`）

## 已知边界（产品裁决 v1 + R12 运行时观察项）

| 模块 | 历史缺口 | 状态 |
|------|----------|------|
| sentiment | riseCount/fallCount/flatCount 等无免费历史源 | PARTIAL/UNAVAILABLE |
| fundFlow | stockInflowTop10/OutflowTop10 无历史源；push2his 封禁 | UNAVAILABLE/PARTIAL |
| tracks | 07-20~08-19 板块快照不可回溯（接入前）→诚实空池（3.3 起）；excessReturn20d 无 HS300 归档源（诚实缺口）；概念腿净流入/涨跌家数无源（INSUFFICIENT 层诚实缺列）；涨停池分子（东财）与 universe 分母（THS 家数）命名体系混合，未对齐时情绪维 fail-closed | 空池日 UNAVAILABLE；数据日 PARTIAL |
| 07-20~07-24 | 涨停池保留窗口外不可恢复 | UNRECOVERABLE |

R28 后待观察：周一 08-24 首个 3.5 自动滚动；coverage 常态 76~82% 对阈值 80 余量薄（08-21 已落 DEGRADED 带——保留评分降置信，属设计内）；概念腿资金流缺口常态化后 minFormalItems=4 是否仍稳。

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
| `work/SMI_R2[2-8]_Fix_Notes.md` | R22-R28 评审迭代修复说明（种子池缺陷→3.5 收敛全程） |
| `work/acceptance/*.json` | 验收报告存档 |
| `work/DATA_AUDIT_20260823.md` | 线上数据全量审计报告（07-20~08-21 逐日矩阵+不可回补清单） |
