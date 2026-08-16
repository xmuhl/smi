# SMI R12 P0 只读复核报告

- 评审对象：SMI R12 P0《范本验收标准与基线报告》
- 送审 commit：`3306ba7`（`feat/p0-acceptance-baseline`）
- 复核模式：**只读复核**，未修改仓库、未声称在调用方环境执行测试或重算 manifest
- 复核日期：2026-08-16
- CWA_REQUEST_ID：`cwa-smi-r12-p0-20260816`

## 1. 总体结论

**结论：不通过（HOLD，需修订 P0 验收口径后再进入硬门禁）。**

P0 的工程方向——机器可读标准、数据侧验收器、跨日期基线——是正确的；送审声明的 **21 日基线 1 PASS / 20 FAIL** 以及各模块失败日期计数，与 `work/acceptance/baseline-report.json` 在当前验收器规则下相符。但当前“PASS”尚不能等价于“达到 2026-07-17 XLSX 范本效果”，存在可证明的假阳性路径，尤其是：

1. **参考基线本身被降格为“适配现有快照”而非“还原 XLSX 范本”**：送审说明明确给出 07-17 XLSX 前一交易日成交额 `24035.65`，但 `template-standard` 与 `accept.py` 对 Legacy 日直接豁免 `turnoverPrevious/Delta/ChangePct`；实际 07-17 快照三项均为 `null`，仍被判 PASS。
2. **`template-standard.json` 不是执行器的真正单一真源**：`accept.py` 仅加载 JSON，但逐模块规则基本硬编码，多个 JSON/文档要求没有被实际执行，导致标准与验收器可漂移。
3. **北向拟定口径存在历史“看未来”风险**：不能把运行时“最近季度持仓（例如 2026-06-30）”统一倒灌给更早的历史选择日。应使用“截至所选日期当时已经公开的最近官方披露”。

因此，本轮可以认可“**基线报告准确反映了当前验收器**”，但不能认可“**当前验收器已经准确表达最终验收标准**”。

### 问题数量

- P1：3
- P2：5
- P3：1
- 合计：9

---

## 2. Q1–Q5 结论矩阵

| 问题 | 状态 | 结论 |
|---|---|---|
| Q1 北向官方日度停发后的统一口径 | **NOT_CLOSED** | 可采用“官方替代口径”，但必须按所选日期做 point-in-time（当时可见）披露；不得把未来季度持仓倒灌历史。官方日度仍有成交总额/笔数、ETF成交额、前十大活跃证券及成交总额，可与季度持仓共同构成替代面板，但无法官方重建范本式日度净流入。 |
| Q2 07-20 跨口径成交额 | **NOT_CLOSED** | 不建议硬编码 07-20 例外，也不应把 +1.84% 当作正常同口径环比。优先同口径回补 07-17；无法回补时保留 `PREVIOUS_METHOD_MISMATCH`，另设“跨口径参考变化”字段并显式标注。 |
| Q3 Legacy 情绪重复字段 | **NOT_CLOSED** | 不能只验有限性；07-17 页面/规范化数据应以 XLSX 权威值校正为 ST涨停10、ST跌停32，并保留原始 Legacy 值仅作溯源。当前验收器没有落实标准文档写明的校正规则。 |
| Q4 tracks 16 列免费路线 | **NOT_CLOSED** | 16 列作为最终范本目标合理，不应因历史数据困难而静默降门槛；但需逐指标定义来源、历史覆盖起点、窗口成熟条件、缺失原因与派生规则。当前“键存在”验收过松，且标准 displayRules 仍只要求页面显示 8 列，与最终 16 列目标不一致。 |
| Q5 验收器完备性 | **NOT_CLOSED** | 存在标准/代码漂移、summary 仅长度检查、northbound/margin/tracks 过松，以及排序、符号、单位、日期、方法一致性等语义约束缺失。fundFlow 六类 TOP10 与概念板块不属过严——它们既然是范本目标，就应保留。 |

---

