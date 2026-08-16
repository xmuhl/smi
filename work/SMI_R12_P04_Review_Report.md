# SMI R12 P0.4 复审报告

- 复审轮次：R12 P0.4
- Review 深度：只读复核
- 送审输入 commit：`25b162925acb9035b435364b408b411b3a88e197`
- 代码修订 commit：`d6887774a686544d10ed13b980db55696c01cfea`
- 基线报告 commit：`ece8874`
- 前轮待闭环：`P0-003 / P0-007 / P0-008 / P03-001`
- 本轮结论：**HOLD（仅剩 P03-001 的 1 个 P3 测试覆盖余项）**
- 本轮状态：`P0-003 / P0-007 / P0-008` CLOSED；`P03-001` NOT_CLOSED
- 当前 NOT_CLOSED：**P1=0 / P2=0 / P3=1**

> 本轮为只读复核：未修改调用方工作区，也不声称在调用方本地重新执行 pytest/collector 测试。送审方声明 `test_accept.py 29/29`；源码静态计数与“20 旧 + 9 新测试函数”一致，本轮未发现测试总数数字漂移。

---

## 1. 总体裁决

P0.4 已经把 P0.3 的三个功能性阻断完整收口：

1. `P0-003`：嵌套 `percentString/numericString/dateString` 及 OFFICIAL northbound typed 分支闭环；
2. `P0-007`：OFFICIAL summaryFacts 组合约束与禁词约束已机读执行；
3. `P0-008`：turnover/margin 均显式声明 required `unit=亿元`，上一轮 unit invariant 假阳性消除，版本绑定同步。

`P03-001` 的专项回归也大幅补齐，9 个新增测试函数真实存在，且覆盖 OFFICIAL 正向、百分比垃圾、NaN/Infinity/负 shareholding、非法 ISO、generic ruleVersion、tracks effective date、recalc trackId、OFFICIAL summary 伪造日度净流入、unit 删除等路径。

但 P0.3 报告 `[FIX:SMI-R12-P03-001]` 的优先清单第 4 项明确要求：

> 删除 `turnover.unit / margin.unit` → `INV-UNIT-亿元=false`

本轮 `test_p04_unit_deleted_invariant` 只删除并验证了 `turnover.unit`，没有对应 `margin.unit` mutation。虽然当前 standard 与 invariant 实现经静态复核可确认 margin 的功能逻辑已经正确，因此 `P0-008` 可以 CLOSED；但 `P03-001` 本身是“关键门禁缺专项 regression/mutation”的覆盖问题，margin 分支仍缺前轮明确要求的回归用例，因此只能维持 **NOT_CLOSED（P3）**。

---

# 2. 前轮问题逐项裁决

## SMI-R12-P0-003 — CLOSED

- 严重度：P1（沿用）
- 状态：**CLOSED**
- 定位：`tools/acceptance/accept.py::_validate_nested_value/_parse_iso_date_strict`；`docs/acceptance/template-standard.json::northbound`

### 已核实整改

#### 2.1 percentString

嵌套 DSL 已使用数字百分比全串匹配：

- 合法形态：数字 + 可选小数 + `%`；
- 匹配后继续将百分比数值转换为 float；
- 要求 finite；
- 强制 `0 <= pct <= 100`。

因此上一轮的错误正则问题已消失：

- `"0.93%"` 可通过；
- `"dd.dd%"` 被拒；
- 越界百分比不能通过。

#### 2.2 numericString

`numericString` 在去除千分位逗号后转换 float，并继续要求：

- `math.isfinite(value)`；
- `value >= 0`。

因此：

- `"4,401,900"` 可解析；
- `"NaN"` / `"Infinity"` / `"-5"` 均被拒。

#### 2.3 严格 ISO 日期

`_parse_iso_date_strict` 不再截断前 10 位：

- 10 位日期由 `date.fromisoformat` 全串解析；
- datetime 由 `datetime.fromisoformat` 全串解析；
- 垃圾后缀解析失败返回 None，调用侧 FAIL。

#### 2.4 OFFICIAL nested typed

standard 中 OFFICIAL `quarterlyHolding.items` 已与当前 HKEX 数据形态对齐：

- `shareholding: numericString`
- `pctOfIssued: percentString`
- `market: enum ["sh", "sz"]`
- `asOf/publishedAt: dateString`
- items 非空且子字段 required。

并有基于 08-14 quarterlyHolding 形态构造的 OFFICIAL 正向测试。

