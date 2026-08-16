# SMI R12 P0.1 只读复审报告

- 评审对象：SMI R12 P0.1（R12 P0 HOLD 的修订轮）
- 送审请求：`SMI_R12_P01_Review_Request.md`
- 送审 commit：`ac1963ca5dab9388574557c8fa5f55a88aa7a5d3`
- 基线：`3306ba7fdd025627f92d945150d4f79f9c084621`
- 复核模式：**只读复核**；未修改送审仓库，未声称在调用方本地重新执行 pytest/manifest/构建
- CWA_REQUEST_ID：`cwa-smi-r12-p01-20260816`

## 1. 总体结论

**结论：HOLD，不满足“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”的条件。**

本轮方向较 P0 明显收紧，尤其是 07-17 turnover/sentiment canonical 校正、状态机、typed tracks、summary 文本门禁、跨模块 invariant 框架和 provenance 字段都已经真实进入代码/数据；但独立复核发现，送审声明的若干“硬门禁”仍存在可构造假阳性路径。

### 本轮裁决汇总

- 上轮 9 项：**1 CLOSED / 8 NOT_CLOSED**
- 新增问题：**1 项 P3**（交付证据数字/集合不一致）
- 当前 NOT_CLOSED 严重度：**P1×3 / P2×4 / P3×2，共 9 项**

> 注意：这里的 9 项 NOT_CLOSED = 上轮遗留 8 项 + 本轮新增 1 项；不是把已闭环问题重复登记。

### 上轮 9 项逐项状态

| 编号 | 严重度 | 本轮裁决 | 核心原因 |
|---|---:|---|---|
| SMI-R12-P0-001 | P1 | **NOT_CLOSED** | `referenceAssertions` 声明很多，但“缺失期望项可跳过/部分字段未消费”，07-17 仍可产生 `INV-REF-EXACT=true` 假阳性。 |
| SMI-R12-P0-002 | P1 | **NOT_CLOSED** | 单一真源仍存在 handler 绕开标准字段、ruleVersion 未真正绑定、northbound/tracks 声明未完全消费。 |
| SMI-R12-P0-003 | P1 | **NOT_CLOSED** | OFFICIAL_REPLACEMENT 未强制 `asOf/publishedAt` 存在；PIT 只在字段存在时比较，删除字段仍可绕过。 |
| SMI-R12-P0-004 | P2 | **NOT_CLOSED** | MISMATCH 分支未实现标准所写 `nonComparable=true` 硬门禁，跨口径参考字段也可整体缺失。 |
| SMI-R12-P0-005 | P2 | **CLOSED** | 07-17 ST=10/32、封板率43.75、2连板、correctionReason/rawLegacy 与 reference assertions 已形成 canonical 可执行验收。 |
| SMI-R12-P0-006 | P2 | **NOT_CLOSED** | 16 列 typed 已增强，但配置生效区间、item 日期、占位禁用、窗口成熟、score/decision 可推导性仍未机器闭环。 |
| SMI-R12-P0-007 | P2 | **NOT_CLOSED** | summary 仍未做到结构化事实一致性；07-17 已存在 turnover 与 marketEnvironment 自相矛盾但仍 PASS。 |
| SMI-R12-P0-008 | P2 | **NOT_CLOSED** | 宣称 9 条 invariant，执行结果实际只有 8 条；`INV-ENUM-SOURCE-METHOD` 未进入 `results`，且若干 invariant 仍是条件式/部分覆盖。 |
| SMI-R12-P0-009 | P3 | **NOT_CLOSED** | baseline provenance 的 `repoCommit` 仍是旧基线 `3306ba7...`，并非本轮被审输入的稳定提交树。 |

---

## 2. 独立核验范围与证据

本轮实际核对了：

