# SMI R16 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R16（R15 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R16_source_20260822.zip`  
**送审声明 HEAD：** `a3a706c`  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**

---

# 1. 总体结论

## 1.1 结论

**HOLD。**

R15 尚未闭环的 4 项，本轮逐项裁定：

| 编号 | R16 裁定 | 结论 |
|---|---|---|
| R13-P2-01 | **CLOSED** | universe 门禁已完成绝对下限 + 严格前向可信峰值因果化；R15 两个反例均已被回归固化 |
| R14-P2-01 | **CLOSED** | R15 §15 列出的 9 类契约失配均已逐项闭合；21 条 v4 专项测试本端 PASS |
| R15-P2-01 + R15-N01 | **CLOSED** | 三个最终文件已真实随 ZIP 交付；Legacy 当日豁免代码、回归测试、07-17 revision 8 数据均可直接复核 |
| R15-P3-01 | **CLOSED** | `ci.yml` 已新增 `pytest -q tools/acceptance/test_accept.py` 独立门禁 |

R15-N01 本身：**CLOSED**。

## 1.2 本轮新增问题

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| **R16-P2-01** | P2 | **NOT_CLOSED** | v4 兼容分支只信任快照自报 `configVersion`，没有把 3.0/3.1 限定在既有历史日期；未来新快照错误自报 3.0 时可绕过 3.2 严格字段并 PASS |

**新增：P1=0 / P2=1 / P3=0。**

因此本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

---

# 2. 独立复验摘要

## 2.1 R16 ZIP 实际包含 N01 三个最终文件

已确认存在：

1. `collector/jobs/reconcile_turnover_chain.py`
2. `collector/tests/test_core.py`
3. `web/public/data/daily/2026/2026-07-17.json`

并非只存在于 diff。

07-17 最终数据：

```text
revision = 8
generationReason = LEGACY_REFERENCE_DAY_RESTORE
```

turnover 关键值：

```text
turnoverToday      = 26549.58
turnoverPrevious   = 24035.65
turnoverDelta      = 2513.93
turnoverChangePct  = 10.46
volumeState        = EXPANSION
previousMethod     = LEGACY_UNKNOWN
comparisonStatus   = COMPARABLE
method             = LEGACY_UNKNOWN
```

独立算术核对：

```text
26549.58 - 24035.65 = 2513.93
2513.93 / 24035.65 × 100 = 10.46%
```

与 `referenceAssertions` 一致。

---

## 2.2 重点测试独立复验

在 R14 完整源码基底上覆盖 R16 最小复送文件，执行定点回归：

### tracks 因果/迟滞相关

```text
12 passed
```

包含：

- cold-start tiny universe；
- causal no-retro-clear；
- FAIL→PASS→FAIL；
- WARMING_UP；
- 全预热 fail-closed；
- 双阈值等相关路径。

### v4 acceptance

```text
21 passed
```

与 R16 说明一致：10 条既有 + 11 条新增。

### N01 Legacy reconcile

```text
1 passed
```

`test_reconcile_legacy_day_exempt_from_overwrite` 实际 PASS。

### identity

R16 当前 identity 套件：

```text
11 passed
```

### 07-17 acceptance

本端执行：

```text
PASS 2026-07-17
9 模块全部 PASS
```

---

## 2.3 全量 291+1 未在本端独立复现

本端环境缺少 `akshare`，全量 pytest 在收集：

- `test_sectors_history.py`
- `test_sentiment_history.py`

时因 `ModuleNotFoundError: akshare` 中止。

因此本报告：

- **记录**送审方 `291 passed + 1 skipped`；
- 但不把它写成“本端独立全量复验”。

这属于审查环境依赖差异，不登记项目问题。

---

# 3. R13-P2-01 — universe 因果门禁

**原严重度：P2**  
**R16 裁定：CLOSED**

## 3.1 冷启动盲区已修

配置：

```text
minUniverseBoards = 45
minUniverseBoardRatio = 0.5
```

R16 包内 `industry-universe-snapshot.jsonl` 的 2026-08-20 记录实际有：

```text
90 个行业板块
```

因此 45 的来源与注释声明一致：

> 已验证完整快照 90 的 50%。

首日若只有 1/2 个板块，不再能通过“相对自身峰值”自证完整。

对应真实配置回归：

```text
首日 2 板块
→ select_scoring_pool == []
```