## 3. 问题总表

| 编号 | 严重度 | 状态 | 一句话结论 |
|---|---:|---|---|
| SMI-R12-P0-001 | P1 | NOT_CLOSED | 范本优先级未锁定，07-17 可在缺失 XLSX 明确字段时仍 PASS，存在参考基线假阳性。 |
| SMI-R12-P0-002 | P1 | NOT_CLOSED | `template-standard.json` 被加载但并未驱动大部分规则，标准与验收器可无声漂移。 |
| SMI-R12-P0-003 | P1 | NOT_CLOSED | 北向“统一最近季度持仓”会造成历史看未来，且当前季度分支验收本身存在结构/状态/日期漏洞。 |
| SMI-R12-P0-004 | P2 | NOT_CLOSED | 07-20 应按“方法边界”通用处理，不应日期特判或把跨口径 +1.84% 伪装成正常环比。 |
| SMI-R12-P0-005 | P2 | NOT_CLOSED | 情绪 Legacy 校正与范本中的封板率/最高连板高度没有形成可执行验收。 |
| SMI-R12-P0-006 | P2 | NOT_CLOSED | tracks 只验字段存在远不足以证明 16 列有效，且历史覆盖/窗口成熟/定性配置缺少机器口径。 |
| SMI-R12-P0-007 | P2 | NOT_CLOSED | summary 只检查 8 个字符串长度，未检查中文、依赖完整性和与底层模块的事实一致性。 |
| SMI-R12-P0-008 | P2 | NOT_CLOSED | 排名、符号、单位、日期、来源、算术恒等式、唯一性等跨模块语义完整性规则缺失。 |
| SMI-R12-P0-009 | P3 | NOT_CLOSED | baseline 缺标准/验收器/输入快照的不可变哈希与 commit 指纹，复验可追溯性不足。 |

---

# 4. 详细问题

## SMI-R12-P0-001 — 参考基线假阳性：验收目标混淆“XLSX 范本”与“现有 Legacy 快照”

- **严重度**：P1
- **状态**：NOT_CLOSED
- **定位**：
  - `docs/acceptance/template-standard.json` / `template-standard.md`：turnover Legacy 例外
  - `tools/acceptance/accept.py::check_turnover`
  - `web/public/data/daily/2026/2026-07-17.json`
  - 送审说明 §七 07-17 范本要点
- **证据**：
  - 送审说明明确写出：07-17 成交额 `26549.58` 亿元，**前日 `24035.65`**。
  - 实际 07-17 快照：`turnoverPrevious=null`、`turnoverDelta=null`、`turnoverChangePct=null`、`volumeState=UNKNOWN`。
  - 标准文档却把这个“快照缺失”定义成 Legacy 允许例外；`accept.py` 对 `meta.legacy=true` 只要求 `turnoverToday` 有限，因此 07-17 被判 PASS。
- **根因**：参考标准不是从最终目标 XLSX 的可见数据逐项固化，而是反向迁就了当前快照数据模型。
- **影响**：最重要的金标日期都可以少字段仍 PASS，因此“其它日期 PASS = 达到范本效果”的逻辑基础不成立。
- **建议**：明确并机器固化优先级：**Reference XLSX（展示语义） > 经校正 canonical snapshot > raw legacy snapshot**。参考日期必须有一组精确 fixture/expected values，至少对范本关键字段做值级校验，而非仅结构/有限性校验。

**[FIX:SMI-R12-P0-001] 建议修订块（只读建议）**

- 为标准增加 `referenceAssertions`，对 07-17 明确写入范本真实展示值。
- `turnover` 至少记录/验证 `turnoverToday=26549.58`、`turnoverPrevious=24035.65`，并按范本公式固定增减/幅度/量能定性；若当前快照无法承载，应先补 canonical 字段，不应以 Legacy 豁免替代。
- 所有“仅因当前快照缺字段而产生”的 reference exception 必须逐项删除或改成 `rawLegacyException`，不得影响 canonical/reference PASS。

