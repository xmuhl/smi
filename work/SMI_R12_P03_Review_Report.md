# SMI R12 P0.3 只读复审报告

- 评审对象：SMI R12 P0.3（对 P0.2 剩余 5 项 NOT_CLOSED 的收口轮）
- 送审请求：`SMI_R12_P03_Review_Request.md`
- 被验收输入 commit：`c9e278284dc42a43e228e7026d2c1ed606ee9c14`
- 基线报告提交：`2f955f0`（独立核对：相对 `c9e2782` 仅修改 `work/acceptance/baseline-report.json`）
- 复核模式：只读复核；未修改送审仓库，也不声称在调用方环境重新执行 112 项测试
- CWA_REQUEST_ID：`cwa-smi-r12-p03-20260816`

## 1. 总体结论

**结论：HOLD，尚不能声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

P0.3 的修订方向明显收敛：generic ruleVersion 版本绑定、严格 ISO 解析、tracks 生效区间 fail-closed、`summaryFacts` 机读执行、9 invariant 的多个弱语义均已真实进入 `accept.py`。但源码独立复核仍发现 3 个既有问题未完全闭环，并新增 1 个测试证据覆盖问题。

### 本轮裁决汇总

- 上轮 5 项：**2 CLOSED / 3 NOT_CLOSED**
- 新增：**1 项 NOT_CLOSED**
- 当前合计：**P1×1 / P2×2 / P3×1，共 4 NOT_CLOSED**
- 因此本轮不能写“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

### 逐项状态

| 编号 | 严重度 | 裁决 | 核心结论 |
|---|---:|---|---|
| SMI-R12-P0-002 | P1 | **CLOSED** | generic 与 complex 均已 `ruleId -> {supportedVersions, handler}`；nested DSL 已递归执行；summaryFacts 已由 checker 读取。 |
| SMI-R12-P0-003 | P1 | **NOT_CLOSED** | strict date 已修，但 nested `percentString` 正则写错，`numericString` 又允许 NaN/Infinity/负值；OFFICIAL 持仓 typed 门禁仍可误拒真值/放过垃圾值。 |
| SMI-R12-P0-006 | P2 | **CLOSED** | effective 区间已严格解析并 fail-closed；重算 trackId 集合强等；当前 `score_tracks` 对每个输入恰好 append 一条结果，现有实现下集合完整性闭环。 |
| SMI-R12-P0-007 | P2 | **NOT_CLOSED** | Legacy/两融方向和量能数值锚已补，但 OFFICIAL northbound summary 仍只需命中任一“停发/季度/披露/不再”词，可同时虚构“官方日度净流入”。 |
| SMI-R12-P0-008 | P2 | **NOT_CLOSED** | unit invariant 的实现仍与标准 `enforce` 冲突：turnover/margin 未在模块 fields 声明 required unit，运行时会直接跳过，删除 unit 仍可得到 invariant=true。 |
| SMI-R12-P03-001 | P3 | **NOT_CLOSED（新增）** | 20 个 acceptance tests 未新增 P0.3 关键 mutation/positive；因此 nested DSL 的正则错误在“112 全绿”下仍未被发现。 |

---

## 2. 独立核验范围与事实

本轮实际核对了：

1. `c9e2782` commit 的真实修改内容；
2. `tools/acceptance/accept.py`：
   - `_COMPLEX_HANDLERS/_GENERIC_HANDLERS`
   - `startup_self_check/_build_checkers`
   - `_parse_iso_date_strict`
   - `_required_condition_met`
   - `_validate_nested_value/_validate_sub_field/_validate_field_values`
   - `check_northbound`
   - `check_tracks/_recalc_tracks`
   - `_run_summary_facts/check_summary`
   - `run_cross_module_invariants`
3. `docs/acceptance/template-standard.json`：
   - generic ruleVersion
   - northbound quarterlyHolding nested DSL
   - tracks `dateString`
   - summaryFacts
   - crossModuleInvariants
4. `collector/calculators/tracks.py::score_tracks`；
5. `tools/acceptance/test_accept.py`；
6. `2f955f0:work/acceptance/baseline-report.json`；
7. `c9e2782 -> 2f955f0` 提交差异。

独立确认的基线事实：

- `2f955f0` 相对 `c9e2782` **仅修改 `work/acceptance/baseline-report.json`**，两提交法结构成立；
- baseline provenance 为：
  - `repoCommit = evaluatedCommit = c9e278284dc42a43e228e7026d2c1ed606ee9c14`
  - `dirty = false`
