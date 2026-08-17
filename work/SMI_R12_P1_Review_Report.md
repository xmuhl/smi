# SMI R12 P1 只读复核报告

- 轮次：R12 P1
- Review 深度：只读复核
- 送审代码 commit：`a8b3a319200d196b652cde194447c4b215b98128`
- 送审数据/报告 commit：`01224c9`
- 前置状态：R12 P0.5 已收敛；本轮为新的 P1 历史回补范围
- 本轮结论：**HOLD**
- 当前 NOT_CLOSED：**P1 = 4 / P2 = 4 / P3 = 0**
- `SMI-R12-P1-001`：CLOSED
- `SMI-R12-P1-002`：NOT_CLOSED
- 新登记：`SMI-R12-P1-003` ～ `SMI-R12-P1-009`

> 本轮为只读复核。未修改调用方仓库，未在调用方环境重新执行 backfill、pytest、验收器或网络探测。  
> “无免费源”“主机封禁持续时间”“接口保留窗口”等外部事实，本轮只把仓库中已有声明视为送审方陈述；除仓库内可复验事实外，不自行扩大为已独立证明的事实。

---

## 1. 总体裁决

本轮两个代码修订中：

1. `P1-001` 将 `EASTMONEY_PUSH2HIS_HISTORICAL` 加入 `fundFlow.method` 单一真源枚举，**可 CLOSED**；
2. `P1-002` 将 `INV-ENUM-SOURCE-METHOD` 对所有非 `FINAL` 模块直接跳过，虽消除了当前 21 日报告中的枚举假失败，但该状态豁免**未写入标准的 machine-readable contract，且执行器硬编码 `FINAL`**，所以仍是 **NOT_CLOSED**。

更重要的是，P1 的核心目标不是“把 9 条 invariant 变成 true”，而是历史数据回补达到既定验收标准。当前实际仍有：

- fundFlow 历史路径的结构性六榜单不完备；
- sectorPerformance 12 日已知数据质量失败；
- sentiment 历史宽度数据缺口；
- tracks 历史量化输入缺口；
- 07-20 turnover 可直接修复缺口；
- 07-20～07-24 共用涨停池历史覆盖缺口；
- 最终 21 日验收报告的 provenance 仍是 `dirty=true`，且 canonical `baseline-report.json` 被覆盖成单日脏报告。

因此本轮不能声明收敛。

---

# 2. 送审提交边界独立核对

## 2.1 `a8b3a31` 代码提交

实际 diff 与送审声明一致，仅三处：

- `collector/modules/sectors.py`
  - `_THS_HIST_CONCURRENCY = 10` → `6`
- `docs/acceptance/template-standard.json`
  - `INV-ENUM-SOURCE-METHOD.spec.allowedEnums.fundFlow.method`
  - 新增 `EASTMONEY_PUSH2HIS_HISTORICAL`
- `tools/acceptance/accept.py`
  - `INV-ENUM-SOURCE-METHOD` 在模块 `status != FINAL` 时 `continue`

未发现送审方对该提交改动清单的漏报。

## 2.2 `a8b3a31 → 01224c9`

GitHub compare 显示 `01224c9` 顺序领先 `a8b3a31` 1 个提交，主要包含：

- 07-20～08-13 历史 daily snapshots；
- archive seed；
- manifest/相关数据；
- P0/P1 review 与 acceptance 报告归档；
- `work/acceptance/baseline-report.json` 的重写。

因此两提交顺序关系成立。但第二提交中的验收报告 provenance 不满足“干净输入树绑定”，详见 `P1-009`。

---

# 3. 逐项裁决

## SMI-R12-P1-001 — fundFlow 历史 method 枚举

- **严重度**：P2
- **状态**：**CLOSED**
- **定位**
  - `docs/acceptance/template-standard.json`
  - `collector/modules/fund_flow.py`
- **证据**
  - 标准允许值新增 `EASTMONEY_PUSH2HIS_HISTORICAL`；
  - collector 历史路径实际使用的常量也是同一 token。
- **根因**
  - 前一版单一真源枚举没有覆盖新增历史采集 method。
- **裁决**
  - 当前标准与生产者 token 已对齐，不再形成“实现合法、验收枚举拒绝”的假失败。
- **结论**
  - **CLOSED**。

> 注意：此项 CLOSED 只说明 method token 合法，不代表历史 fundFlow 已满足完整模块验收；后者见 `P1-003`。