---

## SMI-R12-P0-002 — JSON 标准不是执行真源，标准/实现可漂移

- **严重度**：P1
- **状态**：NOT_CLOSED
- **定位**：`tools/acceptance/accept.py::main` 及各 `check_*`
- **证据**：`main` 会读取 `template-standard.json` 到 `standard`，但后续 `run_acceptance_date` 与各模块 checker 没有接收/消费该标准对象；核心规则（核心指数代码、最小长度、字段名、状态要求等）均硬编码在 Python 中。
- **已观察到的实际漂移**：
  - 标准说明 sentiment 应识别 07-17 Legacy 重复并“按 XLSX 校正”；代码没有读取 XLSX/canonical 映射，只检查有限性。
  - `stLimitDownCount` 在标准中是必检展示字段，但代码缺失时只记 note，不 fail。
  - tracks 标准有 16 个字段，代码虽然检查“键存在”，但只对 `mainNetInflow` 做有限数校验，`score/decision` 甚至只检查 `is not None`。
  - summary 送审口径称“≥10 字中文”，代码只检查 `str.strip()` 长度 >=10，并不验证中文。
- **根因**：规则定义存在两份：JSON/MD 是描述，Python 是真实执行逻辑。
- **影响**：后续修改标准文件可能不会改变验收行为；每日硬门禁有“文档看似收紧、代码仍放行”的风险。
- **建议**：至少做到“规则可执行 + 自检”：通用字段/minItems/requiredStatus 从 JSON 驱动；复杂规则保留 Python rule handler，但 JSON 明确 `ruleId/ruleVersion`，启动时校验每条规则版本和必需字段与 handler 一致；增加 mutation/negative fixtures，证明每个门禁真的能拒绝坏数据。

**[FIX:SMI-R12-P0-002] 建议修订块**

1. 标准增加 `schemaVersion`、每模块 `ruleId/ruleVersion`、类型/有限性/枚举/范围/空值策略。
2. checker 不再重复维护字段列表；从标准读取通用规则。
3. 对不能声明式表达的语义规则，标准只引用明确版本化 handler。
4. 新增“标准-执行器一致性测试”：故意把每个必检字段置空/错类型/错枚举，必须逐项 FAIL。

---

## SMI-R12-P0-003 — 北向统一季度持仓存在历史看未来 + 当前 checker 过松

- **严重度**：P1
- **状态**：NOT_CLOSED
- **定位**：Q1；`check_northbound`；`template-standard` northbound
- **外部官方事实复核**：
  - 上交所/深交所自 **2024-08-19** 调整沪深股通披露机制。
  - 北向每日收市后仍披露：成交总额、总笔数、ETF 成交总额、前十大成交活跃证券及其成交总额；**不提供足以还原范本式“日度净流入/净买入”的买卖拆分**。
  - 每季度第 5 个沪/深股通交易日披露上季度末单只证券的沪/深股通投资者合计持有数量。
- **对拟定方案的判断**：
  - “所有 POST_20240819 日期统一展示运行时最近季度持仓，例如 2026-06-30” **不可接受**，因为选择 2026-01、2026-03 等历史日期时会展示当时尚未公开的信息，构成 point-in-time 泄漏。
  - “季度持仓 + 日度已停发”作为**官方替代口径**可以 PASS，但只能称“信息密度/展示完整度等价”，不能称“与 Legacy 日度净流入语义等价”。
- **checker 具体漏洞**：
  - 季度分支没有强制模块自身 `status == FINAL`。
  - `quarterlyHolding` 若直接是任意非空 list，也可被当作真实季度数据。
  - 未验证 item schema、`asOf`、发布日期/可用日期、所选日期关系。
  - `mode` 仅要求字符串包含 `POST_20240819`，过于宽泛。