- 07-17 报告记录 **9/9 模块 PASS + 9/9 invariant=true**；
- 本轮不把“112 项测试本端已重新运行”作为证据；112 全绿是送审方本地执行声明。

---

# 3. 上轮五项逐项裁决

## SMI-R12-P0-002 — 单一真源 / dispatch / nested DSL

- **严重度**：P1
- **状态**：**CLOSED**

### 证据

1. `_GENERIC_HANDLERS` 已与 complex handler 相同，采用：
   `ruleId -> {supportedVersions, handler}`。
2. `startup_self_check` 对 generic 分支实际检查：
   `ruleVersion in supportedVersions`，不支持则写入 errors，主流程退出码 3。
3. `_validate_nested_value/_validate_sub_field` 已实现 object.subFields、array.itemFields、dateString、numericString、boolean、enum 等递归消费。
4. `_validate_field_values` 会把 object/array/dateString/numericString 等委托到 nested validator。
5. `check_summary` 已真实读取 `spec["summaryFacts"]` 并调用 `_run_summary_facts`。

### 裁决说明

上一轮 P0-002 的**架构性根因**——generic 版本不绑定、nested/summaryFacts 只是“标准声明但执行不消费”——已经消除。

本轮发现的 `percentString/numericString` 类型实现错误属于 **P0-003 的北向 typed schema 真实性问题**，不重复计入 P0-002。

---

## SMI-R12-P0-003 — Northbound strict PIT + typed holdings

- **严重度**：P1
- **状态**：**NOT_CLOSED**

### 已闭环部分

严格日期解析已真实修复：

- 长度 10：全串 `date.fromisoformat`
- datetime：全串 `datetime.fromisoformat`
- 垃圾后缀不再截前 10 位放行
- OFFICIAL `asOf/publishedAt` 缺失、不可解析、晚于 tradeDate 均 FAIL

`quarterlyHolding` 也确实通过 nested DSL 递归到 `items.itemFields`。

### 阻断 1：nested percentString 正则写错

`accept.py::_validate_nested_value` 当前源码为：

```python
re.fullmatch(r"d+(.d+)?%", val)
```

而不是：

```python
re.fullmatch(r"\d+(\.\d+)?%", val)
```

独立语义复验：

- `"0.93%"` → **不匹配**
- `"85%"` → **不匹配**
- `"d%"` → **匹配**
- `"dd.dd%"` → **匹配**

因此本轮宣称的真实 HKEX `pctOfIssued="0.93%"` 会被验收器错误拒绝，而形如 `"dd.dd%"` 的垃圾值反而能通过 nested percentString。

### 阻断 2：numericString 只要求 `float()` 可解析，不保证 finite/nonnegative

当前逻辑：

```python
float(val.replace(",", "").strip())
```

没有 `math.isfinite`，也没有 `>=0`。

因此以下值都可通过 `shareholding:numericString`：

- `"4,401,900"`：合法
- `"-5"`：**也通过**
- `"NaN"`：**也通过**
- `"Infinity"`：**也通过**

而持仓数量的业务语义应至少是 finite 且非负。

### 可构造的错误 PASS

在其它 OFFICIAL 字段均合法时：

- `shareholding = "NaN"`
- `pctOfIssued = "dd.dd%"`
- `market = "sh"`
- `asOf/publishedAt` 合法且不 look-ahead

nested DSL 的上述两个字段都可能通过；`check_northbound` 已把逐项 typed 校验委托给 DSL，不再有第二层数值真实性校验。

### [FIX:SMI-R12-P0-003]

建议最小修订：

1. `percentString` 使用真正的数字百分比全串正则；
2. 将 `shareholding` 定义为能表达逗号字符串但同时要求 `finite + nonnegative` 的 kind，例如 `nonNegativeNumericString`；
3. `pctOfIssued` 建议再明确 0~100 范围；
4. 增加 OFFICIAL **正向 fixture**，真实形态至少覆盖：
   - `"4,401,900"`
   - `"0.93%"`
   - `market="sh"/"sz"`
5. 负向覆盖：
   - `"dd.dd%"`
   - `"NaN"/"Infinity"/"-5"`
   - 非法 ISO suffix
   - 非法 market。

---

## SMI-R12-P0-006 — tracks 时序 / 生效区间 / 重算完整性

- **严重度**：P2
- **状态**：**CLOSED**

### 证据

1. `effectiveFrom/effectiveTo` 已改成 `kind=dateString`。
2. `check_tracks` 又显式使用 `_parse_iso_date_strict`；任一值不可解析时直接 `_detail_gap`，不会再跳过区间比较。
3. 解析成功后执行 `effectiveFrom <= tradeDate <= effectiveTo`。
4. `_recalc_tracks` 强制：
   `set(recomputed.trackId) == set(snapshot.trackId)`，空集合也 FAIL。
