# SMI R15 修复对照说明（Fix Notes）

- 基线：R14 送审 HEAD `0e2cfbf`
- 本轮范围：R14 裁定的 6 项 NOT_CLOSED（R13 遗留 2 + R14 新增 4）+ 本轮评审新增 3 项
- 日期：2026-08-22

---

## 一、R14 遗留问题修复对照

### R14-P1-01 Windows spawn 对真实 @net_guard 装饰函数不可用 → CLOSED

按 R14 §4 建议实现 module-level target registry：

| 修复点 | 位置 | 说明 |
|---|---|---|
| 装饰阶段登记 | `netguard.py:_spawn_target_key` | 按稳定 key `module:qualname` 把**原始未包装函数**登记进 `_SPAWN_REGISTRY`；非模块级函数（qualname 含 `<locals>`）装饰时即 fail-closed 抛 `GuardedCallError` |
| 子进程按 key 解析 | `netguard.py:_resolve_spawn_target` | 子进程只接收字符串 key，重 import 目标模块（import 重放装饰、重建注册表）后解析原始函数**直接调用**，不调用 wrapper（无递归 spawn）；属性链回退沿 `__wrapped__` 解包 |
| 严禁 pickle 函数对象 | `_run_once_hard_timeout` | spawn 路径 `args` 中 fn 位置传 None，只传 spawn_key |
| 全路径句柄释放 | `_run_once_hard_timeout` | success/error/timeout/unknown 全路径 `finally: process.close()`（R14 附带要求） |
| 强制 spawn 测试开关 | `_pick_context` | `SMI_NETGUARD_FORCE_SPAWN=1` 在 POSIX 上回归 Windows spawn 路径 |

**新增回归**：`collector/tests/test_netguard_spawn.py` 4 条——真实 `@net_guard` 装饰器语法（临时模块）+ 强制 spawn 下：成功返回 / 异常原类型传回 / 超时确定性终止 / 闭包装饰即 fail-closed。

**本机（win32）实测**：Windows 生产路径本身就是 spawn context，4 条测试在本机真实 spawn 下全部通过（不是模拟）。

### R13-P2-01 迟滞选池 / 预热 / WARMING_UP → CLOSED

R14 §5 列出的三个阻断点逐一收口：

| 阻断点 | 修复 | 回归测试 |
|---|---|---|
| A. "连续 2 日"退化为"累计 2 次" | `tracks.py:select_scoring_pool`：健康日 `streak=0`，仅 exit_hit 日累加 | `test_r13_p2_01_exit_streak_resets_on_healthy_day`（FAIL→PASS→FAIL 不出池） |
| B. minHistoryDays 只是标签 | `_make_track_item`：WARMING_UP 项 `score=null`、`coveragePct=null`、`decision=数据不足`、`dimensionPass=null`；`collect_tracks` 预热项不进 coverage 分母、不参与 any_score/critical 判定；全部候选预热 → `UNAVAILABLE/TRACKS_ALL_WARMING_UP` 诚实 fail-closed | `test_r13_p2_01_warming_up_not_formally_scored`、`test_r13_p2_01_all_warming_fails_closed` |
| C. 缺行=出池前提是 universe 完整 | `select_scoring_pool`：逐日板块行数 >= `max(minUniverseBoards, 峰值×minUniverseBoardRatio)` 才算完整证据日；不完整日不驱动出池 streak、不提供入池命中（config 3.2 新增 `minUniverseBoardRatio: 0.5`） | `test_r13_p2_01_incomplete_universe_day_not_exit_evidence` |

### R13-P3-04 optional membership 语义不一致 → CLOSED

| 修复点 | 说明 |
|---|---|
| 实现抽取 | workflow 内联脚本抽取为 `tools/deploy/verify_archive_sync.sh`（支持 `SMI_VERIFY_FAKE_REMOTE_DIR` 离线自测） |
| 语义严格化 | optional 本地缺失 → warning；optional 本地**存在**但线上不存在/unreachable/SHA 不一致 → `ok=0` FAIL（"存在则必须一致"落地） |
| 三态回归 | `tools/deploy/test_verify_archive_sync.sh`：absent→PASS / present+match→PASS / present+mismatch→FAIL / required mismatch→FAIL，已接入 CI（`ci.yml` 新增 step） |

### R14-P2-01 tracks_V2 验收标准与现行模型失配 → CLOSED（产品裁决落地）

v4 契约（`template-standard.json` ruleVersion 4）：

- `allowedStatuses: [FINAL, PARTIAL, UNAVAILABLE]` 取代 `requiredStatus: FINAL`（Legacy FINAL 仍合法）；
- `decisionContract` 状态-判定矩阵：
  - FINAL ⟺ TRACKS_SUFFICIENT（coverage>=target）
  - PARTIAL ⟺ TRACKS_SUFFICIENT（coverage>=target，诚实缺口）/ TRACKS_DEGRADED（floor<=coverage<target）
  - UNAVAILABLE ⟺ TRACKS_INSUFFICIENT（critical 或 coverage<floor）
  - `readinessMap`：decision 与 dataReadiness 一致性
- item decision 枚举换 R12 四级判定中文（核心主赛道/次主线·轮动主线/短线支线/一日游脉冲·回避/数据不足）；
- WARMING_UP 项不计 `minFormalItems`、不得输出成熟 score、decision 必须为「数据不足」；
- 非动态候选定性双列（coreCatalyst/earningsRealization）条件必填；动态候选（`dyn_` 前缀）允许 fail-closed 留白；
- `excessReturn20d` 登记 nullable 诚实缺口（无 HS300 归档源）；
- 配置生效区间外（<2026-08-20）的历史日豁免矩阵回溯判定（防止配置倒灌）。