- **建议口径**：采用 **point-in-time official replacement**：对所选日期 D，只展示 `publishedAt <= D` 的最新官方季度持仓；同时可展示 D 当日官方沪/深股通成交总额/笔数、ETF 成交额、前十大活跃证券成交额。页面明确：“官方已停止日度净流入披露，以下为官方替代口径，不与 Legacy 净流入连续比较。”

**[FIX:SMI-R12-P0-003] 建议修订块**

- `mode` 改成严格枚举，例如 `POST_20240819_OFFICIAL_REPLACEMENT`。
- 季度持仓必须：模块 FINAL；holding FINAL；items 非空且逐项 schema 合法；`asOf <= selectedDate`；新增 `publishedAt` 并要求 `publishedAt <= selectedDate`。
- 日度替代信息可独立作为 `dailyOfficialActivity`：仅承载官方仍披露的成交活跃信息，不推导净流入。
- 非官方估算若未来采用，只能放在独立 `estimated` 分支，必须 `isOfficial=false`、标明模型/误差/来源，且**不应作为官方口径验收门禁的替代**。

---

## SMI-R12-P0-004 — 07-20 成交额应按“方法边界”处理，而不是日期例外或伪同口径环比

- **严重度**：P2
- **状态**：NOT_CLOSED
- **定位**：Q2；`check_turnover`
- **独立计算**：`27037.72 - 26549.58 = 488.14` 亿元；跨口径参考变化约 `+1.8386%`（显示可四舍五入 `+1.84%`）。
- **判断**：
  - 方案 a“仅 07-20 例外”不推荐：未来任何方法切换都会重复产生同类问题。
  - 方案 b“直接允许跨口径比较并写入正常 turnoverChangePct”也不推荐：会把不可比数字伪装成连续序列。
- **推荐顺序**：
  1. **优先**：如能用 `SH_SZ_A_NO_B_NO_BJ_V1` 规则同源重建 07-17，则重建后做正常同口径环比。
  2. 若无法同口径重建：保留 canonical `comparisonStatus=PREVIOUS_METHOD_MISMATCH`；正常 `turnoverDelta/ChangePct` 继续为 null；另提供 `crossMethodReferencePrevious/Delta/ChangePct`，页面显著标记“跨口径参考”。
  3. 验收器对任意 `PREVIOUS_METHOD_MISMATCH` 使用通用分支，不硬编码具体日期。
- **关于“范本效果”**：视觉上仍可填满“前日/增减/幅度”区域，但必须把跨口径值标为“参考”，不能与正常同口径变化共用字段/样式。

**[FIX:SMI-R12-P0-004] 建议修订块**

- 定义 `comparisonStatus` 状态机：`COMPARABLE / PREVIOUS_UNAVAILABLE / PREVIOUS_METHOD_MISMATCH`。
- `COMPARABLE`：强制算术恒等式和同 method/version。
- `MISMATCH`：要求前后 method/version 均明确；canonical change 保持空；若展示参考变化，则独立字段有限且带 `nonComparable=true`。
- 不增加 `2026-07-20` 特判。

---

## SMI-R12-P0-005 — 情绪 Legacy 仅验有限性不够，且范本两个指标被标准遗漏为不可执行

- **严重度**：P2
- **状态**：NOT_CLOSED
- **定位**：Q3；`check_sentiment`；`template-standard` sentiment
- **证据**：
  - 07-17 快照实际为：non-ST涨停25 / ST涨停25、non-ST跌停180 / ST跌停180。
  - 送审材料与标准文档均明确 XLSX 正确值为：**non-ST涨停25 / ST涨停10 / non-ST跌停180 / ST跌停32**。
  - `check_sentiment` 没有落实校正；`stLimitDownCount` 缺失甚至不算 fail。
  - XLSX 还有“涨停封板率 43.75%”“市场最高连板高度 2连板”，标准说明它们只在 XLSX、快照未展开，因此当前验收根本不能证明这两个范本字段达到效果。