5. `collector.calculators.tracks.score_tracks` 当前实现对 `tracks_input` 每项恰好 append 一条输出，未做过滤，因此在当前受审版本中，配合 snapshot `uniqueBy=trackId` 与集合强等，可覆盖上一轮“计算器只返回子集”问题。
6. 标准 notes 已改成：Legacy 参考日以 referenceAssertions 为唯一金标，不做 score 重算，与实现一致。

### 裁决

上一轮三个具体未闭环点均已消除。本轮不再保留 P0-006。

> 非阻断建议：未来如 `score_tracks` 改成可能过滤/展开输入，可再增加显式 `len(recomputed)==len(items)` 作为防御；当前版本不是阻断项。

---

## SMI-R12-P0-007 — summary 结构化事实一致性

- **严重度**：P2
- **状态**：**NOT_CLOSED**

### 已闭环部分

`summaryFacts` 已真正由标准驱动执行，且新增：

- turnover：禁词 + volumeState 词 + today/previous/delta 整数锚；
- margin：marginBalanceChange 正负对应增减词；
- northbound Legacy：totalNetInflow 正负对应净流入/净流出；
- tracks：赛道名称片段 + decision 提及。

这些修订已经关闭上一轮“margin/netflow 可以直接说反”的主要 Legacy 路径。

### 剩余阻断：OFFICIAL_REPLACEMENT 文本仍可虚构“官方日度净流入”

标准本身要求 OFFICIAL 体现 point-in-time/季度替代口径，且不得把官方日度净流入当连续序列。

但 `_run_summary_facts` 当前 OFFICIAL 检查只是：

```text
officialWords = ["停发", "季度", "披露", "不再"]
只要命中其中任意一个词即可
```

即使用的是 `any(...)`，没有：

- 强制“季度/PIT”语义；
- 强制“停发/不再披露日度净流入”语义；
- 禁止出现“官方日度净流入/连续净流入”等相反断言。

因此例如下面这种**事实错误**文本仍可命中“披露”而通过该分支：

> “北向官方披露日度净流入 100 亿元，已连续三日净流入。”

只要其它 summary 通用约束满足，就不能由当前 OFFICIAL fact anchor 拦住。

### [FIX:SMI-R12-P0-007]

建议把 OFFICIAL summaryFacts 改为机读组合约束，例如：

- `mustContainAny`: `["停发","不再"]`
- `mustContainAny`: `["季度","point-in-time","时点"]`
- `mustNotContain`: `["官方日度净流入","连续净流入","今日北向净流入"]`

或更稳妥地让 summary 直接引用结构化 `northbound.mode` 与 `quarterlyHolding.asOf` 生成事实片段，而不是只做关键词存在性检查。

### 说明

本轮“marketEnvironment 只锚整数部分”是送审方明确采用的 P0.3 契约，本报告不把小数精度继续升级为新阻断；当前阻断只针对 **OFFICIAL 语义方向仍可说反**。

---

## SMI-R12-P0-008 — 9 条 invariant enforce 语义

- **严重度**：P2
- **状态**：**NOT_CLOSED**

### 已闭环部分

本轮以下整改真实存在：

- sentiment FINAL 任一宽度计数非 finite → invariant=false；
- margin 非参考日找不到前一 FINAL margin → invariant=false；
- enum invariant 读取 `spec.allowedEnums`，并递归 tracks items；
- 9 个 invariant key 继续全部产出；
- 参考日 margin 有显式 `referenceDateExemption`，由 INV-REF-EXACT 兜底。

### 阻断：INV-UNIT-亿元 仍可让 turnover/margin 缺 unit 时保持 true

当前标准：

```json
"spec": {
  "unit": "亿元",
  "modules": ["turnover", "fundFlow", "margin"]
},
"enforce": "... unit 缺失即 FAIL ..."
```

但 `run_cross_module_invariants` 的实现不是直接按 `spec.modules` 强制，而是先检查该模块标准 `fields` 中是否存在：

```text
name == "unit" AND required == true
```

若没有，就：

```python
continue
```

当前标准实际情况：

- fundFlow.fields：有 `unit`, required=true
- turnover.fields：**没有 unit 字段**
- margin.fields：**没有 unit 字段**

所以对 turnover 和 margin，unit invariant 会直接跳过。

这意味着可构造：

- 从 07-17 `turnover` 删除 `unit`
- 或从 07-17 `margin` 删除 `unit`