### 裁决

P0.3 指出的 typed/PIT 具体绕过与误拒路径均已消除，**CLOSED**。

---

## SMI-R12-P0-007 — CLOSED

- 严重度：P2（沿用）
- 状态：**CLOSED**
- 定位：`template-standard.json::summary.summaryFacts.northbound`；`accept.py::_run_summary_facts`

### 已核实整改

OFFICIAL northbound summary 现在由标准中的机读组合约束驱动：

- 第一组至少命中：`停发 / 不再`；
- 第二组至少命中：`季度 / point-in-time / 时点`；
- 禁止送审约定的伪日度净流入措辞：
  `官方日度净流入 / 连续净流入 / 今日北向净流入`。

执行器逐组校验 `mustContainAnyGroups`，不是“全部候选词任意命中一个”的弱检查；并逐项执行 `mustNotContain`。

`test_p04_official_summary_fabricates_daily` 明确构造“北向官方日度净流入 100 亿元，已连续净流入三日”的错误文案，并要求 summary FAIL。

### 裁决

实现符合 P0.3 报告给出的收口方向，**CLOSED**。

---

## SMI-R12-P0-008 — CLOSED

- 严重度：P2（沿用）
- 状态：**CLOSED**
- 定位：turnover/margin fields、dispatch ruleVersion、`run_cross_module_invariants`

### 已核实整改

P0.4 采用上一轮推荐方案 A：

- `turnover.fields` 显式新增 required `unit`，枚举只允许 `亿元`；
- `margin.fields` 显式新增 required `unit`，枚举只允许 `亿元`；
- fundFlow 原有 required unit 保持；
- `INV-UNIT-亿元.spec.modules` 与 desc/enforce 统一为 turnover/fundFlow/margin；
- turnover/margin/summary 的 ruleVersion 与 dispatch 支持版本同步升级。

因此 invariant 当前的“只有 standard fields 声明 required unit 才检查”的实现，不再跳过 turnover 或 margin。

同时 P0.3 已确认闭环的 invariant 强化没有发生回退：

- sentiment FINAL 任一宽度计数缺失/非 finite → false；
- 非参考日 margin FINAL 找不到前一 FINAL margin → false；
- enum invariant 从标准 `allowedEnums` 执行；
- 9 个 invariant key 全部产出。

### 关于专项测试

本轮新增 `test_p04_unit_deleted_invariant` 已验证删除 `turnover.unit` 时 `INV-UNIT-亿元=false`。

虽然尚缺 margin.unit 的同构 mutation（因此 P03-001 仍保留 P3），但当前 `margin.fields` 的 unit 声明与 invariant 循环逻辑经静态复核均已存在，所以这不构成 P0-008 的功能性 NOT_CLOSED。

### 裁决

上一轮的 unit 整体验收假阳性已消除，**CLOSED**。

---

## SMI-R12-P03-001 — NOT_CLOSED

- 严重度：P3
- 状态：**NOT_CLOSED（仅剩 1 个窄覆盖余项）**
- 定位：`tools/acceptance/test_accept.py::test_p04_unit_deleted_invariant`

### 已闭环的大部分回归覆盖

P0.4 新增 9 个测试函数，真实覆盖：

1. OFFICIAL northbound 合法正向样本；
2. `pctOfIssued="dd.dd%"` 失败；正向 fixture 同时覆盖合法百分比形态；
3. `shareholding` 的 `NaN/Infinity/-5` 失败；正向 fixture 覆盖逗号数字串；
4. 严格 ISO 垃圾后缀失败；
5. generic ruleVersion unsupported 自检失败；
6. tracks invalid effectiveFrom/effectiveTo 失败；
7. recalc trackId 集合缺项失败；
8. OFFICIAL summary 虚构官方日度净流入失败；
9. turnover.unit 删除时 invariant=false。

源码中旧 20 个测试函数仍在，新 9 个测试函数也确实存在，因此“20 旧 + 9 新 = 29”这一函数/测试节点计数没有发现矛盾；多值 shareholding 检查使用的是**函数内部 for 循环**，并非 pytest parametrize，不会额外扩展收集节点。

### 剩余缺口

P0.3 报告的明确优先闭环条目为：

> 删除 `turnover.unit / margin.unit` → `INV-UNIT-亿元=false`

当前测试源码只有：

- 删除 `turnover.unit`；
- assert `INV-UNIT-亿元 is False`。

没有第二条 `margin.unit` 删除 mutation。

