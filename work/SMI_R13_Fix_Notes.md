# SMI R13 修订记录（2026-08-20 登记 · 2026-08-21 全部应用完成）

## 状态总览

R13 全部 7 项问题（P1×1 / P2×5 / P3×1）已全部应用修复并验证，
修订包提交 `ef95499`（16 文件 +2309/-230），待 R14 复审。

| 编号 | 严重度 | 摘要 | 状态 |
|---|---|---|---|
| R13-P3-01 | P1 | netguard 硬超时失效 | 已修（commit b610d75，进程隔离） |
| R13-P2-01 | P2 | tracks 动态选池缺预热/迟滞/就绪门禁 | 已修（ef95499） |
| R13-P2-02 | P2 | coverage=80 单硬门槛过激 | 已修（ef95499，三态） |
| R13-P3-02 | P2 | acceptance 缺顶层身份闭合 | 已修（ef95499） |
| R13-P3-03 | P2 | close-snapshot 自检只验 updatedAt | 已修（ef95499，sha256 全等） |
| R13-P3-04 | P2 | archive-raw 自检部分缺失仍 PASS | 已修（ef95499，全集校验） |
| R13-P3-05 | P3 | 前端日期切换 stale response 竞态 | 已修（ef95499） |

## 已应用明细

### R13-P3-01（P1）netguard 硬超时失效（b610d75）

- **问题**：R12 线程方案 `future.result(timeout)` 只停止等待、不终止底层调用；
  `_orphanify_executor()` 依赖的私有 API 按 CPython 语义不生效（运行中线程禁止改
  daemon；`_threads_queues` 的键是 worker Thread 而非 executor），08-18 式挂死风险仍在。
- **修订**（基于 ChatGPT [FIX:R13-P3-01]，加 Windows spawn 兜底，经用户确认）：
  - `collector/netguard.py` 整体重写：被装饰采集函数在独立子进程执行，超时
    `terminate()→kill()` 确定性终止；结果经 pickle 文件原子回传；异常优先原样
    传递，不可序列化时退化 `GuardedCallError`；
  - POSIX（GitHub ubuntu 生产）用 fork；Windows 用 spawn 子进程（被装饰函数须为
    模块级可 pickle 函数——本项目全部采集入口满足；不可 pickle 时 fail-closed，
    绝不退化为不可终止线程）；
  - `process.close()` 释放句柄（Windows 句柄不释放会让 pid 探测失真）。
- **测试**：worker 全部改模块级函数（spawn 可 pickle）；新增 worker 终止验证
  （pid 探测）、retries=0 不产生第二子进程、DataFrame 可序列化、不可 pickle
  异常 fail-closed。测试直通：`conftest.py` 设 `SMI_NETGUARD_MODE=inline`
  （仅测试会话；生产 workflow 严禁设置），netguard 专项走真实子进程。

### R13-P2-01（P2）迟滞选池 + 预热池 + 就绪门禁（ef95499）

- `select_scoring_pool`：入池确认（近 entryWindowDays=3 归档日 ≥ entryMinDays=2
  日满足"排名≤poolSize=8 且净流入>0"）；出池确认（连续 exitConfirmDays=2 日
  触及"排名>exitRankMax=12 或净流入非正或当日缺行"）；入 8/出 12 双阈值分离；
  池成员资格从 universe 归档全历史逐日递推（无额外状态文件）；归档历史不足时
  eff_min 按实际天数收敛（冷启动退化单日规则）。
- `select_discovery_pool` 预热池：成交额排名前 prewarmRankMax=16 的板块（不筛
  净流入），由 archive-raw 持续回补 close 历史；预热数据不直接参与评分。
- `minHistoryDays=20`：动态候选 close 历史不足 → `dataReadiness=WARMING_UP`
  （与 FETCH_FAILED 语义分离，前端不显示为"获取失败"）。
- config：tracks.yaml v3.0→v3.1（selection 新增 6 参数，含注释）。

### R13-P2-02（P2）coverage 三态分级（ef95499）

- `coverage_target_pct: 80`（≥ → READY/TRACKS_SUFFICIENT，点亮 D0）；
  `coverage_hard_floor_pct: 65`（< → INSUFFICIENT/TRACKS_INSUFFICIENT）；
  [floor, target) → `DEGRADED`（decision=TRACKS_DEGRADED，PARTIAL 保留可用
  评分、仅降置信；不点亮 D0 CLOSE_COMPLETE）。floor=65 为临时值，待 20~30 个
  真实交易日 coverage 分布回放后标定。
- `collector/calculators/tracks.py`：INSUFFICIENT 只由硬下限触发；输出
  `dataReadiness`（READY/DEGRADED/INSUFFICIENT，模块层可覆盖 WARMING_UP）。
- `collector/completeness.py` + `collector/validators/schema.py`：阈值以
  config/track-scoring.yaml 为单一真源；validator 允许
  TRACKS_SUFFICIENT/TRACKS_DEGRADED 两种 PARTIAL decision 并按阈值区间深度校验。