通过。

---

## 3.2 前向峰值已因果化

当前算法按日期升序：

```text
threshold = max(min_abs, trusted_peak * ratio)

仅当：
board_count >= threshold
才把当日记为 complete_date

只有 complete_date：
trusted_peak = max(trusted_peak, board_count)
```

因此：

- 当前日资格只依赖严格早于当前日的可信状态；
- 未通过门禁的部分响应不会污染 trusted_peak；
- 未来更大 universe 不会回溯重判过去完整日。

R15 反例：

```text
D1=2
D2=2
D3=6
```

在玩具门禁 `min=2` 下，D1/D2 已建立的池籍不会因 D3 峰值出现而被回溯清空。

对应回归 PASS。

---

## 3.3 “缺行=exit hit”前置条件已闭合

代码只有：

```text
if d not in complete_dates:
    continue
```

之后才执行：

- 存量成员 exit streak；
- 新成员 entry hit。

因此不完整 universe 日：

- 不累计出池；
- 不累计入池；
- 不把“缺行”错误解释为市场出池事实。

---

## 3.4 参数层剩余风险

`minUniverseBoards=45` 仍是经验门限，但本轮已给出真实 90 板块快照依据，且属于保守 fail-closed 门禁。

若未来 THS 合法行业数量结构性下降到 <45，该门禁会停止驱动动态池，而不是错误地产生池籍变化。该行为属于安全退化，不构成本轮阻断问题。

### 裁定

**R13-P2-01 CLOSED。**

---

# 4. R14-P2-01 — v4 acceptance 状态机

**原严重度：P2**  
**R16 裁定：CLOSED（原问题）**

R15 报告 §15 列出的 9 类失配，本轮逐项核对如下。

---

## 4.1 PARTIAL + TRACKS_INSUFFICIENT

当前显式拒绝。

**CLOSED。**

---

## 4.2 UNAVAILABLE 缺 decision

所有状态都要求 decision 存在。

**CLOSED。**

---

## 4.3 UNAVAILABLE 使用旧 `INSUFFICIENT`

不在 `moduleDecisions`：

```text
TRACKS_SUFFICIENT
TRACKS_DEGRADED
TRACKS_INSUFFICIENT
```

因此拒绝。

**CLOSED。**

---

## 4.4 FINAL coverage 缺失或低于 target

FINAL 明确要求：

```text
decision == TRACKS_SUFFICIENT
coverage 为有限数
coverage >= target
```

对应两条负向测试均存在并 PASS。

**CLOSED。**

---

## 4.5 strict 3.2 缺 dataReadiness

`configVersion>=3.2`：

```text
dataReadiness 必填
且必须 == readinessMap[decision]
```

**CLOSED。**

---

## 4.6 strict 3.2 缺 target/floor

以下字段均强制有限且必须等于 decisionContract：

- `coverageTargetPct`
- `coverageHardFloorPct`

**CLOSED。**

---

## 4.7 formal item 过滤

strict 分支 formal 只计：

```text
READY
DEGRADED
```

以下不能再充数：

```text
INSUFFICIENT
FETCH_FAILED
WARMING_UP
```

**CLOSED。**

---

## 4.8 WARMING_UP 四字段

已强制：

```text
score = null
coveragePct = null
dimensionPass = null
decision = 数据不足
```

**CLOSED。**

---

## 4.9 3.0 存量不是“偶然 optionality”

已存在显式：

```text
strict_v42 = configVersion >= 3.2
```

非 strict 仍执行状态⇄decision 矩阵，但不强迫 3.2 新字段。

因此“历史旧快照通过”已经从偶然 optional 放行变成显式版本兼容逻辑。

R15 §15 的原失配清单可判闭环。

### 裁定

**R14-P2-01 CLOSED。**

但该新版本兼容逻辑存在新的独立边界，登记 `R16-P2-01`。

---

# 5. R16-P2-01 — 旧版本兼容没有权威时间边界

**严重度：P2**  
**状态：NOT_CLOSED**

## 5.1 定位

`tools/acceptance/accept.py`

当前 strict 判定只依据快照自身：

```text
configVersion >= 3.2
```

不存在外部权威规则：

```text
某日期以后必须 >=3.2
```

或：

```text
3.0 只允许既有历史快照日期
```

---

## 5.2 为什么 08-20 的 3.0 PASS 本身是正确的