---

## SMI-R12-P1-002 — INV-ENUM-SOURCE-METHOD 对非 FINAL 的状态豁免

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**
  - `tools/acceptance/accept.py::run_cross_module_invariants`
  - `docs/acceptance/template-standard.json::INV-ENUM-SOURCE-METHOD`
- **实际实现**
  - 执行器现在对任何不是 `FINAL` 的模块直接跳过整个 allowedEnums 检查。
- **标准现状**
  - invariant 的 `enforce` 仍声明：
    - 对 `spec.allowedEnums` 中声明的字段逐项检查；
    - required 字段缺失或值不在枚举均 FAIL；
    - 允许值只来自 spec。
  - 标准没有声明：
    - `applyWhenStatus = FINAL`；
    - 或 `skipStatuses = [PENDING, PARTIAL, UNAVAILABLE, ...]`；
    - 或其它 machine-readable 状态作用域。
- **根因**
  - 为消除非 FINAL 状态下的“枚举字段缺失”噪声，执行器直接硬编码了状态豁免，但没有先把语义写回单一真源标准。
- **影响**
  1. 标准与执行器语义漂移；
  2. 21/21 `INV-ENUM-SOURCE-METHOD=true` 的含义被弱化为“FINAL 模块枚举合法”，而不是标准文字当前描述的全量检查；
  3. 将来新增状态或改变状态机时，执行器仍会静默跳过；
  4. 当前提交没有新增针对该豁免的专项 regression/mutation，后续重构容易回归。
- **[FIX:SMI-R12-P1-002]**
  - 在 invariant spec 中显式加入状态作用域，例如 `applyWhenStatus` / `skipStatuses`；
  - 执行器只消费该标准配置，不自行硬编码 `status != FINAL`；
  - 同步 `desc/enforce`；
  - 增加至少三类测试：
    1. 非 FINAL + 枚举字段为空：按标准定义的结果；
    2. FINAL + required 缺失：false；
    3. FINAL + 非法枚举：false。
- **结论**
  - **NOT_CLOSED**。

---

## SMI-R12-P1-003 — 历史 fundFlow 六榜单契约无法由当前实现满足

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**
  - `collector/modules/fund_flow.py`
  - `docs/acceptance/template-standard.json::fundFlow`
- **证据**
  - 历史 collector 明确记录：
    - 行业/概念榜单来自 push2his；
    - “个股历史榜单”当前没有实现可用历史批量源；
    - `stockInflowTop10 = []`
    - `stockOutflowTop10 = []`
    - `errors += STOCK_HISTORICAL_UNAVAILABLE`
  - 但只要行业/概念历史拉取成功，collector 最终仍设置：
    - `status = FINAL`
  - 验收标准对：
    - `stockInflowTop10`
    - `stockOutflowTop10`
    均要求 `minItems = 10`。
- **根因**
  - 历史采集能力只覆盖四类板块榜单，而产品标准要求六类榜单；同时 collector 把“结构性缺两榜单”的半成品标成 FINAL。
- **影响**
  - **即使 push2his 主机解封，当前历史实现也仍不能让 fundFlow 通过完整标准。**
  - 因此“19 日 fundFlow 失败仅是临时封禁，解封后补齐”这一送审口径不充分。
- **[FIX:SMI-R12-P1-003]**
  - 优先方案：找到/构建历史个股资金流数据，使六类 TOP10 全部可生成，保持现有标准。
  - 如果产品明确决定历史模式只要求四类板块榜单：
    - 必须作为显式产品规格重设计；
    - 建立新的历史 profile/version；
    - 明确 UI/summary 的降级含义；
    - 不得把它描述成“与 07-17 完整基准等效”。
  - 在未解决前，历史结果缺两类 stock 榜单时不应标 `FINAL`；应使用与标准一致的 `PARTIAL/UNAVAILABLE` 语义。
- **结论**
  - **NOT_CLOSED**。

### 对 push2his 封禁的裁决

封禁本身可标为**临时运营缺口**，但 fundFlow 当前总体缺口是：

> **临时网络/主机可用性问题 + 结构性历史个股榜单能力缺口**

两者必须分开。

**不建议为了当前 1/21 PASS 去放宽现有验收标准。**  
那会掩盖结构性缺两榜单，而不是解决临时封禁。

---