- **判断**：页面应展示校正后的 canonical 值；错误的 raw Legacy 字段不能继续作为展示值。原始值可保留在 `rawLegacy`/provenance 中用于审计。
- **建议**：参考日做精确值 fixture；非参考日做类型、范围、市场宽度完整性、ST/non-ST 组成和来源口径验收。若最终网页要达到 XLSX 完整效果，则封板率和最高连板高度必须进入 canonical schema + checker。

**[FIX:SMI-R12-P0-005] 建议修订块**

- 增加 canonical `limitSealRatePct`、`maxLimitUpStreak`（命名可按现有 schema 风格确定）。
- 07-17 迁移/归一化时把 ST 值校正为 10/32，并记录 `correctionReason=LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX`。
- checker 强制 7 个涨跌停/市场宽度字段均有限（若业务允许 null，必须有明确 reason，而不是 silent note）。

---

## SMI-R12-P0-006 — tracks 16 列目标合理，但当前有效性、历史覆盖和展示规则都未闭环

- **严重度**：P2
- **状态**：NOT_CLOSED
- **定位**：Q4；`template-standard` tracks；`check_tracks`
- **结论**：如果最终目标明确是“网页达到 07-17 4赛道×16列效果”，**16 列不应因为免费历史源困难而降成软要求**。历史不可回补应继续 FAIL/NOT_CLOSED，直到找到合法来源或用户显式批准等价替代口径。
- **当前过松点**：
  - 代码只验证 16 个 key 是否存在。
  - 数值只严格校验 `mainNetInflow`；`score` 仅 `is not None`，空串/非数值理论上可通过；`decision` 仅非 None，空串也可通过。
  - turnoverRank、continuousInflowDays、rps60、limitUpCount 等可能为 null/占位仍未被拦截。
  - 定性字段 `coreCatalyst/earningsRealization` 只要 key 存在即可，没有配置版本、来源或“占位文案”判定。
  - `displayRules.tracks` 仍只要求网页显示 8 列（赛道/定位/主力净流入/连续流入/RPS60/涨停/综合分/判定），与最终 16 列网页目标不一致。
- **免费路线应按指标分类**：
  - **历史行情可派生**：近5日成交额排名、MA 5/10/20、RPS60、超额收益、红盘占比（前提是对应板块/成分历史完整且 point-in-time 成分定义明确）。
  - **资金流时间序列依赖**：今日主力净流入、连续净流入天数；后者不能只靠当天数据，必须有连续历史且口径相同。
  - **涨停池/成分依赖**：涨停家数、连板梯队；若现有免费历史窗口从 07-27 起，则 07-27 之前不能伪造或凭空回算，除非找到其它可核验历史源。
  - **配置定性列**：定位、核心催化、业绩兑现；可由 versioned config 提供，但必须明确 `configVersion/effectiveFrom/effectiveTo/source`，避免今天的判断倒灌旧日期。
  - **派生输出**：score/decision 必须对输入完整性、规则版本、范围/枚举做校验。

**[FIX:SMI-R12-P0-006] 建议修订块**

- 每个指标增加 `value + quality + source + asOf + methodVersion`（可按模块级元数据减少冗余）。
- 明确 `historyCoverageStart`、`windowRequiredDays`、`windowMatured`；未成熟时不得给“完整 PASS”。
- 数值字段做 finite/range；文本字段做非空+禁止占位词；枚举字段做严格枚举。
- score 约束范围与规则版本，decision 必须是明确枚举/映射，并验证可由 score/规则推导。
- P3 前端 16 列对齐前，P0 的 `displayRules` 先改成最终 16 列目标，避免验收标准先天低于目标。

---

## SMI-R12-P0-007 — summary 只验长度，无法证明“总结内容达到范本效果”