R16 附带的真实 2026-08-20 tracks：

```text
status = UNAVAILABLE
configVersion = 3.0
decision = TRACKS_INSUFFICIENT
coveragePct = 71.4
dataReadiness 缺失
target/floor 透传字段缺失
```

直接用当前 v4 checker 单独验证 tracks：

```text
PASS
```

这是**合理的历史兼容行为**。

8 月 20 日快照是在 3.2 新契约之前生成，不能因为今天标准升级就强迫重写历史快照字段。

因此：

> **08-20 经 3.0 显式版本分支合法 PASS，设计方向正确。**

---

## 5.3 真正的问题：未来新数据也能伪装成 3.0

当前 checker 没有把“旧版本”绑定到历史时间。

本轮独立构造：

```text
tradeDate = 2026-08-24
status = UNAVAILABLE
configVersion = 3.0
effectiveFrom = 2026-08-20
effectiveTo = 2026-12-31
sourceSystem = THS_UNIVERSE
decision = TRACKS_INSUFFICIENT
coveragePct = 71.4
items = []

完全不携带：
dataReadiness
coverageTargetPct
coverageHardFloorPct
warmingUpBoards
```

当前 `check_tracks()` 返回：

```text
PASS
```

也就是说：

> 如果未来生产 collector 发生回归，错误输出 3.0，验收器会把它当“历史兼容快照”，自动绕过 3.2 strict 契约。

这不是攻击场景才会发生；普通版本回退、错误常量、旧 worker 发布都可能触发。

---

## 5.4 根因

把：

```text
snapshot.configVersion
```

同时当作：

1. 被验收事实；
2. 决定验收强度的可信依据。

这形成自证循环。

验收器需要一个**快照外部的权威版本生效表**。

---

## 5.5 影响

未来交易日可能出现：

```text
configVersion 错回退到 3.0
```

同时遗漏：

- dataReadiness；
- target/floor；
- warmingUpBoards；
- formal readiness 语义；

但 acceptance 仍可能 PASS。

这会削弱本轮刚建立的 v4.2 契约。

---

## 5.6 建议

不要取消 08-20 的历史兼容。

建议增加权威版本时间表，例如放在 acceptance standard：

```text
tracksVersionSchedule:
  - through: 2026-08-20
    allowedConfigVersions: ["3.0"]
  - from: 2026-08-21
    allowedConfigVersions: ["3.1", "3.2"]
  - from: <3.2正式生产生效交易日>
    allowedConfigVersions: ["3.2"]
```

更稳妥的是：

- 使用实际“3.2 首个生产交易日”作为 cutoff；
- 对 cutoff 之后的快照：
  - configVersion <3.2 → FAIL；
- cutoff 之前：
  - 明确列出允许版本；
- 不允许任意旧版本长期依赖自身 `effectiveTo` 穿透到未来。

### 建议新增负向测试

至少：

```text
未来交易日 + configVersion=3.0
=> FAIL

真实 2026-08-20 + configVersion=3.0
=> PASS
```

这样既保留历史兼容，又关闭版本降级旁路。

---

# 6. R15-P2-01 + R15-N01 — Legacy 范本日恢复

**R16 裁定：CLOSED**

## 6.1 最终源码已交付

`reconcile_turnover_chain.py` 中 `_reconcile_day()`：

```text
如果当前 turnover method != canonical TURNOVER_METHOD
→ return False
```

因此 Legacy Excel：

```text
method = LEGACY_UNKNOWN
```

不会进入归档链跨日重算。

这个门禁不是硬编码 07-17 日期，而是按口径方法判断，符合原 docstring：

> 只有当前/前日 method 都可证明为 canonical，才重算跨日派生链。

---

## 6.2 回归测试最终字节已交付

`test_core.py` 已包含：

```text
test_reconcile_legacy_day_exempt_from_overwrite
```

本端定点运行：

```text
1 passed
```

验证：

- changed=False；
- COMPARABLE 保留；
- turnoverPrevious 保留；
- EXPANSION 保留；
- summary 不被规则引擎覆写。

---

## 6.3 07-17 revision 8 数据可接受

最终文件：

```text
tradeDate = 2026-07-17
revision = 8
generationReason = LEGACY_REFERENCE_DAY_RESTORE
overallStatus = FINAL
```

恢复值与 referenceAssertions 完全匹配。

本端 acceptance：

