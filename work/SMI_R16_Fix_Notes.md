# SMI R16 修复对照说明（Fix Notes）

- 基线：R15 送审 HEAD `ebac337`
- 本轮范围：R15 裁定的 4 项 NOT_CLOSED（R13-P2-01 / R14-P2-01 / R15-P2-01 / R15-P3-01；R15-N01 随 R15-P2-01 补件闭环）
- 日期：2026-08-22

---

## 一、逐项修复对照

### R13-P2-01 universe 完整性门禁两个阻断点 → 已修复

| 阻断点 | 修复 | 位置 |
|---|---|---|
| 1. 冷启动自校准盲区（首日 1 板块也成为证据日） | 绝对下限改为**有据非零值**：`minUniverseBoards: 45`——来源为已验证完整快照（2026-08-20 实测 THS universe **90 板块**，取其半），配置注释注明依据；归档初期 count<45 的日子一律不是证据日，直到出现可信完整日 | `config/tracks.yaml`、`tracks.py` |
| 2. 最终峰值回溯重分类（未来峰值改写历史证据资格） | 门禁**因果化**：证据日判定只依赖**严格早于当日**的前向峰值（`trusted_peak`）；且前向峰值只由**已通过门禁的完整日**抬高（可信基线，部分响应日不污染基线）。升序单遍历，严格因果状态机——同一历史日的证据资格不随未来观测变化 | `collector/modules/tracks.py:select_scoring_pool` |

**新增回归**（R15 §4 建议两条全落地）：
- `test_r15_universe_cold_start_tiny_not_evidence_day`：首日 2 板块（真实配置 45）→ `select_scoring_pool` 返回 `[]`；
- `test_r15_universe_gate_causal_no_retro_clear`：partial(2)→partial(2)→full(6)（min=2）→ D2/D1 建立的池籍在 T 日更高峰值出现后保留（旧全局峰值实现下池被无解释清空）。

**测试基建**：`_patch_archive` 增加 `min_universe_boards` 参数——生产阈值 45 面向真实 universe（90 板块），玩具宇宙（1~6 板）按玩具尺度显式覆写以聚焦迟滞/预热语义；门禁专项测试传 `None` 用真实配置。原 `test_r13_p2_01_incomplete_universe_day_not_exit_evidence` 改用 `min_universe_boards=2`（下限 1 无法验证门禁本身）。

### R14-P2-01 v4 矩阵六阻断点（A~F+G）→ 已修复

`tools/acceptance/accept.py` 矩阵重写为**穷举式状态机** + **显式版本分支**：

| 阻断点 | 修复 |
|---|---|
| A. PARTIAL+TRACKS_INSUFFICIENT 放行 | 穷举分支：PARTIAL 显式拒绝 TRACKS_INSUFFICIENT（"该 decision 仅属于 UNAVAILABLE"） |
| B. UNAVAILABLE 缺 decision / 旧值 "INSUFFICIENT" 放行 | decision 存在性检查从 (FINAL,PARTIAL) 扩到**所有状态**；UNAVAILABLE 必须精确等于 TRACKS_INSUFFICIENT；旧值 "INSUFFICIENT" 不在契约枚举被拒 |
| C. FINAL 不验 coverage | FINAL/TRACKS_SUFFICIENT 要求有限 coverage >= target（缺失与低于同拒） |
| D. dataReadiness/阈值字段可缺失 | `strict_v42`（configVersion>=3.2）：dataReadiness 必填且精确等于 readinessMap[decision]；coverageTargetPct/coverageHardFloorPct 必填且与 decisionContract 单一真源一致；warmingUpBoards 必填数组。非 strict（2.0/3.0/3.1 存量）保留软校验（存在则须一致） |
| E. INSUFFICIENT/FETCH_FAILED 项算 formal | strict 下 formal 仅计 `dataReadiness∈{READY,DEGRADED}`；数据缺口项（INSUFFICIENT/FETCH_FAILED）不得充数 minFormalItems。非 strict 沿用旧口径（旧数据无 readiness 字段） |
| F. WARMING_UP 只查 score/decision | 补 coveragePct、dimensionPass 必须 null（四字段全检） |
| G. 旧 3.0 数据靠 optionality 偶然放行 | **显式版本分支** `strict_v42`：数值版本解析（"3.2"→(3,2)>=（3,2)），2.0/3.0/3.1 只做状态⇄decision 配对（覆盖区间内），>=3.2 全字段契约；"legacy" 等非数值合法标记按非 strict |

**新增回归 11 条**（`tools/acceptance/test_accept.py`）：A/B×2/C×2/E/F×2/D×2 负向 + 3.0 存量形态正例（真实 08-20 快照形态：UNAVAILABLE/TRACKS_INSUFFICIENT/无 dataReadiness/无阈值字段 → 合法 PASS）。

**计数更正**：R15 送审正文"v4 13 条"系笔误（diff 实际 10 条，Fix Notes 亦为 10 条）；本轮后 v4 测试共 **21 条**（10+11）。

### R15-P2-01 送审包缺 N01 三个最终文件 → 已补

R16 包新增携带（最终归档字节，非 diff）：
- `collector/jobs/reconcile_turnover_chain.py`
- `collector/tests/test_core.py`
- `web/public/data/daily/2026/2026-07-17.json`（revision 8，LEGACY_REFERENCE_DAY_RESTORE）

随 R15-N01 一并请求裁定闭环。

### R15-P3-01 acceptance 测试未进 CI → 已修复

`.github/workflows/ci.yml` 新增独立 step：`pytest -q tools/acceptance/test_accept.py`（与既有 archive 自测 step 并列）。

---

## 二、验证证据（2026-08-22）

| 验证项 | 结果 |
|---|---|
| `pytest -q collector/tests tools/acceptance/test_accept.py` | **291 passed, 1 skipped**（R15 后 278 → 净增 13：门禁回归 2 + v4 负向 11） |
| `bash tools/deploy/test_verify_archive_sync.sh` | 4/4 PASS |
| `npm run typecheck`（vue-tsc） | 通过 |
| acceptance 07-17 / 08-20 | 9 模块全 PASS（08-20 以 3.0 版本分支合法通过；07-17 范本日不受影响） |

## 三、已知边界（不变）

沿用 R15 裁定：coverage floor=65 临时标定；sentiment/fundFlow 历史源缺口；margin/turnover/northbound/summary 存量上游失败；manifest 指针停在 07-17 与 D0 语义一致。
