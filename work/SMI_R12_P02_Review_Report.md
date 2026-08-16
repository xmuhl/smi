# SMI R12 P0.2 只读复审报告

- 评审对象：SMI R12 P0.2（R12 P0.1 HOLD 的第二修订轮）
- 送审请求：`SMI_R12_P02_Review_Request.md`
- 被验收输入 commit：`594512ad018d2490495552f6ad5aa3245f72d960`
- 基线报告提交：`59cac97`（相对 594512a 仅修改 `work/acceptance/baseline-report.json`）
- 复核模式：**只读复核**；未修改送审仓库，未声称在调用方本地重新执行 pytest / collector 测试 / manifest 重算
- CWA_REQUEST_ID：`cwa-smi-r12-p02-20260816`

## 1. 总体结论

**结论：HOLD，尚不能声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

P0.2 相比 P0.1 已有实质性收敛：reference matcher 的 fail-on-missing、9 项指数范本数据、跨口径 `crossMethodReference`、07-17 summary 矛盾文案、9 个 invariant key、以及两提交 provenance 均真实落入代码/数据/报告。但独立复核仍能构造 5 个可证明的验收绕过路径，因此数据侧验收器还不能作为“任意历史日期达到 07-17 范本效果”的最终硬门禁。

### 本轮裁决汇总

- P0.1 的 9 个 NOT_CLOSED：**4 CLOSED / 5 NOT_CLOSED**
- 当前 NOT_CLOSED：**P1×2 / P2×3 / P3×0，共 5 项**
- 本轮未另立新编号；未闭环点仍属于既有问题根因的延伸，不重复拆号。
- `SMI-R12-P0-005` 上轮已 CLOSED，本轮不重复登记。

### 逐项状态

| 编号 | 严重度 | 裁决 | 核心结论 |
|---|---:|---|---|
| SMI-R12-P0-001 | P1 | **CLOSED** | reference fail-on-missing、9 指数补齐、northbound/margin/summary 全量消费与 declared/consumed 覆盖机制已形成闭环。 |
| SMI-R12-P0-002 | P1 | **NOT_CLOSED** | 真实 dispatch 只对复杂 handler 做版本绑定；generic 规则版本仍可任意漂移，且 `subFields/summaryFacts` 仍未由单一真源驱动。 |
| SMI-R12-P0-003 | P1 | **NOT_CLOSED** | PIT 必填已补，但“严格日期解析”和 quarterlyHolding item typed schema 仍可绕过。 |
| SMI-R12-P0-004 | P2 | **CLOSED** | MISMATCH 已强制结构化 crossMethodReference、nonComparable=true、成组数值与内部恒等。 |
| SMI-R12-P0-006 | P2 | **NOT_CLOSED** | tracks 生效区间非法日期可跳过；重算未验证结果全集，且 legacy 重算与标准说明仍不一致。 |
| SMI-R12-P0-007 | P2 | **NOT_CLOSED** | 07-17 stale 文案已修，但事实锚点仍主要是关键词门禁，不能阻止方向/数值与结构化事实相反。 |
| SMI-R12-P0-008 | P2 | **NOT_CLOSED** | 9 个 invariant key 已齐，但多条 invariant 的实际语义仍弱于标准 `enforce`，存在 true 假阳性。 |
| SMI-R12-P0-009 | P3 | **CLOSED** | 两提交 provenance 语义成立；报告绑定 evaluatedCommit=594512a 且报告提交仅改 baseline。 |
| SMI-R12-P01-010 | P3 | **CLOSED** | 20 tests=18 negative + 2 positive 的口径已统一，基线集合/计数与送审摘要一致。 |

---

## 2. 独立核验范围

本轮实际核对：

1. `ac1963c -> 594512a` 的真实 commit 差异：标准 JSON/MD、`accept.py`、07-17 快照和 P0.1 评审材料有增量修订；`test_accept.py` 本轮未修改。
2. `594512a` 下 `docs/acceptance/template-standard.json` 的 ruleVersion、nested subFields、tracks coversTradeDate、summaryFacts、crossModuleInvariants.enforce。
3. `594512a` 下 `tools/acceptance/accept.py` 的 `_validate_field_values`、`check_turnover`、`check_northbound`、`check_tracks/_recalc_tracks`、`check_summary`、reference assertion coverage、9 invariant、startup dispatch、report provenance。
4. `594512a` 的 07-17 快照：已补第 9 个“科创综合”，turnover/sentiment/summary 修订真实存在。
5. `59cac97` 的 baseline report：`evaluatedCommit=594512a`、`dirty=false`；07-17 记录 9/9 模块 PASS、9/9 invariant true；08-14 模块失败为 sentiment/northbound/tracks；模块失败计数与送审摘要一致。
6. `594512a -> 59cac97` 真实只变更 `work/acceptance/baseline-report.json`，符合两提交法结构。