1. GitHub commit `ac1963c` 与基线 `3306ba7` 的真实差异：标准 JSON/MD、`accept.py`、新增 `test_accept.py`、07-17 快照、baseline report 等确有增量修订。
2. `docs/acceptance/template-standard.json` v2 的 fields/items/lists/referenceAssertions/crossModuleInvariants。
3. `tools/acceptance/accept.py` 的通用校验器、各复杂 handler、reference assertion dispatcher、9 条 invariant 实现、startup self-check、report provenance。
4. `tools/acceptance/test_accept.py` 的测试数量与实际测试性质。
5. `web/public/data/daily/2026/2026-07-17.json` revision 4 的 turnover/sentiment/tracks/summary canonical 数据。
6. `work/acceptance/baseline-report.json` 的 07-17 PASS、08-14 与 19 个历史日期的模块失败集合及 provenance。
7. 北向官方披露边界再次按上交所/深交所 2024-07-26 调整通知复核：自 2024-08-19 起，沪/深股通日度仍披露成交总额/笔数、ETF成交额、前十大活跃证券及成交总额；季度披露上季末单只证券合计持有数量。该业务方向本轮没有问题，问题在 PIT 门禁实现不完整。

---

# 3. 逐项复核

## SMI-R12-P0-001 — 参考金标仍可假阳性

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**：
  - `template-standard.json` → `referenceAssertions.2026-07-17.marketIndex`
  - `accept.py::_ref_match_items_by_name`
  - `accept.py::_run_reference_assertions`
  - `2026-07-17.json::modules.marketIndex`
- **已确认整改**：turnover、sentiment 等参考值已按 XLSX canonical 化；方向正确。
- **仍未闭环证据**：
  1. 标准 `marketIndex.displayRules` 明确写“范本日须能同时展示 9 项”，`referenceAssertions` 也包含“科创综合”。
  2. 实际 07-17 快照仍只有 8 项，没有“科创综合”。
  3. `_ref_match_items_by_name` 对 expected 中存在但 actual 缺失的名称执行 `continue`，即**不报错**。
  4. 因 `requiredCodes` 仅强制 6 个核心指数，故当前 8 项快照仍可让 `INV-REF-EXACT=true`。
  5. 这不是唯一未消费路径：
     - northbound 的 reference expected 包含 `netBuyTop10/netSellTop10`，但 `_ref_match_northbound` 只核三项净流入标量；
     - margin reference expected 有 8 个范本值，dispatcher 只取 4 个余额/变动字段；
     - summary reference expected 有 `segmentCount/riskWarningMustContain`，`_run_reference_assertions` 没有 summary 分支。
- **根因**：标准中“声明了 reference assertion”与“该 assertion 被执行器消费”仍是两件事；缺少 assertion coverage/未消费即失败机制。
- **影响**：07-17 的 PASS 仍不足以证明“所有范本断言已经被精确执行”，因此不能作为最终金标硬门禁。

**[FIX:SMI-R12-P0-001] 建议**

- reference matcher 对 expected 项必须 fail-closed：expected 中每一个 key/list item 都要产生 consumed 记录；缺 actual 即 FAIL，禁止 `continue`。
- 启动或测试阶段统计 `declaredAssertions == consumedAssertions`；出现未消费 assertion 直接退出。
- 参考日 marketIndex 明确要求标准中的完整 reference name/code 集合，而不是只要求 6 core codes。
- northbound/margin/summary 的 reference expected 要全部进入 dispatcher 或明确删除非门禁字段，不能“标准有、执行器忽略”。

---

## SMI-R12-P0-002 — “单一真源 + ruleId/ruleVersion 绑定”仍不成立

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**：`accept.py::startup_self_check`、`check_northbound`、`check_tracks`
- **已确认整改**：通用 `_validate_field_values/_validate_items/_validate_lists` 已真实存在并覆盖部分模块，较 P0 明显进步。
- **仍未闭环证据**：
  1. `check_northbound` 只要找到了 `mode` spec，就只手工校验 mode；`sourceSystem`、`officialDisclosureCompatible` 等同一 `fields` 声明不会进入 `_validate_field_values`。
  2. `check_tracks` 不调用模块级 `_validate_field_values`。标准把 `configVersion/effectiveFrom/effectiveTo/sourceSystem` 都声明为 required，但代码对 `legacy` 明确豁免 effectiveFrom/effectiveTo，且未校验 sourceSystem。
  3. `startup_self_check` 只检查 `ruleVersion` 是否“存在/非零”，不校验 handler 支持的**具体版本**。标准把 ruleVersion 从 1 改为 2，当前 self-check 仍可通过。
  4. `_COMPLEX_HANDLERS` 并未真正驱动 dispatch；实际 dispatch 仍由固定 `CHECKERS` 字典完成，因此所谓“ruleId 绑定 handler”更多是存在性检查，而不是 fail-closed 路由契约。