## SMI-R12-P1-004 — sectorPerformance 12 日 FINAL 数据违反 Bottom5 符号契约

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**
  - 12 个历史日期的 `sectorPerformance`
  - `collector/modules/sectors.py` 历史路径
- **证据**
  - 最终 P1 验收报告中可见多日：
    - `status = FINAL`
    - 但 `industryBottom5[*].changePct` 出现正数，例如 0.55、0.33、0.54 等；
  - collector 普通排序逻辑本身是按 changePct 升序取 Bottom5，因此当前更像是历史序列/日期对齐/源数据质量问题，而非单纯 list sort 方向写反。
- **根因**
  - 历史 THS 序列进入 FINAL 前没有按验收标准做足够的数据质量门禁。
- **影响**
  - 12/21 日期 sectorPerformance 失败；
  - 更危险的是模块仍声称 FINAL，容易让下游误判“数据完整但验收器挑剔”，实际上是输入质量不满足契约。
- **[FIX:SMI-R12-P1-004]**
  1. 诊断历史 changePct 的日期对齐、基准日、序列切片与缓存键；
  2. 在 collector 输出 FINAL 前执行最小质量门：
     - Top/Bottom 数量；
     - unique；
     - 排序；
     - Top/Bottom 符号契约；
  3. 不满足则 fail-closed 为 PARTIAL/UNAVAILABLE，并记录可诊断 reason；
  4. 修复后重跑 12 日。
- **结论**
  - **NOT_CLOSED**。

---

## SMI-R12-P1-005 — 07-20～07-24 涨停池 archive 覆盖缺口（sentiment + tracks 共用根因）

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**
  - `web/public/data/archive/limit-up-pool.jsonl`
  - 受影响模块：sentiment、tracks
- **证据**
  - 当前 archive seed 可直接核到历史条目从 `2026-07-27` 起；
  - 07-20～07-24 未见对应 seed。
- **根因**
  - 这五日没有被当前 archive 底座覆盖。
- **边界说明**
  - 送审方声明“东财涨停池只保留近期窗口，因此早期五日不可回补”；
  - 本轮仓库证据只能证明**当前 archive 没有这五日**，不能仅凭代码独立证明外部服务永远无法再获得这些历史数据。
- **影响**
  - sentiment 和 tracks 的部分字段在这五日无法由当前 archive 重建。
- **[FIX:SMI-R12-P1-005]**
  - 若能从其它可信历史源补回，补 seed 并记录 provenance；
  - 若最终确认不可恢复，应在产品规格中把这五日标为明确、可机读的历史不可恢复区间，而非用普通 FAILED 与未来可修复日混在一起。
- **结论**
  - **NOT_CLOSED**。

---

## SMI-R12-P1-006 — sentiment 历史市场宽度不完整

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**
  - 07-20～08-14 sentiment 历史数据/验收结果
- **证据**
  - 送审最终统计：sentiment 仅 1/21 PASS、20 日 FAIL；
  - 主要缺失包括 `riseCount / fallCount / flatCount`，并有早期涨停池窗口问题及 08-14 的派生字段缺口。
- **根因**
  - 历史市场宽度数据源/归档链尚未建立到能满足现行标准的程度。
- **裁决边界**
  - “没有免费源”是送审方能力/来源判断，本轮没有外部检索去证明世界范围内不存在其它免费源；
  - 可确认的事实是：**当前仓库实现没有提供满足标准的历史数据。**
- **影响**
  - 与 P1“历史日达到 07-17 验收效果”的目标直接冲突。
- **[FIX:SMI-R12-P1-006]**
  - 优先补历史 source/archive/可重复推导链；
  - 若确认某字段在历史范围不可恢复，需由产品层显式裁决是否：
    1. 缩短承诺历史范围；
    2. 引入历史 profile；
    3. 保持 UNAVAILABLE/PARTIAL，明确不能声称全量等效。
- **结论**
  - **NOT_CLOSED**。

---

## SMI-R12-P1-007 — tracks 历史量化输入底座仍不完整

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**
  - tracks archive / calculator 输入
  - 07-20～08-14 tracks 验收
- **证据**
  - 送审最终统计：tracks 1/21 PASS、20 日 FAIL；
  - 当前缺口包括：
    - mainNetInflow
    - continuousInflowDays
    - excessReturn20d
    - redStockRatio
    - 以及早期五日涨停池覆盖。
- **根因**
  - P1 所需的历史 track 量化数据底座仍只覆盖部分指标。