> 测试声明说明：本轮是只读源码/产物复核。报告确认测试文件与送审口径的结构一致，但**不声称在调用方环境重新运行了 112 项测试**。

---

# 3. 逐项复核

## SMI-R12-P0-001 — referenceAssertions 全量消费

- **严重度**：P1
- **状态**：**CLOSED**
- **定位**：
  - `accept.py::_run_reference_assertions`
  - `_ref_match_items_by_name/_ref_match_lists/_ref_match_northbound/_ref_match_tracks/_ref_match_summary`
  - `_count_assertion_leaves`
  - `2026-07-17.json::modules.marketIndex`
- **独立证据**：
  1. `_ref_match_items_by_name` 对 expected name 缺失已改为 `_detail_gap`，不再 `continue` 静默放过。
  2. 07-17 快照已实际增加第 9 项“科创综合”(000680, 1938.77, -8.13%)，与标准 referenceAssertions 一致。
  3. northbound 已消费三项净流入 + netBuyTop10/netSellTop10；margin 不再只取四余额字段；summary 已有专门 matcher。
  4. `_run_reference_assertions` 计算 declared leaf 数与 consumed path 数，不等即 FAIL。
- **裁决**：上一轮“标准声明 ≠ 执行消费、缺期望项假阳性”的核心路径已消除。

---

## SMI-R12-P0-002 — 单一真源 / ruleId+ruleVersion 真实绑定仍不完整

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**：
  - `accept.py::_COMPLEX_HANDLERS`
  - `startup_self_check`
  - `_GENERIC_HANDLERS`
  - `_validate_field_values`
  - `template-standard.json::northbound.fields.quarterlyHolding.subFields`
  - `template-standard.json::summary.summaryFacts`

### 已确认整改

复杂 handler 已改成 `ruleId -> {supportedVersions, handler}`，`evaluate_modules` 也确实通过 `_build_checkers(standard)` 运行，不再使用固定旁路；这是实质改进。

### 仍未闭环 1：generic ruleVersion 没有版本绑定

`startup_self_check` 对 `_COMPLEX_HANDLERS` 会检查 `supportedVersions`，但进入 `_GENERIC_HANDLERS` 的 marketIndex / sectorPerformance / fundFlow **只检查 handler callable，不检查 ruleVersion**。

因此可构造：

- 把 `marketIndex.ruleVersion` 从 2 改为 999；
- `ruleId` 仍为 `marketIndex_V2`；
- startup self-check 仍会命中 `_GENERIC_HANDLERS` 并通过；
- 执行行为不变。

这直接违反本轮声明的“ruleId→{版本,handler}，版本不符即退出”。

### 仍未闭环 2：nested 标准没有被 generic engine 消费

标准已为 `quarterlyHolding` 声明 `subFields`（status/asOf/publishedAt/items.itemFields），但 `_validate_field_values(kind="object")` 只检查顶层值是 `dict/list`，**不会递归处理 `subFields`**；`dateString/array/boolean/const/requiredCondition` 也不是通用引擎可解释的完整 DSL。

当前只能靠 `check_northbound/check_turnover` 手工复制部分规则。因此修改标准 nested constraint，并不保证执行行为随之变化，仍不满足“单一真源驱动”的强语义。

同理，标准 `summaryFacts` 是结构化规则，但 `check_summary` 实际使用硬编码词表/逻辑，并未读取 `summaryFacts`。

### 影响

标准与执行器仍可漂移，尤其是未来调整 nested schema、allowedEnums、summaryFacts 时，会再次出现“标准看起来已收紧、执行门禁未同步”的同类问题。

### [FIX:SMI-R12-P0-002] 建议

1. generic handler 也改为 `ruleId -> {supportedVersions, handler}`，所有 9 模块统一版本绑定。
2. 要么让 generic DSL 真正递归消费 `object.subFields/array.itemFields/dateString/boolean/const/requiredCondition`；要么明确把这些规则从标准 generic DSL 移到具名 handler contract，避免“声明但未消费”。
3. `summaryFacts` 应由 checker 读取配置执行，或删除该结构化配置并明确其只是说明文档；不能同时称其为单一真源。
4. 增加 version mutation：generic 模块 ruleVersion 改为未支持值必须 startup exit 3。

---