- **影响**：标准可以被修改而执行行为不变，或执行器可以绕开标准 required 字段；上一轮“文档收紧但门禁没收紧”的根因尚未完全消除。

**[FIX:SMI-R12-P0-002] 建议**

- 复杂 handler 也必须先统一执行标准 fields/items/lists，再在其上叠加复杂语义；若需状态豁免，豁免规则也应声明在标准，不在代码私自特判。
- 将 `_COMPLEX_HANDLERS` 改为 `ruleId -> {supportedRuleVersion, callable}` 的真实 dispatch 真源；未知 ruleId/版本立即启动失败。
- startup self-check 验证“所有标准字段被某个 generic/handler plan 消费”，避免静默未消费。

---

## SMI-R12-P0-003 — 北向 PIT 防 look-ahead 仍可通过“删字段”绕过

- **严重度**：P1
- **状态**：**NOT_CLOSED**
- **定位**：`accept.py::check_northbound`、`run_cross_module_invariants::INV-NORTHBOUND-PIT`
- **已确认整改**：严格 mode 枚举、legacy/official 两分支、quarterlyHolding.items 非空与字段检查均已落地；方向正确。
- **阻断点**：
  - official 分支：
    - `asOf = qh.get("asOf")`
    - `publishedAt = qh.get("publishedAt")`
    - 仅当值 `is not None` 时才检查是否 `> tradeDate`。
  - 因此 `quarterlyHolding` 只要 `status=FINAL`、`items` 非空并带 6 个 item 字段，就算完全删除 `asOf/publishedAt`，仍没有这两项 gap。
  - `INV-NORTHBOUND-PIT` 同样只在字段是 string 时比较，不要求字段存在。
- **额外边界**：当前使用字符串直接与 `YYYY-MM-DD tradeDate` 比较；若 `publishedAt` 将来存 ISO datetime（如同日 `2026-08-14T18:00:00+08:00`），字典序与日期语义并不等价，应先解析成明确的 date/datetime 语义。
- **影响**：无法证明季度持仓在所选历史日期当时已经公开，PIT 核心安全目标仍可被绕过。

**[FIX:SMI-R12-P0-003] 建议**

- OFFICIAL_REPLACEMENT 强制 `asOf`、`publishedAt` 为 required 且可解析；缺任一字段即 FAIL。
- 使用 date/datetime parser 比较，不用裸字符串比较。
- PIT invariant 对缺失也应返回 false，而非只拦未来值。
- 增加至少 3 个 mutation：删除 asOf、删除 publishedAt、publishedAt 为未来时间。

---

## SMI-R12-P0-004 — 跨口径状态机主体已成型，但 nonComparable 契约未执行

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：`template-standard.json::turnover`、`accept.py::check_turnover`
- **已确认整改**：COMPARABLE/PREVIOUS_UNAVAILABLE/PREVIOUS_METHOD_MISMATCH 三态和 COMPARABLE 两个算术恒等已实现，且没有 07-20 日期特判。
- **未闭环点**：
  1. 标准明确要求 MISMATCH 的跨口径参考“带 `nonComparable=true`”；但标准 fields 中没有该字段，checker 也完全不检查。
  2. MISMATCH 分支允许 `crossMethodReferencePrevious/Delta/ChangePct` 三项全部不存在仍 PASS；若最终目标仍要求四格达到范本信息密度，这会退化为无参考值。
  3. 若 `crossMethodReferencePrevious` 存在，代码也没有要求 delta/changePct 同时完整存在并满足自身算术关系。
- **影响**：可以构造“标记为 MISMATCH、但没有非可比声明/没有可展示参考值”的数据仍通过，页面契约与验收契约不一致。