在现有模块 checker/referenceAssertions 中也没有其它 required-unit 门禁，`INV-UNIT-亿元` 仍可能保持 `true`，形成真正的整体验收假阳性。

此外标准 `desc/enforce` 文案仍写 `northbound`，而 `spec.modules` 已去掉 northbound，标准自身也需统一口径。

### [FIX:SMI-R12-P0-008]

两种方案任选其一并保持单一真源一致：

**方案 A（推荐）**
- 在 turnover.fields、margin.fields 显式增加：
  `{"name":"unit","kind":"enum","required":true,"enumValues":["亿元"]}`
- invariant 直接消费标准字段规则。

**方案 B**
- `INV-UNIT-亿元` 直接以 `spec.modules` 为权威：
  对列表内每个模块无条件要求 `module.unit == spec.unit`；
- 不再依赖模块 fields 是否另有 unit 声明。

同时把 invariant 的 `desc/enforce/spec.modules` 对 northbound 的口径统一。

---

# 4. 新发现问题

## SMI-R12-P03-001 — P0.3 关键门禁缺少对应 regression/mutation

- **严重度**：P3
- **状态**：**NOT_CLOSED（新增）**
- **定位**：`tools/acceptance/test_accept.py`

### 证据

当前 acceptance suite 仍是：

- 18 个负向 mutation
- 2 个正向 regression
- 共 20 tests

P0.3 仅调整了 08-14 正向/预期失败集合，并没有新增专门覆盖：

- generic ruleVersion unsupported；
- strict ISO garbage suffix；
- OFFICIAL_REPLACEMENT 合法正向 fixture；
- quarterlyHolding nested `numericString/percentString/market`；
- tracks invalid effective date；
- recalc trackId 集合不一致；
- summary margin/northbound 方向；
- INV-UNIT unit 删除；
- sentiment finite invariant；
- margin 前序缺失 invariant。

因此“112 全绿”不能证明本轮新增安全门禁本身正确；`percentString` 的明显正则错误正是在该测试结构下漏过的。

### [FIX:SMI-R12-P03-001]

建议至少补一组聚焦 P0.3 的 acceptance tests，优先：

1. OFFICIAL northbound **合法正向样本必须 PASS**；
2. `pctOfIssued="0.93%"` PASS；`"dd.dd%"` FAIL；
3. `shareholding="4,401,900"` PASS；`NaN/Infinity/-5` FAIL；
4. 删除 turnover.unit / margin.unit → `INV-UNIT-亿元=false`；
5. OFFICIAL summary 虚构“官方日度净流入” → summary FAIL；
6. generic ruleVersion 改未支持版本 → startup self-check FAIL；
7. tracks invalid effectiveFrom → FAIL；
8. recalc trackId 缺项/多项 → FAIL。

---

# 5. 基线与 provenance 裁决

## 两提交法

**通过。**

独立 GitHub compare：

- base：`c9e2782`
- head：`2f955f0`
- ahead_by=1
- 变更文件只有：
  `work/acceptance/baseline-report.json`

baseline 内：

- `evaluatedCommit=c9e2782...`
- `repoCommit=c9e2782...`
- `dirty=false`

因此本轮 provenance 结构本身没有新增问题。

## 07-17

baseline 记录：

- 9/9 模块 PASS
- 9/9 invariant=true

该结果与当前验收器在**现有 07-17 数据**上的输出一致。

但由于：

- P0-003 的 OFFICIAL typed 分支当前没有正向数据覆盖；
- P0-008 的 unit 删除可形成参考日整体假阳性；

所以“07-17 PASS”仍不能作为验收器最终收敛的充分证明。

## 08-14

送审声明的失败集合：

`{sentiment, northbound, tracks, summary}`

与本轮标准/验收器设计方向相符；summary 因旧文本缺新增数值锚而 FAIL 属于预期门禁收紧，不作为新问题。

---

# 6. 收敛判断

本轮**不能**写：

> 本轮 0 NOT_CLOSED，ChatGPT 侧已收敛

当前剩余：

1. `SMI-R12-P0-003` / P1 — Northbound nested typed validator 仍有百分比正则和 finite/nonnegative 漏洞；
2. `SMI-R12-P0-007` / P2 — OFFICIAL summary 仍可虚构日度净流入；
3. `SMI-R12-P0-008` / P2 — turnover/margin 缺 unit 时 invariant 仍可 false-positive；
4. `SMI-R12-P03-001` / P3 — P0.3 新门禁缺少针对性 regression/mutation。

建议下一轮只做以上 4 个最小增量，不需要重开 P0-002/P0-006，也不要回归已在更早轮次 CLOSED 的问题。