### R13-P3-02（P2）acceptance 顶层身份闭合（ef95499）

- `_validate_manifest_latest_identity` 启动预检（退出码 4）：
  availableDates 严格日期串/去重/升序；latestCapturedDate==max(availableDates)；
  latestDate（废弃别名）== latestCapturedDate；三指针 ∈ availableDates 且
  latestFinalDate ≤ latestCloseCompleteDate ≤ latestCapturedDate；
  latest.json.tradeDate == latestCapturedDate；latestCapturedDate 对应 daily
  文件存在且 tradeDate 一致。
- `build_entry`：daily 文件名 ↔ snapshot.tradeDate 身份不等 →
  SNAPSHOT_IDENTITY_MISMATCH（schemaValid=False，整体 FAIL）。
- 负向测试 9 项：`collector/tests/test_acceptance_identity.py`。

### R13-P3-03/04（P2）发布自检升级为内容身份全等（ef95499）

- close-snapshot：dist 与线上 `latest.json` 的 sha256 + tradeDate 双全等，
  6×30s 重试；替代原 updatedAt 时间新鲜度口径。
- archive-raw：REQUIRED_FILES 全集（track-board-close / track-board-flow /
  limit-up-pool / industry-universe-snapshot）逐一 sha256 全等 + 本地集合
  完整性（checked==required）；任一缺失/不一致即红。
  **与报告 [FIX] 的差异**：报告建议 5 文件含 track-membership-snapshot；该
  归档集当前尚无数据文件（模块未产出），纳入 REQUIRED 会让 workflow 永红。
  按"预期发布集合=实际存在的 4 类"处理；membership 归档启用时需同步加入。

### R13-P3-05（P3）前端请求序列保护（ef95499）

- `useDailySnapshot.load()`：requestSequence 递增令牌，只有最后一次请求可
  提交 snapshot/error/loading；快速切换日期时旧响应不再覆盖新数据。

## 附带修复（本会话 2026-08-21）

1. **test_p1_3_ensure_universe_archived 时间炸弹**：测试定义了 `_FakeDT` 但从未
   patch；`_ensure_universe_archived` 函数内局部 `from datetime import datetime`
   取真实时间，写测试当天（08-20）通过、跨日（08-21）必红。修订：函数改用模块级
   `datetime`/`TZ_SHANGHAI`（可 patch），测试显式 `monkeypatch.setattr(common,
   "datetime", _FakeDT)`。
2. **test_r13_p2_01_dual_rank_threshold 测试数据错误**：原数据按**单日成交额**
   推算排名（注释"证券X rank10/医药Y rank14"），但实现按范本口径用
   **amountWindowDays 窗口累计成交额**排名——窗口和完全改变排名分布，原数据从未
   触发期望行为（且"板块07 仅 1 次命中"断言与其自身数据矛盾）。按窗口排名语义
   重造 3 日数据（14 板块，已验算 D2/D1/T 累计和与排名序列），覆盖三个行为：
   9~12 保留区留池、连续 2 日>12 出池、单日命中不足入池（+ 两日命中入池正向对照）。

## 验证证据（2026-08-21，Windows 本地）

- pytest 全量：**227 passed + 1 skipped**（含新增 identity 9 项 + tracks 动态 36 项）；
- compileall 通过；vue-tsc + vite build 通过；
- acceptance：`--all` 全 25 日期跑通，身份预检无 gap（08-20 及此前 tracks
  FAIL 为存量状态，见下）；
- CI（ef95499）：web success；python 见 check-runs。

## 已知边界（R14 需披露，非本轮修复范围）

1. **tracks_V2 验收标准滞后**（R12 引入四级判定时未同步）：template-standard.json
   的 decision 枚举仍为旧值（核心防御主线/次主线/…），requiredStatus=FINAL 是
   验收目标模型（历史上仅 07-17 Legacy 达到）。线上新数据（四级判定 +
   TRACKS_DEGRADED）与标准枚举不匹配 → acceptance 对 tracks 报 FAIL 属预期。
   标准更新需产品裁决（新枚举/新就绪语义如何映射验收），建议 R14 单列讨论。
2. margin 08-17/18/19 FAIL、summary 08-19 FAIL 为线上存量数据状态（T+1 时序 +
   当日真实 errors），本次 diff 不涉及 margin/summary 采集逻辑。
3. coverage_hard_floor_pct=65 为临时标定值（设计注释已注明回放标定计划）。
4. archive REQUIRED_FILES=4（不含 track-membership-snapshot），见上文差异说明。

## 复核报告存档

- `work/SMI_R13_Review_Request.md`（送审说明）
- `work/SMI_R13_Review_Report_Part1.md`（方案层：含 Q1/Q2 完整答案与托管方案对比）
- `work/SMI_R13_Review_Report_Part2.md`（源码层：7 文件定点复核）