**[FIX:SMI-R12-P0-004] 建议**

- 将跨口径参考改成结构化块（或等价字段组），至少 required：previous/delta/changePct/nonComparable/currentMethod/previousMethod。
- `nonComparable` 必须严格为 `true`；三项数值必须成组出现并满足内部算术关系。
- 如果业务允许“不展示跨口径参考”，标准须明确该分支的页面降级规则；否则当前目标应强制存在。

---

## SMI-R12-P0-005 — Legacy 情绪校正

- **严重度**：P2
- **状态**：**CLOSED**
- **证据**：
  - 07-17 canonical 已为 non-ST涨停25 / ST涨停10 / non-ST跌停180 / ST跌停32。
  - `limitSealRatePct=43.75`、`maxLimitUpStreak="2连板"` 已进入 canonical。
  - `correctionReason=LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX`。
  - rawLegacy 保留原始 25/180。
  - sentiment reference matcher 对上述 canonical 值做值级断言，非参考日 required fields 也会被 generic field validator 拦截。
- **裁决**：上一轮该问题的核心根因已消除，不再登记新问题。

---

## SMI-R12-P0-006 — tracks 16 列 typed 已增强，但“历史可用性/版本时序/派生正确性”仍未闭环

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：`template-standard.json::tracks`、`accept.py::check_tracks/_validate_items`
- **已确认整改**：16 列确已逐列声明类型/范围/枚举，displayRules 也已从 8 列升级到最终 16 列目标。
- **仍未闭环点**：
  1. 标准 fields 声明 `effectiveFrom/effectiveTo/sourceSystem` required；handler 对 legacy 私自豁免 effectiveFrom/effectiveTo，且 sourceSystem 未验证。
  2. 非 legacy 只检查 effectiveFrom/effectiveTo “非空”，没有验证 `effectiveFrom <= tradeDate <= effectiveTo`，因此“今天配置倒灌旧日期”仍可发生。
  3. item 的 `date` 只做 string 类型，不要求 `date == tradeDate`；跨模块 DATE invariant 也不扫描 tracks items。
  4. `coreCatalyst/earningsRealization` 虽有中文/minChars，但 `_validate_items` 不使用全局 `rejectedPlaceholders`，所以“暂无/待补/未知”等占位仍可能通过。
  5. `redStockRatio` 只校验正则 `%`，没有 0~100 上限，`999%` 可通过。
  6. 标准 notes 已写“score/decision 必须可由输入指标+规则版本推导”“窗口未成熟不得完整 PASS”，但验收器没有：
     - historyCoverageStart/windowRequiredDays/windowMatured；
     - score 重算；
     - score→decision 映射一致性；
     - 指标 source/asOf/methodVersion 的机器校验。
- **影响**：16 个字段“长得像正确数据”即可 PASS，仍不足以证明历史日的数据是当时可得、窗口已成熟、并按对应规则版本计算。

**[FIX:SMI-R12-P0-006] 建议**

- 将配置生效区间、source/methodVersion、窗口成熟度从 notes 升级为 fields/规则。
- 强制 tracks.item.date==tradeDate，effective 区间覆盖 tradeDate。
- 文本字段复用 rejectedPlaceholders。
- 解析百分比并限制 0~100。
- 至少对 score/decision 建立可复算 handler 或 deterministic mapping；输入不完整/窗口未成熟只能 FAIL/INSUFFICIENT，不可正常 FINAL PASS。

---

## SMI-R12-P0-007 — summary 仍未实现“事实锚点一致性”

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：`accept.py::check_summary`、07-17 快照 summary
- **已确认整改**：8 段长度、非参考日 CJK 比例、占位词、风险提示、底层非 FINAL 缺口词均已进入验收器。
- **可证明反例**：
  - 07-17 turnover 已校正成：`comparisonStatus=COMPARABLE`、`turnoverPrevious=24035.65`、`turnoverDelta=2513.93`、`turnoverChangePct=10.46`。
  - 但同一 07-17 summary.marketEnvironment 仍写：**“暂无可比较的前一交易日快照。”**
  - 当前 07-17 仍整体 PASS。