```text
2026-07-17
9 模块全 PASS
```

### 裁定

- `R15-P2-01`：**CLOSED**
- `R15-N01`：**CLOSED**

revision 8 是一次真实内容恢复后的 revision bump，身份语义可接受。

---

# 7. R15-P3-01 — acceptance tests 进入 CI

**原严重度：P3**  
**R16 裁定：CLOSED**

当前 `.github/workflows/ci.yml`：

```text
Run Python tests
  pytest -q collector/tests

Acceptance contract tests (R15-P3-01)
  pytest -q tools/acceptance/test_accept.py

Archive site-check selftest
  bash tools/deploy/test_verify_archive_sync.sh
```

因此 acceptance 已成为独立 CI 门禁，不再依赖人工本地运行。

Node 仍为 22，web typecheck/build 原链保持。

### 裁定

**R15-P3-01 CLOSED。**

---

# 8. R16 v4 测试计数核验

R16 当前 `test_accept.py` 中实际存在：

```text
21 个 test_tracks_v4_* 测试
```

与本轮更正说明一致：

```text
R15 既有 10
R16 新增 11
合计 21
```

本端：

```text
21 passed
```

因此 R15 “13 条”笔误已澄清，不再登记问题。

---

# 9. 08-20 生产日 3.0 版本分支裁定

## 结论

**对 2026-08-20 这一既有存量快照，3.0 显式兼容 PASS 是正确的。**

原因：

1. 它是 3.2 strict 契约形成前的真实生产字节；
2. 不应要求历史文件事后伪造当时不存在的：
   - dataReadiness
   - target/floor
   - warmingUpBoards
3. 当前 checker 仍强制：
   - status 属 allowedStatuses；
   - decision 属新模块枚举；
   - UNAVAILABLE 与 TRACKS_INSUFFICIENT 配对。

因此历史兼容不是“完全跳过验收”。

但必须补上 `R16-P2-01` 的**时间边界**，防未来日期继续冒用 3.0。

---

# 10. 关于送审方“08-20 9 模块全 PASS”证据

R16 是最小复送包，只带：

- 07-17
- 08-20

而 08-20 的 margin=PENDING 会回读其：

```text
latestPublishedReference = 2026-08-14
```

当前最小包没有附 08-14 daily。

因此本端直接跑完整：

```text
acceptance --date 2026-08-20
```

会因缺 08-14 reference 文件导致 margin FAIL。

但：

- 08-20 tracks 本身用当前 v4 checker **独立 PASS**；
- 07-17 全模块 **独立 PASS**；
- 该差异来自最小复送包没有携带完整历史 reference 链，而不是本轮代码故障。

鉴于本轮送审明确为“R15 §18 A~D 最小复送”，本报告只作为证据复现边界记录，**不登记新问题**。

---

# 11. 已知边界裁定

沿用 R15 结论，均无需新编号：

| 边界 | 裁定 |
|---|---|
| coverage floor=65 临时标定 | 参数校准债务，非当前逻辑缺陷 |
| sentiment/fundFlow 历史源缺口 | historical-profile 已披露 |
| margin/turnover/northbound/summary 存量采集失败 | 存量数据状态，无新回归证据 |
| manifest closeComplete/final 停在 07-17 | 与 D0/FINAL 定义一致 |

---

# 12. 下一轮最小修复建议

只需修 `R16-P2-01`，不必再重新提交其他已闭环文件。

建议最小复送：

1. `docs/acceptance/template-standard.json`
2. `tools/acceptance/accept.py`
3. `tools/acceptance/test_accept.py`

新增：

```text
权威 tracks configVersion 生效日期表
```

以及至少两条测试：

```text
2026-08-20 + 3.0 => PASS
3.2 生效后的新交易日 + 3.0 => FAIL
```

若届时无其它新问题，即可进入 0 NOT_CLOSED 收敛判定。

---

# 13. 最终裁定汇总

## R15 四项

```text
R13-P2-01             CLOSED
R14-P2-01             CLOSED
R15-P2-01 + R15-N01  CLOSED
R15-P3-01             CLOSED
```

## R15-N01

```text
R15-N01 CLOSED
```

## R16 新增

```text
R16-P2-01 NOT_CLOSED
```

**新增问题：P1=0 / P2=1 / P3=0。**

**R16 最终结论：HOLD。**

本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

再次声明：**未修改调用方本地工作区。**