- **影响**
  - tracks 不能达到 07-17 完整 benchmark；
  - 同时 tracks 是整体 CLOSE_COMPLETE/历史一致性的重要组成，不能仅靠“诚实 UNAVAILABLE”视为 P1 完成。
- **[FIX:SMI-R12-P1-007]**
  - 为每个缺失指标明确：
    - source/archive；
    - 最早可恢复日期；
    - point-in-time 约束；
    - 不可恢复时的状态和 UI 语义；
  - 在此基础上决定是补源、缩短历史承诺，还是建立显式 historical profile。
- **结论**
  - **NOT_CLOSED**。

> 早期五日 limit-up-pool 的共同根因只登记在 `P1-005`，这里不重复编号。

---

## SMI-R12-P1-008 — turnover 2026-07-20 缺 crossMethodReference

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**
  - `2026-07-20` turnover snapshot
- **证据**
  - 验收明确失败：
    - `PREVIOUS_METHOD_MISMATCH`
    - 需要 `crossMethodReference` 对象。
- **根因**
  - 这是口径切换边界的确定性数据补录/生成缺口，不是外部源不可用问题。
- **影响**
  - turnover 20/21，而不是 21/21。
- **[FIX:SMI-R12-P1-008]**
  - 按既定 schema 补齐跨口径 reference；
  - 重跑该日；
  - 增加边界日回归，防止以后 backfill 再遗漏。
- **结论**
  - **NOT_CLOSED**。

---

## SMI-R12-P1-009 — P1 最终验收报告 provenance 未绑定干净送审输入树

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**
  - `work/acceptance/p1_post_inv_fix.json`
  - `work/acceptance/baseline-report.json`
- **证据 A：p1_post_inv_fix**
  - 21 日最终报告内容确实显示修复后的 invariant 结果；
  - 但 provenance 记录：
    - `repoCommit = 60617f9...`
    - `evaluatedCommit = 60617f9...`
    - `dirty = true`
  - 这说明报告是在未提交改动存在时生成，不能唯一绑定到 `a8b3a31 + 01224c9` 的已提交输入树。
- **证据 B：baseline-report**
  - `01224c9` 中 canonical `work/acceptance/baseline-report.json` 被覆盖成：
    - 只含 `2026-07-20`
    - `repoCommit/evaluatedCommit = 60617f9...`
    - `dirty = true`
    - `INV-ENUM-SOURCE-METHOD = false`
  - 它不是本轮声明的 21 日最终验收证据，也不再是此前 P0 的干净 baseline。
- **根因**
  - 在 dirty workspace 中多次运行 acceptance，并把中间/单日报告写入 canonical 路径后统一提交。
- **影响**
  - 21/21 invariants 的“结果内容”可以作为调试证据，但无法满足此前已经建立的两提交 provenance 纪律；
  - 调用方无法仅凭 commit + hashes 精确重建本次最终验收输入。
- **[FIX:SMI-R12-P1-009]**
  1. 先把最终代码 + 数据输入全部提交成一个固定 input commit；
  2. 确认工作区 clean；
  3. 从该 commit 运行 21 日全量 acceptance；
  4. 报告必须：
     - `repoCommit == evaluatedCommit == 固定 input commit`
     - `dirty == false`
     - 含 21 日；
  5. 报告单独一个 report-only commit；
  6. 恢复或明确版本化 canonical `baseline-report.json`，不要让单日调查运行覆盖正式基线。
- **结论**
  - **NOT_CLOSED**。

---

# 4. 七大“诚实缺口”重新分类

| 原序号 | 送审缺口 | 本轮分类 | 是否可仅作为已知边界接受 |
|---|---|---|---|
| 1 | fundFlow push2his 封禁 | **混合：临时运营 + 结构性能力缺口** | **否**。解封只能恢复四类板块榜单；当前历史 stock 两榜单仍恒空 |
| 2 | sentiment rise/fall/flat 无历史免费源 | **结构性历史数据覆盖缺口** | **否，除非产品明确改历史承诺/标准** |
| 3 | sentiment 07-20～07-24 涨停池缺 | **历史 archive 覆盖缺口** | 可作为明确不可恢复窗口候选，但需来源证明/产品裁决 |
| 4 | tracks 主量化指标缺 | **结构性历史底座缺口** | **否，除非重设计 historical profile** |
| 5 | tracks 07-20～07-24 涨停池缺 | 与 #3 **同一根因** | 不另立根因，受影响模块扩展到 tracks |
| 6 | turnover 07-20 crossMethodReference 缺 | **确定性本地可修复缺口** | **否**，应直接补 |
| 7 | sectorPerformance 12 日 Bottom5 异常 | **数据质量/collector gate 缺陷** | **否**，应诊断修复并重跑 |