- **严重度**：P2
- **状态**：NOT_CLOSED
- **定位**：Q5；`check_summary`
- **证据**：代码仅要求 8 个字段都是去空白后长度 >=10 的字符串；并不验证“中文”，也不验证文本与底层模块数据一致。
- **实际风险**：
  - 任意 10+ 字符的模板话术、英文占位、过期数字都可能 PASS。
  - 07-20 等多个底层模块 UNAVAILABLE 时，summary 仍可独立 PASS；这说明当前 summary 门禁没有依赖完整性。
  - 07-17 的 `trackConclusion` 为“有效监测赛道中 0 条达标、0 条观察、0 条规避”，而同一快照存在 4 条 tracks 且均有 score/decision；至少表明 summary 与 tracks 之间没有被机器校验的一致性约束。
- **建议**：summary 应验“结构 + 事实锚点 + 依赖状态”。不要做 NLP 主观评分，优先用结构化 facts 生成文本，再反向校验 facts 与模块。

**[FIX:SMI-R12-P0-007] 建议修订块**

- summary 每段增加 `facts` 或由 rule-engine 输入结构化 facts；验收器验证 facts 与源模块相等。
- 当依赖模块非 FINAL/允许替代状态时，summary 必须显式包含“不可用/口径替代”说明，不得生成貌似完整的结论。
- 文本层只做最小约束：中文字符占比/禁止占位词/风险提示固定语义；关键正确性由结构化 facts 保证。

---

## SMI-R12-P0-008 — 多模块仅做“形状检查”，缺少语义完整性

- **严重度**：P2
- **状态**：NOT_CLOSED
- **定位**：Q5；`check_marketindex/check_turnover/_check_items_list/check_margin` 等
- **遗漏汇总**：
  - **marketIndex**：未检重复 code、dataDate 与 tradeDate 一致、close 合理范围/正值、source/method、8项扩展是否应在参考/最终目标必需。
  - **turnover**：未校验 `delta = today - previous`、`pct = delta/previous`、volumeState 与阈值一致、previous 对应真实前一交易日、方法版本一致。
  - **sectorPerformance**：只看数量/name/changePct；未检 TOP/BOTTOM 排序、重复名称、榜单交叉重复、日期/口径、百分比范围。
  - **fundFlow**：只看数量/name/netInflowYi；未检流入应为正/流出应为负、排序、重复、单位、数据日期、method/source。六类 TOP10 与概念榜本身**不是过严**，因为它们是范本的明确内容。
  - **northbound**：见 P1-003。
  - **margin**：FINAL 仅检查三项余额有限；D0 PENDING 分支只要求 `latestPublishedReference` 是 dict 且 `tradeDate==latestCapturedDate`，并未验证 reference 内的值、reference dataDate、发布日期或 T+1 关系。
  - **通用**：模块 `dataDate/asOf` 与所选日期关系、单位、source/method/version、缺失原因枚举、provenance 没有统一门禁。
- **建议**：引入跨模块通用 invariant 层，再叠加模块规则；尤其避免“长度够、数字有限就算对”的验收方式。

**[FIX:SMI-R12-P0-008] 建议修订块**

通用 invariant 至少包括：

1. `dataDate/asOf/publishedAt` 与 selected date 的时序关系；禁止 look-ahead。
2. `unit/source/method/methodVersion` 必须满足标准枚举。
3. list 类榜单：唯一性、排序方向、正负符号、最小/最大长度、日期一致。
4. 派生数值：算术恒等式与容差。
5. PENDING/替代口径必须携带结构化 reason/quality，不以普通 FINAL 数据伪装。

---

## SMI-R12-P0-009 — baseline 缺不可变输入指纹，复验可追溯性不足

- **严重度**：P3
- **状态**：NOT_CLOSED
- **定位**：`work/acceptance/baseline-report.json`；`accept.py` report 构造
- **证据**：当前 report 顶层记录 `generatedAt` 和标准**路径**，但代码生成结构未记录：标准文件 SHA-256、accept.py 版本/commit、manifest hash、各 daily snapshot hash、schema validator version/hash。
- **影响**：同一路径内容一旦变化，旧报告无法证明“当时究竟以哪一版标准/输入跑出来”，不利于后续回退重研与多轮评审的证据锁定。
- **建议**：在 report 增加不可变 provenance 元数据；这是验收平台的审计能力，不要求本轮生成额外 zip/manifest。