## SMI-R12-P0-003 — 北向 PIT：必填已修，但严格解析/typed schema 仍可绕过

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**：
  - `accept.py::_parse_iso_date_strict`
  - `check_northbound`
  - `_validate_field_values`
  - `template-standard.json::northbound.fields.quarterlyHolding`

### 已确认整改

- OFFICIAL_REPLACEMENT 现在要求 `asOf/publishedAt` 存在；
- 缺任一会 FAIL；
- 晚于 tradeDate 会 FAIL；
- `INV-NORTHBOUND-PIT` 也补了相同必填检查。

上一轮“直接删除字段即可绕过”的路径已消除。

### 仍未闭环 1：所谓 strict ISO parser 实际只解析前 10 个字符

`_parse_iso_date_strict` 对长度 >10 的字符串直接执行 `date.fromisoformat(value[:10])`，不会验证后续内容是否为合法 ISO datetime。

因此类似：

`2026-08-14THIS_IS_NOT_ISO`

仍会被解析成 `2026-08-14`，从而通过“可解析”门禁。这与标准写的 `dateString` / “date/datetime 解析后比较”不等价。

### 仍未闭环 2：quarterlyHolding.items 只验“非空”，没有 typed schema

标准要求逐项：

- `shareholding`: finiteNonNegative
- `pctOfIssued`: nonNegativeInt（当前标准如此定义）
- `market`: enum[沪股通,深股通]
- code/hkexStockCode/name: string

但 `check_northbound` 只是：`if not it.get(fn): 缺字段`。因此 `shareholding="abc"`、`pctOfIssued="abc"`、`market="foo"` 都是 truthy，可通过该 handler；而 generic engine 又不递归 `subFields`。

### 影响

即使 PIT 日期不向未来，仍可把格式非法的发布时间或 typed schema 错误的持仓明细标为 FINAL，属于北向官方替代口径的核心真实性门禁缺口。

### [FIX:SMI-R12-P0-003] 建议

- 日期：完整解析 `YYYY-MM-DD` 或严格 ISO-8601 datetime，不允许“只取前 10 字符”。解析失败必须 FAIL。
- nested items：复用统一 recursive validator，或显式按 standard 的 itemFields 检查类型/范围/enum。
- 增加 mutation：非法 suffix datetime、shareholding 字符串、非法 market、pctOfIssued 非法类型。

---

## SMI-R12-P0-004 — turnover 跨口径契约

- **严重度**：P2
- **状态**：**CLOSED**
- **定位**：`check_turnover`、`template-standard.json::turnover.crossMethodReference`
- **证据**：
  - MISMATCH 必须存在 `crossMethodReference` dict；
  - previous/delta/changePct 三个有限数值成组；
  - `nonComparable is True`；
  - currentMethod/previousMethod 非空；
  - 校验 delta 与 today-prev、pct 与 delta/prev 的内部恒等；
  - 正常 turnoverPrevious/Delta/ChangePct 在 MISMATCH 必须为 null；旧标量 crossMethodReference 不能替代新对象。
- **裁决**：与上一轮 FIX 要求一致，核心绕过路径已关闭。

---

## SMI-R12-P0-006 — tracks 时序/区间/重算仍未机器闭环

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：
  - `check_tracks`
  - `_is_iso_date`
  - `_recalc_tracks`
  - `template-standard.json::tracks.fields/items/notes`

### 已确认整改

item.date==tradeDate、百分比 0~100、占位词、sourceSystem required、非 legacy FINAL 重算均真实进入代码。

### 仍未闭环 1：非法 effective 日期会跳过覆盖校验

标准字段仍是 `kind:string + coversTradeDate:true`。代码只在：

`_is_iso_date(effectiveFrom) and _is_iso_date(effectiveTo) and _is_iso_date(tradeDate)`

全部为 true 时才比较区间；若 `effectiveFrom="garbage"`、`effectiveTo="garbage"`：

- generic string 校验通过；
- 两字段非空；
- `_is_iso_date` 为 false；
- **代码没有追加 FAIL，只是跳过范围比较**。

所以“effectiveFrom<=tradeDate<=effectiveTo”仍不是 fail-closed 规则。

### 仍未闭环 2：重算没有验证 recomputed 集合完整性

`_recalc_tracks` 只遍历 `score_tracks()` 返回的 recomputed rows；没有要求：

- recomputed 长度 == snapshot items 长度；
- recomputed trackId 集合 == snapshot trackId 集合。

如果计算器因输入/配置异常只返回子集，未返回的快照赛道不会被重算比对；若返回空 list，当前函数也没有直接 FAIL。

### 仍未闭环 3：标准与实现对 legacy 重算仍自相矛盾