### 关键原则

“诚实地标 UNAVAILABLE/PARTIAL”是正确的数据治理行为，优于伪造数据；但：

> **诚实暴露缺口 ≠ P1 历史全量回补已经完成。**

如果本轮验收目标仍是“历史日达到 07-17 的完整效果”，这些缺口必须继续保持 NOT_CLOSED。  
若产品决定接受一个能力更弱的 historical profile，应以显式版本化标准重设计，而不是为了让当前报告变绿而放松既有标准。

---

# 5. 对 21/21 invariants 的解释

`p1_post_inv_fix.json` 的内容显示各日的 9 条 invariant 已被计算为 true，这与送审声明方向一致。

但需区分：

1. **invariant closure**
2. **module closure**
3. **provenance closure**

当前：

- invariant 内容：已明显改善；
- module：仍有大量 FAIL；
- provenance：仍是 dirty。

特别是 `INV-ENUM-SOURCE-METHOD` 新逻辑主动跳过非 FINAL 模块，所以“21/21 invariant=true”不能被解释成“21 日的 source/method/decision 字段全部完整且合法”。

---

# 6. 本轮问题总表

| ID | 严重度 | 状态 | 一句话 |
|---|---|---|---|
| SMI-R12-P1-001 | P2 | **CLOSED** | fundFlow 历史 method token 已与标准枚举对齐 |
| SMI-R12-P1-002 | P2 | **NOT_CLOSED** | 非 FINAL skip 仍是执行器硬编码，标准未声明状态作用域 |
| SMI-R12-P1-003 | P1 | **NOT_CLOSED** | fundFlow 历史路径恒缺 stock 两榜单，解封后仍不能满足六榜单标准 |
| SMI-R12-P1-004 | P1 | **NOT_CLOSED** | sectorPerformance 12 日 Bottom5 符号异常但仍标 FINAL |
| SMI-R12-P1-005 | P2 | **NOT_CLOSED** | 07-20～07-24 limit-up archive 缺口同时影响 sentiment/tracks |
| SMI-R12-P1-006 | P1 | **NOT_CLOSED** | sentiment 历史市场宽度仍不完整，20/21 FAIL |
| SMI-R12-P1-007 | P1 | **NOT_CLOSED** | tracks 历史量化输入底座不完整，20/21 FAIL |
| SMI-R12-P1-008 | P2 | **NOT_CLOSED** | turnover 07-20 缺 crossMethodReference，可直接修 |
| SMI-R12-P1-009 | P2 | **NOT_CLOSED** | 最终 21 日报告 dirty=true 且 canonical baseline 被单日报告覆盖 |

当前 NOT_CLOSED：

- **P1：4**
- **P2：4**
- **P3：0**
- **合计：8**

---

# 7. 下一轮最小收口顺序

建议按依赖优先级处理：

1. **先修 P1-009 provenance**
   - 固定 clean input commit；
   - 保证后续每轮结果可复验。
2. **修 P1-002 invariant 标准作用域**
   - 避免“为了变绿而硬编码 skip”成为长期语义债。
3. **修 P1-004 + P1-008 两个确定性本地问题**
   - sector 历史质量；
   - 07-20 turnover reference。
4. **对 P1-003 / 005 / 006 / 007 做产品级历史能力裁决**
   - 能补源则补；
   - 不能补则明确 historical profile / 最早支持日 / 不可恢复区间；
   - 不应直接降低现有 07-17 benchmark 标准。
5. 重新生成 `dirty=false` 的 21 日验收报告，再进入下一轮。

---

# 8. 最终裁决

本轮：

- `P1-001`：**CLOSED**
- `P1-002`：**NOT_CLOSED**
- 新增/确认 7 个独立待闭环根因；
- 当前 **8 NOT_CLOSED**。

因此本轮 **HOLD**，不能写：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”

本轮没有发现需要 `[REVERT:]` 或 `[DEGRADED:]` 的前轮共识冲突；P0.5 已闭环事项未被重新登记。
