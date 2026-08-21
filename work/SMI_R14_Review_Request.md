# SMI R14 送审请求（R13 修订包复核）

## 项目

SMI — A股收盘全景 Web 看板。Python(AKShare) 采集 → JSON 快照 → Vue3 前端 → Cloudflare Pages 双域托管
（smi-6s2.pages.dev / smi.gorestart.cn）。9 大模块：marketIndex / turnover / sentiment /
sectorPerformance / fundFlow / northbound / margin / tracks / summary。

## 本轮送审范围

- main HEAD = `ef95499`（R13 全部 7 项修复的应用包，16 文件 +2309/-230）
- 前置：`b610d75`（R13-P3-01 netguard 进程隔离 + Windows spawn 兜底）、
  `19107b9`（R13 送审文档归档）
- 本轮性质：**R13 HOLD 之后的修订验证轮**——请对照 Part1/Part2 的 7 项
  NOT_CLOSED 逐项裁定是否 CLOSED。

## R13 修复对照表

| 编号 | 严重度 | 修订摘要 | 定位 |
|---|---|---|---|
| R13-P3-01 | P1 | netguard 子进程隔离（fork/spawn），terminate→kill 确定性终止；pickle 原子回传；conftest 仅测试会话 inline | collector/netguard.py（b610d75） |
| R13-P2-01 | P2 | 迟滞选池：入池 2/3 日确认、出池连续 2 日确认、入 8/出 12 双阈值、冷启动收敛、全历史逐日递推；预热池 prewarmRankMax=16 接入 archive_raw 回补；minHistoryDays=20 → dataReadiness=WARMING_UP（与 FETCH_FAILED 分离） | collector/modules/tracks.py、collector/jobs/archive_raw.py、config/tracks.yaml v3.1 |
| R13-P2-02 | P2 | coverage 三态：target=80（READY/SUFFICIENT，点亮 D0）/ hard floor=65（INSUFFICIENT）/ [65,80) → TRACKS_DEGRADED（PARTIAL 保留评分降置信，不点亮 D0）；阈值以 track-scoring.yaml 单一真源；validator 双 decision 深度校验 | collector/calculators/tracks.py、collector/completeness.py、collector/validators/schema.py、config/track-scoring.yaml |
| R13-P3-02 | P2 | acceptance 身份闭合预检（退出码 4）：availableDates 严格性/去重/升序、latestCaptured==max、latestDate 别名一致、三指针 ∈ availableDates 且有序、latest.json↔manifest、daily↔文件名；build_entry 加 SNAPSHOT_IDENTITY_MISMATCH；9 项负向测试 | tools/acceptance/accept.py、collector/tests/test_acceptance_identity.py |
| R13-P3-03 | P2 | close-snapshot 部署自检：dist↔线上 latest.json 的 sha256+tradeDate 双全等（6×30s 重试），替代 updatedAt 时间新鲜度 | .github/workflows/close-snapshot.yml |
| R13-P3-04 | P2 | archive-raw 部署自检：REQUIRED_FILES 全集逐一 sha256 全等 + checked==required 集合完整性；任一缺失即红 | .github/workflows/archive-raw.yml |
| R13-P3-05 | P3 | useDailySnapshot 请求序列令牌，仅最后一次请求可提交状态 | web/src/composables/useSnapshots.ts |

### 与报告 [FIX] 块的有意差异（2 处，均已注释说明）

1. **archive REQUIRED_FILES=4 而非 5**：track-membership-snapshot 归档集当前尚无
   数据文件（模块未产出），纳入 REQUIRED 会使 workflow 永红。按"预期发布集合=
   实际存在的 4 类"处理；membership 启用时需同步加入（workflow 注释已注明）。
2. **netguard Windows spawn 兜底**：报告版仅 POSIX fork（不支持即 GuardedCallError）；
   实现版 Windows 用 spawn（被装饰函数须模块级可 pickle，本项目全部满足；不可
   pickle 时 fail-closed），经用户确认，因本地开发/测试环境为 Windows。

## 附带修复（非 R13 问题清单项，如实披露）

1. **test_p1_3 时间炸弹**：测试定义 `_FakeDT` 未 patch + 函数局部导入真实
   datetime，写测试当天通过、跨日必红。函数改用模块级 datetime，测试显式 patch。
2. **test_r13_p2_01_dual_rank_threshold 数据重造**：原数据按单日成交额推算排名，
   与实现的窗口累计成交额排名口径不符（从未触发期望行为）。按窗口口径重造
   3 日数据，覆盖：9~12 保留区留池 / 连续 2 日>12 出池 / 单日命中不足入池 /
   两日命中入池（正向对照）。

## 验证证据（2026-08-21）

- pytest 全量 **227 passed + 1 skipped**（新增 identity 9 项、tracks 动态 36 项）；
- compileall / vue-tsc / vite build 通过；
- acceptance `--all`：全 25 日期身份预检无 gap；
- CI（ef95499）：web=success，python=见提交页。

## 已知边界（请裁定是否需要新编号登记）

1. **tracks_V2 验收标准滞后**（R12 四级判定引入时未同步）：template-standard.json
   decision 枚举仍为旧值、requiredStatus=FINAL 为目标模型（历史上仅 07-17 Legacy
   达到）。新数据（四级判定 + TRACKS_DEGRADED）与标准枚举不匹配 → acceptance 对
   tracks 报 FAIL 属预期。标准更新需产品裁决，本轮未动。
2. margin 08-17/18/19、summary 08-19 的 acceptance FAIL 为线上存量数据状态
   （T+1 时序 + 当日真实 errors），本次 diff 不涉及。
3. coverage_hard_floor_pct=65 为临时标定值（20~30 真实交易日回放后重标）。
4. tracks WARMING_UP/PARTIAL 数据形态变化后，前端卡片层（本次未改）对新
   dataReadiness 的展示映射是否需要跟进——Part2 曾标 UNKNOWN，本轮仍未展开。

## 请复核要点

1. 对照 R13 Part1/Part2 的 7 项 NOT_CLOSED 逐项裁定 CLOSED 与否；
2. 两处与 [FIX] 块的有意差异是否可接受；
3. 迟滞选池的递推语义（全历史逐日递推 + 当日缺行计入出池条件）有无边界漏洞；
4. coverage 三态与 D0 完整性模型（DEGRADED 不点亮 D0）的一致性；
5. 已知边界 4 项是否需要登记新编号。

## 附件

- SMI_R14_source_20260821.zip：ef95499 完整源码树（排除 .git/.venv/node_modules/tmp/dist）
  + 关键 diff（19107b9..ef95499）+ 修复对照表。