**[FIX:SMI-R12-P0-009] 建议修订块**

至少记录：`repoCommit`、`standardSha256`、`acceptorSha256`、`manifestSha256`、`schemaVersion`、每日期 `snapshotSha256`、运行 Python 版本、生成时间与时区。

---

# 5. 对 Q1–Q5 的直接裁决

## Q1 北向：最终建议

**采用“官方替代口径”，但必须 point-in-time，不接受“全历史统一当前最近季度”。**

推荐 POST-2024-08-19 面板组成：

1. 当日官方沪股通/深股通成交总额、总笔数、ETF 成交额；
2. 当日前十大成交活跃证券及成交总额；
3. 截至所选日期**当时已经公开**的最近季度持仓；
4. 明确固定提示：官方日度净流入已停止披露，以上信息不与 Legacy 净流入连续比较。

这能满足“页面有真实内容、无伪造、信息密度接近范本”的产品目标，但必须在标准中命名为 **equivalent official replacement**，不能写成与 07-17 日度净流入“同指标等价”。若用户坚持“同指标日度净流入必须存在”，则官方免费路线客观上无法满足，只能保持 UNAVAILABLE 或另加明确标注的非官方估算；不建议用估算通过官方门禁。

## Q2 成交额：最终建议

选择“**同口径优先；不可同口径时，跨口径仅作独立参考**”。

- 不采用日期硬例外。
- 不把 `+1.84%` 写入正常 `turnoverChangePct`。
- 可以显示 `+488.14 亿 / +1.84%`，但字段和 UI 必须明确 `跨口径参考（Legacy → SH_SZ_A_NO_B_NO_BJ_V1）`。
- 验收标准应允许 method boundary 作为一个**诚实、结构化、可泛化的 PASS 分支**，前提是页面仍完整呈现并明确不可比性。

## Q3 情绪：最终建议

选择“**按 XLSX 校正 canonical，再验**”，不是“仅有限性”。

07-17 应在展示/规范化数据中使用 ST涨停10、ST跌停32；Legacy 25/180 重复值只保留作 raw provenance。并把封板率、最高连板高度纳入最终 schema/验收，否则还没有达到 XLSX 情绪 sheet 的完整效果。

## Q4 tracks：最终建议

**16 列硬目标保留。** 但把“不可历史重建”写成 coverage 状态，不把它写成可 PASS 的永久豁免。

- 能历史回补的指标：按历史源回补并严格验。
- 需要积累窗口的指标：记录窗口成熟条件；达到条件后才可 FINAL。
- 当前免费源历史窗口不足的指标：历史日期继续 FAIL/NOT_CLOSED，直到找到可验证替代源。
- 定性 config：必须版本化并按有效期选择，不能用今天配置覆盖过去。

## Q5 验收规则：最终建议

### 不应放松

- fundFlow 行业/概念/个股 × 流入/流出六类 TOP10：范本明确存在，应保留。
- sector 行业/概念涨跌 TOP5：范本明确存在，应保留。
- tracks 16 列：最终目标明确，应保留。

### 应收紧

- northbound、margin、tracks、summary 以及榜单排序/符号/日期/单位/来源/重复项/算术一致性。
- reference date 做精确 fixture 值校验。
- 防 look-ahead 的 `publishedAt <= selectedDate` 通用规则。

### 应调整而非简单收紧/放松

- turnover 的 method mismatch：从“必须有正常环比”改成“同口径正常环比 / 方法边界诚实展示”两种可证明状态。
- northbound：从“Legacy 字段复制”改成“旧制度 Legacy / 新制度官方替代”两个明确语义分支。

---

# 6. 基线结果独立核对

在 commit `3306ba7` 的 `baseline-report.json` 中，可确认当前验收器产出的总体口径为：