这意味着功能实现虽然已正确，但 margin unit 这条曾经真实存在过的验收假阳性路径还没有被专项测试锁死；将来 standard 或 invariant 重构时，margin 分支可能单独回归而现有测试无法捕获。

### [FIX:SMI-R12-P03-001]

只需补一个极小 mutation 即可，不需修改生产逻辑：

- 基于可验收 snapshot 删除 `modules.margin.unit`；
- 调用 `evaluate_modules(...)`；
- 断言：
  - `checks["margin"]["pass"] is False`（建议同时锁）；
  - `inv["INV-UNIT-亿元"] is False`。

随后用实际 pytest 输出更新测试总数（若新增独立 test 函数，则 acceptance suite 应从 29 增至 30；若合并到现有函数内部循环，则仍可保持 29，但应明确其覆盖 turnover+margin 两分支）。

闭环标准：**turnover.unit 与 margin.unit 两条删除路径均有可复验 regression/mutation。**

---

# 3. 基线与 provenance 独立核对

## 3.1 两提交法 — PASS

独立比较 `25b1629 -> ece8874`：

- ahead_by=1；
- 仅 `work/acceptance/baseline-report.json` 修改；
- 没有混入 standard、acceptor、snapshot 或测试代码改动。

因此“先固定被验收输入树，再单独提交报告”的两提交结构成立。

## 3.2 provenance — PASS

baseline-report 记录：

- `repoCommit = 25b162925acb9035b435364b408b411b3a88e197`
- `evaluatedCommit = 25b162925acb9035b435364b408b411b3a88e197`
- `dirty = false`
- standard / acceptor / manifest / per-date snapshot SHA256 均存在。

与本轮送审输入一致。

## 3.3 2026-07-17 — PASS

baseline 中：

- overall = PASS；
- 9/9 模块 pass；
- 9/9 invariant=true。

与送审声明一致。

## 3.4 2026-08-14 — 送审摘要一致

baseline 可独立确认：

- sentiment FAIL；
- northbound FAIL；
- tracks FAIL；
- summary FAIL（`marketEnvironment` 缺 `turnoverPrevious=25538`、`turnoverDelta=4115` 数值锚）；
- marketIndex / turnover / sectorPerformance / fundFlow / margin PASS。

因此失败集合确为：

`{sentiment, northbound, tracks, summary}`

这属于后续 P1/P2 数据补齐范围，不登记为本轮新 P0 问题。

---

# 4. 测试声明复核

送审方声明：`tools/acceptance/test_accept.py 29/29`。

源码独立计数：

- 原有 18 个负向 + 2 个正向 = 20 个测试函数；
- P0.4 新增 9 个测试函数；
- 合计 29 个测试函数。

其中 `shareholding` 的 NaN/Infinity/-5 是同一测试函数内的 for-loop，不是 `pytest.mark.parametrize`，因此不会额外增加 pytest node 数。

**结论：本轮不登记“29/29 数字漂移”问题。**

本轮未在调用方机器上重新执行 pytest；“29/29 passed”作为送审方本地执行事实由送审方声明，静态源码结构与其测试数量口径一致。

---

# 5. 状态汇总

| 编号 | 严重度 | 本轮状态 | 结论 |
|---|---:|---|---|
| SMI-R12-P0-003 | P1 | CLOSED | nested typed、严格日期、OFFICIAL 正向/负向均闭环 |
| SMI-R12-P0-007 | P2 | CLOSED | OFFICIAL summaryFacts 组合约束已机读执行 |
| SMI-R12-P0-008 | P2 | CLOSED | turnover/margin unit 标准声明与 invariant 语义已闭环 |
| SMI-R12-P03-001 | P3 | NOT_CLOSED | 已补 9 个专项函数，但缺 margin.unit 删除 mutation |

当前：**P1=0 / P2=0 / P3=1，共 1 NOT_CLOSED。**

未发现需要 `[REVERT:]` 或 `[DEGRADED:]` 的情况，也未重新登记此前已经 CLOSED 的其它问题。

---

# 6. 最终裁决

**HOLD（仅剩 P03-001 的 1 个 P3 回归覆盖余项）。**

P0 功能性门禁目前已无新的 P1/P2 阻断；剩余动作非常小：补齐 `margin.unit` 删除 mutation（或把现有 unit deletion test 扩展为 turnover+margin 两分支）并提供对应测试结果即可。

因此本轮**不能**写“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。