**新增回归**：`tools/acceptance/test_accept.py` 10 条 v4 测试（正例 3：PARTIAL+SUFFICIENT、PARTIAL+DEGRADED、UNAVAILABLE+INSUFFICIENT；负例 7：SUFFICIENT 低 coverage、DEGRADED 高 coverage、UNAVAILABLE 非法 decision、readiness 失配、WARMING_UP 成熟 score、正式项不足、非动态项定性缺失）。

**真实数据验证**：2026-08-20 生产日 acceptance 9 模块全 PASS（`work/acceptance/r15_verify_d20.json`）。

### R14-P3-01 前端未消费新就绪态契约 → CLOSED

- `web/src/types/smi.ts`：`TrackItem` 补 `dataReadiness`（含 WARMING_UP）/`historyDays`；`TracksModule.decision` 补 `TRACKS_DEGRADED`/`TRACKS_INSUFFICIENT`；补 `dataReadiness`/`coverageTargetPct`/`coverageHardFloorPct`/`warmingUpBoards`；
- `TrackMonitorPanel.vue`：WARMING_UP 项 score 列加「预热」徽标（title 说明 close 历史天数与就绪线）、最终判定显示「预热中」（不当成熟结论解读）；模块级 TRACKS_DEGRADED 显示降级区间说明（coverage/floor/target）、warmingUpBoards 汇总提示；
- `npm run typecheck`（vue-tsc）通过。

### R14-P3-02 acceptance 允许非法 null 指针链 → CLOSED

- `_validate_manifest_latest_identity`：新增存在性单调检查——`latestFinalDate!=null ⇒ latestCloseCompleteDate!=null`、`latestCloseCompleteDate!=null ⇒ latestCapturedDate!=null`；
- 负向回归 2 条：`test_identity_final_without_close_complete_rejected`、`test_identity_close_complete_without_captured_rejected`。

---

## 二、本轮评审新增问题与修复（R15-N01~N03）

### R15-N01（P2）reconcile_turnover_chain 覆写 Legacy 范本日 → 已修复

**发现过程**：全量 pytest 发现 `test_positive_0717_all_pass`、`test_turnover_delta_wrong` 2 条失败；在 R14 基线 `0e2cfbf` 上同样失败（存量问题，非 R15 修复引入）。

**根因**：`610c854`（manual backfill，2026-08-20）执行 `TURNOVER_CHAIN_RECONCILE` 时，对归档链首日 2026-07-17（Legacy Excel 导入日）因链上无 07-16 文件，把 Excel 记录的跨日比较事实（turnoverPrevious=24035.65、EXPANSION 等）null 化为 PREVIOUS_UNAVAILABLE，并用模板文案覆写了 Excel 手写 summary 叙述——破坏"参考日以 referenceAssertions（Excel）为唯一金标"契约。docstring 声称"仅当前后 method 均可证明为 SH_SZ_A_NO_B_NO_BJ_V1 才重算"，但代码从未对**当日**为 LEGACY_UNKNOWN 的情况设门禁。

**修复**：
1. `reconcile_turnover_chain._reconcile_day`：`_infer_turnover_method(module) != TURNOVER_METHOD` 即跳过（Legacy 导入日的比较字段与 summary 是 Excel 事实，非链派生值）；
2. 数据恢复：`2026-07-17.json` revision 7→8（`LEGACY_REFERENCE_DAY_RESTORE`），仅恢复被覆写的 turnover 6 字段 + summary 4 段叙述（外科手术式，git diff 可核）；
3. 回归：`test_reconcile_legacy_day_exempt_from_overwrite`。

**验证**：07-17 acceptance 9 模块全 PASS（此前 FAIL）。

### R15-N02（P3）collect_tracks 死变量 → 已清理

`all_scores_present` 在 R15 重构后无任何消费点（基线上同样死代码），删除。

### R15-N03（P3）template-standard notes 滞后枚举文案 → 已更正

notes 中 "decision 非空枚举（核心防御主线/次主线/…）" 旧文案与 v4 enumValues 矛盾，更新为新四级枚举说明。

---

## 三、验证证据汇总

| 验证项 | 结果 |
|---|---|
| `pytest -q collector/tests tools/acceptance/test_accept.py` | **278 passed, 1 skipped**（含新增 netguard spawn 4 + tracks 回归 4 + identity 负向 2 + v4 acceptance 10 + reconcile 豁免 1） |
| `bash tools/deploy/test_verify_archive_sync.sh` | 4/4 PASS |
| `npm run typecheck`（vue-tsc） | 通过 |
| acceptance --all（25 个交易日） | PASS=2（07-17 范本日、08-20 当前生产日），其余 23 日失败全部落在 historical-profile 已披露边界（sentiment 22 日无免费历史源 / fundFlow 21 日主机封禁+无历史源 / margin 08-17~19 上游错误 / tracks 08-14/17/18 历史日 / turnover 08-18 采集 ERROR / northbound 08-17 / summary 08-19） |
| acceptance 07-17 / 08-20 单日 | 9 模块全 PASS |

**已知边界（非本轮缺陷，已在 profile/文档披露）**：
1. coverage_hard_floor_pct=65 临时标定，待 20~30 真实交易日回放重标（R14 边界 #3 延续）；
2. sentiment/fundFlow 历史源缺口（historical-profile.json 已披露，fundFlow 主机封禁解封可恢复）；
3. margin 08-17/18/19、turnover 08-18 等上游失败为存量数据状态（R14 边界 #2 延续）。