- **代码原因**：
  1. reference 日故意跳过 CJK/placeholder 检查，注释称 summary reference assertion 会兜底，但 `_run_reference_assertions` 根本没有 summary 分支。
  2. tracks 依赖检查虽然读取了 `track_names`，实际却硬编码只搜索 `["高股息", "电力"]` 两个子串，没有校验四赛道数量、score、decision 或实际 trackName。
  3. 没有把 turnover/sentiment/fundFlow/margin 等结构化事实锚到 summary 各段。
- **影响**：summary 可以与底层模块事实矛盾仍 PASS，上一轮提出的“事实一致性”核心尚未解决。

**[FIX:SMI-R12-P0-007] 建议**

- 优先采用结构化 `facts`（或 rule-engine 输入快照）并与底层模块逐字段比对；文本只做呈现层最小门禁。
- 至少先补：marketEnvironment↔turnover、trackConclusion↔tracks、margin↔margin、northbound↔northbound 的事实锚点。
- 修正 07-17 stale marketEnvironment 文案并加 mutation，确保未来回归会 FAIL。

---

## SMI-R12-P0-008 — 9 条跨模块 invariant 实际只产出 8 条

- **严重度**：P2
- **状态**：**NOT_CLOSED**
- **定位**：`accept.py::run_cross_module_invariants`、`baseline-report.json::dates.*.invariants`
- **直接证据**：
  - 代码开头声明 `_INVARIANT_IDS` 共 9 个，其中包含 `INV-ENUM-SOURCE-METHOD`。
  - `run_cross_module_invariants` 对该项只有一行注释：`各模块 source/method 枚举合法，由通用引擎覆盖`，没有 `results["INV-ENUM-SOURCE-METHOD"] = ...`。
  - baseline 的 07-17/历史日期 invariants 实际也只有 8 个 key，明确缺该项。
- **其它部分覆盖问题**：
  - `INV-UNIT-亿元` 只在 unit 字段“存在且错误”时 FAIL；unit 缺失不会失败。
  - DATE invariant 只扫模块顶层 dataDate/asOf/publishedAt，不扫 tracks.items.date 等 nested 时序字段。
  - northbound legacy list invariant 只查正负号，不查排序/唯一性；reference matcher 又不消费 top10 expected。
  - `INV-MARGIN-IDENTITY` 的 cross invariant 本身只复核总量恒等，没有把标准描述中的 `marginBalanceChange` 环比结果写入该 invariant；模块 checker 里前日缺失时还会记 note 而非 fail。
- **影响**：报告宣称“9 条全 true”在结构上就不成立，且 invariant 层不能作为完整语义兜底。

**[FIX:SMI-R12-P0-008] 建议**

- startup self-check 强制 `set(standard.crossModuleInvariants.ids) == set(_INVARIANT_IDS) == set(run结果keys)`。
- 每一 invariant 必须有独立 mutation 测试；不能用“别处应该覆盖”替代该 invariant 的结果产出。
- unit/date/nested list 等要按标准的 enforce 范围做 required/递归检查。

---

## SMI-R12-P0-009 — provenance 有字段，但未绑定本轮稳定输入树

- **严重度**：P3
- **状态**：**NOT_CLOSED**
- **定位**：`work/acceptance/baseline-report.json::provenance.repoCommit`
- **证据**：
  - 送审 commit 是 `ac1963ca5dab...`。
  - baseline report 内 `repoCommit` 却是 **`3306ba7fdd0...`**，即上一轮基线 commit。
  - 这说明报告是在未提交/不同提交状态下生成；虽然 standard/acceptor/manifest/snapshot 各自有 SHA256，但 `repoCommit` 不能定位出本次被验收输入集合。
- **影响**：无法仅凭 provenance 从 Git 历史恢复“报告对应的代码+标准+数据”组合；上一轮提出的复验可追溯目标未完成。

**[FIX:SMI-R12-P0-009] 建议**