- 21 个日期；07-17 PASS，其余 20 个 FAIL。
- 模块失败日期数与送审说明一致：
  - marketIndex 0
  - turnover 1
  - sentiment 19
  - sectorPerformance 19
  - fundFlow 19
  - northbound 19
  - margin 0
  - tracks 20
  - summary 0

**裁决**：这些数字可以 `CLOSED` 为“当前验收器跑分统计一致性”；但不能据此 `CLOSED` “最终范本效果验收正确性”，后者受 P1/P2 问题阻断。

---

# 7. 本轮边界与 UNKNOWN

1. 本轮未拿到原始 `A股收盘全景_20260717.xlsx` 文件本体，因此对于送审说明列出的 XLSX 数值，采用“送审材料明确声明 + 仓库快照/标准交叉核对”的证据等级；无法独立打开 Excel 逐单元格重算。**这不影响 P1-001 的成立**，因为送审说明与仓库标准/快照之间已经存在直接、自相矛盾的基线定义。
2. P0 明确是**数据侧**阶段，未做页面 headless 验收属于声明过的后续 P4 边界，本轮不把“尚无页面自动验收”另登记为新缺陷。但在 P4 完成前，P0 数据 PASS 不能被表述为“网页效果已 PASS”。
3. 本轮为只读复核，未修改任何调用方工作区文件，未运行调用方本地测试/采集任务，未重算 manifest。

---

# 8. 建议的 P0 关闭条件

建议满足以下条件后再把 R12 P0 从 HOLD 改为 PASS：

1. 重新锁定 Reference XLSX → canonical snapshot 的优先级，并消除 07-17 turnover/sentiment 的参考假阳性。
2. `template-standard.json` 与 `accept.py` 建立可验证的单一真源/版本绑定；关键 negative fixtures 全部能被拒绝。
3. 北向采用 point-in-time official replacement，并补全日期/状态/item schema 验收。
4. turnover 建立通用 method-boundary 状态机，不做 07-20 日期特判。
5. tracks 16 列的字段类型、范围、来源、coverage、窗口成熟与定性配置版本规则机器化。
6. summary 建立结构化事实一致性校验。
7. 排名/资金流/两融等补齐语义 invariant。
8. baseline report 加入标准/验收器/输入的不可变 hash 与 commit 指纹后重新生成 21 日基线。

满足后，预计 07-17 是否仍 PASS 必须由**新标准**重新决定；不能预设它必然 PASS。若 Reference XLSX 的展示字段尚未进入 canonical snapshot，则应先让 reference fixture FAIL，直到参考数据模型补齐，这比“为了让范本日 PASS 而豁免字段”更符合本阶段目标。

---

# 9. 证据与来源

## 9.1 送审材料 / 仓库证据

- `SMI_R12_P0_Review_Request.md`（本轮附件）
- `xmuhl/smi@3306ba7`：
  - `docs/acceptance/template-standard.json`
  - `docs/acceptance/template-standard.md`
  - `tools/acceptance/accept.py`
  - `work/acceptance/baseline-report.json`
  - `web/public/data/daily/2026/2026-07-17.json`
  - `web/public/data/daily/2026/2026-07-20.json`

## 9.2 北向官方披露规则

- 上海证券交易所：《关于沪港通交易信息披露机制调整相关事项的通知》，2024-07-26，自 2024-08-19 起调整。  
  https://www.sse.com.cn/lawandrules/sselawsrules2025/global/hkexsc/c/c_20250613_10781806.shtml
- 深圳证券交易所：《关于深港通交易信息披露机制调整相关事项的通知》，2024-07-26，自 2024-08-19 起调整。  
  https://www.szse.cn/szhk/hkbussiness/news/t20240726_608353.html
- 上海证券交易所：《沪深港交易所宣布同步调整沪深港通交易信息披露机制》，2024-04-12。  
  https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20240412_10753188.shtml

以上官方资料共同支持：北向调整后日度仍披露成交活跃信息，但日度净买卖方向/净流入不可按原制度官方还原；季度披露上季度末持仓数量。