标准 notes 写明“**对 legacy 来源同样需用规则版本重算校验一致性**”，但 checker 明确只在 `(not is_legacy_snap) and status==FINAL` 调 `_recalc_tracks`；参考日 legacy 只走 reference assertions。

如果设计决定 legacy 只做 XLSX 金标断言，也可以接受，但必须把标准 notes 改成同一口径；当前属于标准/执行语义冲突。

### [FIX:SMI-R12-P0-006] 建议

- effectiveFrom/effectiveTo 用严格 dateString；任一不可解析立即 FAIL，再做区间覆盖。
- 重算后强制 `set(recomputed.trackId)==set(snapshot.trackId)` 且数量相等；缺项/多项均 FAIL。
- 明确 legacy 的最终设计：要么真的重算，要么标准删除“legacy 同样重算”，保留 referenceAssertions 作为唯一金标路径。
- 对上述三条增加 mutation/regression。

---

## SMI-R12-P0-007 — summary 事实锚点仍以关键词为主，不能保证事实方向一致

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：
  - `check_summary`
  - `template-standard.json::summary.summaryFacts`
  - 07-17 snapshot summary

### 已确认整改

07-17 的直接矛盾已真实修掉：marketEnvironment 现在写明 24035.65→26549.58、+2513.93、+10.46%、放量；northbound 也补了 -156.32/-68.54/-87.78 对应文案。

### 仍未闭环：通用 fact anchor 不足以防“说反了”

标准 summaryFacts 要求与结构化事实一致，但 checker 的实际门禁主要是关键词：

- margin FINAL：只要求文本含“融资”或“两融”，**不比较余额、变动方向**；实际 `marginBalanceChange<0` 时，文本写“本日两融余额大幅增加”仍可通过。
- northbound Legacy：只要求含“北向”及“净流入/净流出”任一词；实际 totalNetInflow<0 时写“北向资金净流入”仍可能通过。
- marketEnvironment：只拦不可比词 + 校验“放量/缩量/平量”词，**不锚 today/previous/delta/pct 数值**。
- `summaryFacts` 本身并未被 checker 读取，规则仍是代码硬编码。

因此本轮修掉了当前 07-17 的实例矛盾，但没有关闭同类未来回归。

### [FIX:SMI-R12-P0-007] 建议

至少把“方向事实”机器化：

- turnover：可比状态 + volumeState + delta 正负；如文本展示数字则核数值；
- margin：marginBalanceChange 正/负对应“增加/减少”，必要时锚总余额；
- northbound legacy：totalNetInflow 正/负对应净流入/净流出；official 分支锚 PIT/季度口径；
- tracks：除赛道名/decision 外，可核 score 或结构化摘要 facts。

最好由 `summaryFacts` 驱动而不是复制硬编码。

---

## SMI-R12-P0-008 — 9 个 invariant key 已齐，但 invariant 语义仍弱于标准 enforce

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：
  - `run_cross_module_invariants`
  - `template-standard.json::crossModuleInvariants`
  - `baseline-report.json::dates.*.invariants`

### 已确认整改

- `INV-ENUM-SOURCE-METHOD` 已真实进入 results；
- startup 会比较标准 id 集合与 `_INVARIANT_IDS`；
- 07-17 baseline 现在确实有 9 个 key 且全部 true。

“只有 8 个结果 key”的上一轮结构问题已修。

### 但仍有 4 个明确的语义假阳性

#### A. INV-UNIT-亿元

标准 enforce：`unit 缺失即 FAIL`。

代码：只有 `m.get("unit") is not None and unit != "亿元"` 才 false；**unit 缺失保持 true**。

#### B. INV-SENTIMENT-WIDTH

标准 enforce：三字段皆为 finite，任一缺失/非有限即 FAIL。

代码：只有“三字段全 finite”时才检查 sum<4000；如果某字段缺失，`all(...)` 为 false，但 `b` 不变，**invariant 仍 true**（即使模块 checker 会另行失败，也不等于该 invariant 按标准完成）。

#### C. INV-ENUM-SOURCE-METHOD

标准 `spec.allowedEnums` 明确给出：

- marketIndex.source
- turnover.method/comparisonStatus/volumeState
- sectorPerformance.method
- fundFlow.method
- northbound.mode
- tracks.sourceSystem + item 枚举

代码却没有读取 `crossModuleInvariants[*].spec.allowedEnums`；只扫描各模块**顶层 fields 中 kind=enum** 的字段。因此：