- 不要试图让“包含报告自身的同一 commit”自引用自身 SHA（这是递归问题）。推荐二选一：
  1. **两提交法**：先提交 code/standard/data（输入 commit A），在 clean tree 上跑验收，报告记录 `evaluatedCommit=A`；再以 commit B 只提交报告；
  2. **输入树指纹法**：记录 `evaluatedTreeSha`/`dirty=false` + 关键输入 SHA256，不要求报告所在 commit 与 evaluated commit 相同。
- 报告必须明确 `evaluatedCommit` 与 `reportCommit` 的不同语义。

---

# 4. 本轮新增问题

## SMI-R12-P01-010 — 送审摘要与仓库证据存在数字/失败集合漂移

- **严重度**：P3
- **状态**：**NOT_CLOSED**
- **定位**：`SMI_R12_P01_Review_Request.md`、当前送审说明、`test_accept.py`、`baseline-report.json`
- **证据 1：测试数量口径**
  - 送审主述称“20/20 负向变异测试”。
  - 实际 `test_accept.py` 明确是 **18 个负向 + 2 个正向 = 20 tests**。
  - 送审附件 §二本身也写“20/20 绿（18负向变异+2正向）”，与前面的“20 个负向”自相矛盾。
- **证据 2：历史 19 日失败集合**
  - 送审附件称 07-20~08-13 的失败集合为 `{sentiment, sectorPerformance, fundFlow, northbound, tracks}`。
  - baseline report 的 `moduleFailCounts.summary = 19`；07-20 的 summary 也明确 FAIL（`marketEnvironment` 含占位词“暂无”、`riskWarning` CJK 比例不足）。
  - 因此历史 19 日真实失败集合还包含 `summary`。
- **影响**：不改变代码本身门禁，但会误导后续 P1/P2 回补范围与评审对测试覆盖率的判断。

**[FIX:SMI-R12-P01-010] 建议**

- 统一表述为“20 tests = 18 negative mutation + 2 positive regression”。
- 送审请求中的 baseline 摘要直接从 `baseline-report.json` 自动生成，禁止手抄模块集合/计数。

---

# 5. 对用户三个复审问题的直接回答

## 5.1 上轮 9 项是否全部 CLOSED？

**否。** 本轮仅 `SMI-R12-P0-005` 可判 CLOSED；其余 8 项仍有可复验的未闭环路径。

## 5.2 当前验收口径是否已经等价表达“任意日期达到 07-17 范本效果（数据侧）”？

**尚不能。**

主要阻断不是“缺更多数据源”，而是验收器本身仍允许以下假阳性：

- reference expected 缺失项不一定 fail；
- reference assertions 并非全部被执行；
- 北向 PIT 字段可删除绕过；
- tracks 的时序/窗口/派生正确性尚未机器化；
- summary 可与结构化模块事实冲突；
- 9 条 invariant 实际只输出 8 条。

因此当前 07-17 PASS 只能说明“通过了 v2 当前实现的门禁”，还不能作为最终范本等价证明。

## 5.3 是否可声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”？

**不可。** 当前为 **9 NOT_CLOSED（P1×3 / P2×4 / P3×2）**。

---

# 6. 推荐下一轮最小整改顺序

1. **先修 P1-001**：reference assertion 必须 fail-on-missing，并做 declared/consumed coverage；把 northbound/margin/summary 未消费 reference 项补齐。
2. **再修 P1-003**：PIT 强制 asOf/publishedAt required + 解析后比较，补 3 个负向 mutation。
3. **同时修 P1-002**：复杂 handler 先统一消费标准字段；ruleId+ruleVersion 真实绑定并 fail-closed。
4. **修 P2-008**：让 9 条 invariant 真的得到 9 个 result，并一条一条有 mutation。
5. **修 P2-007/P2-006/P2-004**：summary 事实锚点、tracks 时序/窗口/派生、turnover nonComparable 契约。
6. **最后重生成 baseline + provenance**，并由报告自动生成送审摘要，消除 P3 数字漂移。

完成后再跑全量 baseline；只有 reference PASS 不再存在上述假阳性、且旧 9 项全部 CLOSED、无新问题时，才适合声明 ChatGPT 侧收敛。