- marketIndex.source（kind=string）不受该 invariant 的 allowedEnums 控制；
- sector/fundFlow method 若为 string 也不受控；
- tracks items 的 maAlignment/excessReturn20d/decision 不在该 invariant 的顶层扫描里。

这与标准 `INV-ENUM-SOURCE-METHOD` 的明确 spec 不等价。

#### D. INV-MARGIN-IDENTITY

标准 enforce 明确要求总量恒等 + marginBalanceChange 与前一 FINAL 交易日差额恒等，且前一交易日缺失时不得 note 放行。

当前 invariant 自身只做 `balance == financing + securities`；环比仍依赖 `check_margin`，而该 checker 在找不到前一 FINAL margin 时仍追加 passed note，不判 fail。

### 影响

“07-17 9/9 invariant=true”目前只能证明**9 个键都产出了结果**，不能证明 9 条标准 invariant 的全部 enforce 语义都已实现。

### [FIX:SMI-R12-P0-008] 建议

- 每条 invariant 直接消费其标准 `spec/enforce` 所需字段；不要用“模块 checker 其它位置会拦”替代本 invariant 结果。
- unit 缺失 -> false；sentiment 任一非 finite -> false；margin 环比缺前序证据按标准 fail-closed；enum invariant 直接读取 allowedEnums 并递归 items。
- 为每一 invariant 至少一条“只让 invariant 失败”的 mutation，保证结果 key 的语义可独立验证。

---

## SMI-R12-P0-009 — provenance 两提交语义

- **严重度**：P3
- **状态**：**CLOSED**
- **证据**：
  1. `59cac97` baseline 内：`repoCommit=evaluatedCommit=594512a...`、`dirty=false`。
  2. `594512a -> 59cac97` 的 Git diff 只修改 `work/acceptance/baseline-report.json`，符合“输入树先提交，clean 上运行，报告后提交”的结构。
  3. standard/acceptor/manifest/per-date snapshot SHA256 均保留。
- **边界**：历史时点的 working tree clean 状态只能由生成器记录，无法在事后从 Git 单独证明；但本轮 provenance 设计与提交结构已经满足上一轮要求。

---

## SMI-R12-P01-010 — 测试/基线证据口径

- **严重度**：P3
- **状态**：**CLOSED**
- **证据**：
  - 送审明确写“20 tests = 18 negative mutation + 2 positive regression”，与既有 `test_accept.py` 结构一致；不再称“20 个负向”。
  - baseline 自动结果与送审摘要一致：marketIndex 0 / turnover 1 / sentiment 20 / sectorPerformance 19 / fundFlow 19 / northbound 20 / margin 0 / tracks 20 / summary 19。
  - 08-14 的模块失败集合独立核对为 sentiment / northbound / tracks；margin PENDING PASS，summary PASS。
- **说明**：112 项“全绿”是调用方本地执行声明，本轮未在 ChatGPT 环境重跑，因此不把“本端重新执行”作为 CLOSED 依据。

---

# 4. 当前基线复核

## 2026-07-17

- baseline：9/9 模块 PASS；9/9 invariant key 为 true。
- 07-17 snapshot：第 9 个“科创综合”已补；turnover / sentiment / summary 修订真实存在。
- 但由于 P0-002/P0-003/P0-006/P0-007/P0-008 仍有通用绕过路径，**07-17 PASS 不能等价推出验收器已最终收敛**。

## 2026-08-14

独立核对模块结果：

- PASS：marketIndex、turnover、sectorPerformance、fundFlow、margin(PENDING D0)、summary
- FAIL：sentiment、northbound、tracks

与送审摘要一致。

## 2026-07-20~08-13

baseline 模块失败计数与送审摘要一致：turnover 仅 07-20 多失败 1 日，其余历史缺口主要集中于 sentiment/sector/fundFlow/northbound/tracks/summary。

---

# 5. 收敛判断

本轮**不能**写“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

当前剩余 5 项均不是对已 CLOSED 问题的重复登记，而是 P0.1 原 NOT_CLOSED 根因仍有可执行绕过：

1. **P0-002 / P1**：single-source/version dispatch 仍不完整；
2. **P0-003 / P1**：北向 strict PIT/typed nested schema 仍可绕过；
3. **P0-006 / P2**：tracks 生效日期 fail-closed 与重算全集仍未闭环；
4. **P0-007 / P2**：summary 仍可把事实方向写反；
5. **P0-008 / P2**：9 invariant 的 key 完整，但 enforce 语义仍有多处假阳性。

建议下一轮只针对这 5 个点做最小增量修订，不必重开已 CLOSED 的 P0-001/P0-004/P0-005/P0-009/P01-010。
