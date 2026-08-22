# SMI R15 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R15（R14 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R15_source_20260821.zip`  
**送审声明 HEAD：** `ebac337`（基线 `0e2cfbf`）  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**  
> 本报告以 R15 ZIP 实际字节、包内完整 diff 与本轮独立最小复验为依据。对 ZIP 中未提供最终文件、只能从 diff 看到的修订，不按“最终归档字节已验证”处理。

---

# 1. 总体结论

## 1.1 结论

**HOLD，尚未收敛。**

R14 尚未闭环的 6 项，本轮裁定：

| 编号 | R15 裁定 | 摘要 |
|---|---|---|
| R14-P1-01 | **CLOSED** | spawn registry 方案已正确落地；强制 spawn + 真实 `@net_guard` 装饰器 4 条本端独立 PASS |
| R13-P2-01 | **NOT_CLOSED** | streak/WARMING_UP 已修，但 universe 完整性门禁仍有冷启动盲区与非因果回溯重分类问题 |
| R13-P3-04 | **CLOSED** | optional absent 允许；present 必须 exact-match；4 场景脚本本端独立 PASS |
| R14-P2-01 | **NOT_CLOSED** | v4 acceptance 矩阵仍未完全闭合，存在多个可实际 PASS 的非法状态组合 |
| R14-P3-01 | **CLOSED** | 前端类型与 WARMING_UP/DEGRADED 展示均已补齐 |
| R14-P3-02 | **CLOSED** | FINAL⇒CLOSE_COMPLETE⇒CAPTURED 存在性单调已实现，11 条 identity 测试本端 PASS |

**R14 六项：4 CLOSED / 2 NOT_CLOSED。**

R15 自查 3 项：

| 编号 | R15 裁定 | 摘要 |
|---|---|---|
| R15-N01 | **NOT_CLOSED（证据不完整）** | 修复逻辑与 diff 方向正确，但 ZIP 未包含 `reconcile_turnover_chain.py`、`test_core.py`、`2026-07-17.json` 三个最终修订字节，不能按最终包闭环 |
| R15-N02 | **CLOSED** | `all_scores_present` 已从当前 `tracks.py` 清除 |
| R15-N03 | **CLOSED** | template-standard notes 已更新到 v4 新枚举 |

## 1.2 本轮新增问题

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| R15-P2-01 | P2 | NOT_CLOSED | R15 ZIP 与送审清单不一致：N01 三个关键最终修订文件缺失，只能看到 diff，阻断最终字节复核 |
| R15-P3-01 | P3 | NOT_CLOSED | CI 只跑 `collector/tests`，未执行 `tools/acceptance/test_accept.py`，v4 acceptance 回归没有进入 CI 门禁 |

**新增：P1=0 / P2=1 / P3=1。**

当前唯一问题根因计数：  
- 既有仍未闭环：2 项；
- 新增：2 项；
- R15-N01 的 NOT_CLOSED 由 `R15-P2-01` 证据缺口导致，不重复计数。

因此本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

---

# 2. 本轮独立复验

## 2.1 直接基于 R15 ZIP 成功复验

### netguard spawn

执行：

```text
pytest -q collector/tests/test_netguard_spawn.py
```

结果：

```text
4 passed
```

覆盖：

1. 真实 `@net_guard` 装饰器语法 + 强制 spawn 成功返回；
2. 原异常类型回传；
3. 超时后确定性终止；
4. 局部/闭包函数装饰阶段 fail-closed。

### archive 同步脚本

执行：

```text
bash tools/deploy/test_verify_archive_sync.sh
```

结果：

```text
SELFTEST_ALL_PASS
```

4 场景均通过：

- optional absent → PASS
- optional present+match → PASS
- optional present+mismatch → FAIL
- required mismatch → FAIL

### identity

执行：

```text
pytest -q collector/tests/test_acceptance_identity.py
```

结果：

```text
11 passed
```

### v4 acceptance 已提供测试

执行：

```text
pytest -q tools/acceptance/test_accept.py -k tracks_v4
```

结果：

```text
10 passed
```

**注意：实际 R15 diff 只新增了 10 个 `test_tracks_v4_*` 测试函数，不是主送审正文声称的 13 条。**  
包内 `SMI_R15_Fix_Notes.md` 自己也写的是 10 条，因此“13 条”属于送审摘要数字不一致。

## 2.2 基于 R14 完整源码 + R15 当前修订文件覆盖的定点复验

由于 R15 是“最小包”，不包含 `collector/archive.py` 等完整依赖，本轮用上轮已在本对话中的 R14 完整源码作为只读基底，再覆盖 R15 已提供最终文件，仅用于跑指定的当前 tracks 回归。

以下 6 条均 PASS：

- `FAIL → PASS → FAIL` streak 清零；
- incomplete universe day 不作出池证据；
- WARMING_UP 不输出成熟 score；
- 全 WARMING_UP fail-closed；
- FINAL without CLOSE_COMPLETE 被拒绝；
- CLOSE_COMPLETE without CAPTURED 被拒绝。

这不等于“全量 278”独立复现，只证明上述指定路径。

## 2.3 未能独立复现 278+1 的原因

R15 ZIP 不是自包含全仓包，实际缺少若干测试依赖文件和历史样本；例如 acceptance 测试依赖：

- `2026-07-17.json`
- `2026-08-14.json`

而 R15 ZIP 均未提供。

因此：

> 送审方“278 passed + 1 skipped”的本机证据可以作为外部证据记录，但本报告不把它表述为本端独立复验结果。

---

# 3. R14-P1-01 — Windows spawn registry

**原严重度：P1**  
**R15 裁定：CLOSED**

## 3.1 实现核验

`collector/netguard.py` 已实现：

- `_SPAWN_REGISTRY`
- `_spawn_target_key(fn)`：
  - `module:qualname` 稳定 key；
  - `<locals>` / 非模块级函数装饰时直接 fail-closed；
- `_resolve_spawn_target(key)`：
  - 子进程 import 目标模块；
  - 从 registry 获取原始未包装函数；
  - fallback 时沿 `__wrapped__` 解包，避免递归 wrapper；
- spawn 参数中不再传原函数对象；
- `SMI_NETGUARD_FORCE_SPAWN=1` 用于 POSIX 强制覆盖 Windows 路径；
- `_run_once_hard_timeout()` success/error/timeout/unknown 均进入 `finally: process.close()`；
- timeout 仍为 terminate → kill 两级终止。

## 3.2 真实形态测试

当前测试不是上一轮“先定义函数再手工包装”的绕过形态，而是临时模块内：

```text
@net_guard(...)
def ng_quick(): ...
```

子进程重新 import 临时模块，能真实重建 registry。

本端强制 spawn 4/4 PASS。

### 裁定

**R14-P1-01 CLOSED。**

### 非阻断备注

`SMI_NETGUARD_MODE=inline` 是测试旁路；CI/生产 workflow 不应设置该变量。当前材料未见生产 workflow 设置，因此不登记问题。

---

# 4. R13-P2-01 — 迟滞选池 / WARMING_UP / universe 完整性

**原严重度：P2**  
**R15 裁定：NOT_CLOSED**

本轮三个 R14 阻断点里，A/B 已基本闭合，C 仍有边界漏洞。

---

## 4.1 A：连续失败 streak 清零 — CLOSED 子项

当前代码：

```text
exit_hit → old_streak + 1
healthy  → streak = 0
```

与“连续 2 日”语义一致。

回归：

```text
FAIL → PASS → FAIL
```

本端 PASS，最终仍保留池籍。

---

## 4.2 B：WARMING_UP 从标签升级为正式输出门禁 — CLOSED 子项

当前 `_make_track_item()`：

动态候选历史不足 `minHistoryDays` 时：

- `dataReadiness = WARMING_UP`
- `score = null`
- `coveragePct = null`
- `decision = 数据不足`
- `dimensionPass = null`

`collect_tracks()`：

- WARMING_UP 不进入模块 coverage 分母；
- WARMING_UP 不参与 `any_score`；
- 全部候选 WARMING_UP →  
  `UNAVAILABLE / TRACKS_INSUFFICIENT / TRACKS_ALL_WARMING_UP`。

这已经实现“输出与模块判定层面的正式评分隔离”。

### 非阻断实现备注

代码仍会先把所有 raw item 送进 `score_tracks()`，再在输出层抹掉 warming 评分。  
当前没有证据表明 scorer 有副作用，因此本轮不单独登记；但从结构纯度上，未来可在 scorer 前先拆分 formal/warming，以免预热输入异常影响 scorer。

---

## 4.3 C：universe 完整性门禁 — 仍 NOT_CLOSED

当前规则：

```text
complete_threshold =
    max(minUniverseBoards,
        全历史已知日期最大 board_count × minUniverseBoardRatio)

当前配置：
minUniverseBoards = 0
minUniverseBoardRatio = 0.5
```

### 问题 1：冷启动自校准盲区

如果系统开始积累 archive 时，上游第一天就只返回 1 个板块：

```text
peak = 1
threshold = 0.5
board_count = 1
=> 被判定为完整证据日
```

本轮用当前真实 `select_scoring_pool()` 构造只有 1 个板块的首日 universe：

```text
select_scoring_pool(...)
=> 银行直接进入正式池
```

即：

> **“相对自身峰值 50%”无法检测“从一开始就是部分响应”。**

`minUniverseBoards=0` 使绝对下限完全失效。

### 问题 2：使用“最终峰值”会回溯重分类历史证据

当前 `peak_count` 是对 `known_dates <= trade_date` 一次性取最大值，再用同一个 threshold 回放所有早期日期。

本轮最小复验：

```text
D1：2 个板块
D2：2 个板块
D3：6 个板块（后来源恢复完整）
```

结果：

```text
D2 计算时：银行、煤炭在池
D3 重新全历史回放时：D1/D2 因新峰值 6 而被重分类为“不完整”
D3：池直接变为空
```

实测：

```text
2026-08-19 => ['银行', '煤炭']
2026-08-20 => []
```

这不是正常的“连续出池”，而是后来的较完整响应**回溯撤销了过去曾经被认为有效的入池证据**。

### 根因

门禁缺少“可信绝对基准/因果基准”，只依赖当前回放窗口内的最大观测值。

### 影响

- 冷启动时仍可把明显部分响应当完整 universe；
- 数据源从部分恢复为完整时，正式池会产生与市场资格无关的跳变；
- 全历史重放不是严格因果状态机：同一历史日是否是证据，会随未来更高峰值改变。

### 建议

不要仅靠 `peak×ratio`。

建议改成：

1. **配置一个非零绝对最低板块数**，来源必须是已验证成功的完整 universe 快照，而不是拍脑袋常量；
2. threshold 的相对基线采用**可信历史/滚动基线**，而不是用当前 trade_date 的最终全局峰值回溯改写所有早期日；
3. 在没有任何可信 baseline 时：
   - universe 状态应为 `WARMING_UP/UNKNOWN`；
   - 不允许驱动入池/出池；
4. 增加两条负向回归：
   - 首日只返回极少板块 → 不得成为证据日；
   - `partial, partial, full` → full 日不得通过回溯阈值把已建立的历史状态无解释清空。

### 裁定

**R13-P2-01 仍 NOT_CLOSED。**

---

# 5. R13-P3-04 — archive optional membership

**原严重度：P2**  
**R15 裁定：CLOSED**

当前 `verify_archive_sync.sh` 已准确实现：

```text
required missing        => FAIL
required mismatch       => FAIL
optional local absent   => warning / PASS
optional local present:
  remote missing        => FAIL
  remote mismatch       => FAIL
  exact match           => PASS
```

本端 4 场景全部通过。

workflow 已改为直接调用该脚本：

```text
bash tools/deploy/verify_archive_sync.sh
```

因此脚本测试与生产自检使用同一实现，不再有“测试一个脚本、workflow 另写一套逻辑”的漂移。

### 裁定

**R13-P3-04 CLOSED。**

---

# 6. R14-P2-01 — tracks_V2 v4 acceptance 契约

**原严重度：P2**  
**R15 裁定：NOT_CLOSED**

方向明显改进，但“状态 ⇄ decision ⇄ readiness ⇄ coverage”的矩阵还没有真正闭合。

---

## 6.1 已正确实现的部分

标准已改为：

```text
allowedStatuses = FINAL / PARTIAL / UNAVAILABLE
```

并定义：

```text
TRACKS_SUFFICIENT
TRACKS_DEGRADED
TRACKS_INSUFFICIENT
```

已实现并测试：

- PARTIAL + SUFFICIENT + coverage>=target 正例；
- PARTIAL + DEGRADED + floor<=coverage<target 正例；
- SUFFICIENT 低 coverage 拒绝；
- DEGRADED 高 coverage 拒绝；
- UNAVAILABLE + 错误 TRACKS_SUFFICIENT 拒绝；
- readiness mismatch 拒绝；
- WARMING_UP 成熟 score 拒绝；
- minFormalItems；
- seed 定性必填。

方向正确。

---

## 6.2 阻断点 A：PARTIAL + TRACKS_INSUFFICIENT 可非法 PASS

当前代码对 PARTIAL：

- decision 只要求属于 `moduleDecisions`；
- 随后只分别检查 SUFFICIENT 与 DEGRADED；
- `TRACKS_INSUFFICIENT` 没有被显式拒绝。

本轮最小反例：

```text
status = PARTIAL
decision = TRACKS_INSUFFICIENT
dataReadiness = FAILED
coveragePct = 40
4 个合法 items
```

**当前 `check_tracks()` 返回 PASS。**

这直接违反标准的 `statusMatrix`：

```text
PARTIAL ⇄ SUFFICIENT | DEGRADED
UNAVAILABLE ⇄ INSUFFICIENT
```

---

## 6.3 阻断点 B：UNAVAILABLE 缺 decision / 使用旧 `INSUFFICIENT` 可 PASS

当前逻辑只有：

```text
如果 decision 是字符串、以 TRACKS_ 开头，
且不是 TRACKS_INSUFFICIENT，则 FAIL
```

因此：

```text
UNAVAILABLE + decision=null
```

以及：

```text
UNAVAILABLE + decision="INSUFFICIENT"
```

均可 PASS。

本轮两者均已实际复验 PASS。

标准既然已经声明：

```text
UNAVAILABLE ⇄ TRACKS_INSUFFICIENT
```

就必须强制 decision 存在且精确等于该值。

---

## 6.4 阻断点 C：FINAL 没有验证 coverage>=target

标准写明：

```text
FINAL ⇄ TRACKS_SUFFICIENT 且 coveragePct>=target
```

当前代码只检查：

```text
FINAL 的 decision 必须 TRACKS_SUFFICIENT
```

但没有检查 FINAL coverage。

为隔离 `_recalc_tracks()` 这一独立机制，本轮将重算器替换为空操作后验证矩阵本身：

```text
FINAL + TRACKS_SUFFICIENT + coverage=null  => PASS
FINAL + TRACKS_SUFFICIENT + coverage=10    => PASS
FINAL + TRACKS_SUFFICIENT + coverage=79.9  => PASS
```

即矩阵实现不完整。

---

## 6.5 阻断点 D：readinessMap 不是强制字段

当前：

```text
readiness is not None
AND decision in readinessMap
=> 才比较
```

因此当前 v4 非 legacy 快照完全不带 `dataReadiness` 也可以通过。

同样：

- `coverageTargetPct`
- `coverageHardFloorPct`

在标准中仍是 optional，也没有要求与 decisionContract 的 target/floor 一致。

### 真实样本证据

R15 ZIP 中的 `2026-08-20.json` 仍是旧 tracks 3.0 形态：

```text
configVersion = 3.0
status = UNAVAILABLE
decision = TRACKS_INSUFFICIENT
coveragePct = 71.4
dataReadiness = null/缺失
coverageTargetPct = 缺失
coverageHardFloorPct = 缺失
warmingUpBoards = 缺失
item.dataReadiness/historyDays = 缺失
```

本轮直接调用当前 v4 `check_tracks()`：

```text
PASS
```

这说明“08-20 9 模块 PASS”至少不能用来证明新 v3.2 readiness 契约已经被严格验收；当前 checker 正在兼容性放行旧数据，但这种兼容没有被显式建模为版本分支。

---

## 6.6 阻断点 E：minFormalItems 把 INSUFFICIENT/FETCH_FAILED 也算“正式项”

当前：

```text
formal_items = 所有不是 WARMING_UP 的 item
```

因此：

- `INSUFFICIENT`
- `FETCH_FAILED`

也被计入 `minFormalItems`。

本轮构造 4 个：

```text
dataReadiness = INSUFFICIENT
score = null
decision = 数据不足
```

但模块宣称：

```text
PARTIAL / TRACKS_SUFFICIENT / READY / coverage=82.4
```

当前 checker 仍然 **PASS**。

这与“正式评分项”语义不一致。

建议 formal item 只计：

```text
READY
DEGRADED
```

或明确规定真正可作为 formal 的 readiness 集合。

---

## 6.7 WARMING_UP 契约还有未校验字段

生产当前明确输出：

```text
WARMING_UP:
score = null
coveragePct = null
dimensionPass = null
decision = 数据不足
```

acceptance 目前只检查：

- score 必须 null；
- decision 必须 数据不足。

没有检查：

- item.coveragePct == null
- item.dimensionPass == null

这属于同一 v4 契约未完全落地问题，不另立编号。

---

## 6.8 测试证据数字不一致

主送审正文称：

```text
v4 acceptance 新增 13 条
```

实际 R15 diff 中只新增 **10** 个 `test_tracks_v4_*`。

Fix Notes 又写“10 条”，与源码一致。

更重要的是，缺失的恰好包括当前可绕过的边界：

- PARTIAL + INSUFFICIENT；
- UNAVAILABLE missing decision；
- FINAL coverage<target；
- formal readiness 过滤等。

因此不是纯文案计数问题，而是覆盖矩阵确实有空白。

### 建议

把状态机写成**穷举式矩阵**，而不是若干 `if decision == ...` 的局部约束。

最小语义：

```text
FINAL:
  decision == TRACKS_SUFFICIENT
  readiness == READY
  finite coverage >= target

PARTIAL:
  (SUFFICIENT, READY, coverage>=target)
  OR
  (DEGRADED, DEGRADED, floor<=coverage<target)

UNAVAILABLE:
  decision == TRACKS_INSUFFICIENT
  readiness == FAILED
  coverage 可低于 floor，或 critical reason 明确
```

并且：

```text
configVersion>=3.2
=> dataReadiness/coverageTargetPct/coverageHardFloorPct/warmingUpBoards
   按当前契约显式要求
```

旧 3.0/3.1 数据若要兼容，应做明确的版本兼容分支，而不是靠字段 `required:false` 偶然放行。

### 裁定

**R14-P2-01 仍 NOT_CLOSED。**

---

# 7. R14-P3-01 — 前端新就绪态

**原严重度：P3**  
**R15 裁定：CLOSED**

## 类型层

`TrackItem` 已新增：

- `dataReadiness`
- `historyDays`

`TracksModule` 已新增：

- `TRACKS_DEGRADED`
- `TRACKS_INSUFFICIENT`
- `dataReadiness`
- `coverageTargetPct`
- `coverageHardFloorPct`
- `warmingUpBoards`

## 展示层

`TrackMonitorPanel.vue`：

WARMING_UP：

- score 列显示“预热” badge；
- title 显示 close 历史天数；
- 最终判定显示“预热中”，不把 `数据不足` 当成熟结论。

DEGRADED：

- 显示 coverage/floor/target 区间；
- 明确说明“评分保留但降置信、不点亮 D0”。

warmingUpBoards：

- 有汇总提示。

### 裁定

**R14-P3-01 CLOSED。**

---

# 8. R14-P3-02 — manifest null 指针链

**原严重度：P3**  
**R15 裁定：CLOSED**

当前 identity checker 已明确增加：

```text
latestFinalDate != null
=> latestCloseCompleteDate != null

latestCloseCompleteDate != null
=> latestCapturedDate != null
```

对应负向测试均存在。

本端：

```text
11 passed
```

### 裁定

**R14-P3-02 CLOSED。**

---

# 9. R15-N01 — Legacy 范本日 reconcile 覆写修复

**自查严重度：P2**  
**R15 裁定：NOT_CLOSED（最终包证据不足）**

这里必须把“修复方案是否正确”与“最终送审包是否证明已落地”分开。

---

## 9.1 补丁逻辑评估：方向正确

R15 diff 对 `_reconcile_day()` 增加：

```text
如果当前 turnover method != canonical TURNOVER_METHOD
=> 直接 return False
```

结合既有 `_infer_turnover_method()`：

- `LEGACY_UNKNOWN` 明确不是 canonical；
- 因而 07-17 Legacy Excel 范本日不会再被链式 reconcile 重算。

这与既有 docstring：

> 只有当前/前日口径都可证明为 canonical 才做跨日链派生

是一致的。

这比只按日期硬编码 `2026-07-17` 更好，属于**方法口径门禁**，不是日期特判。

---

## 9.2 revision 8 数据修复方案：从 diff 看可接受

diff 显示仅修改：

### 身份元数据

```text
revision 7 -> 8
generationReason:
TURNOVER_CHAIN_RECONCILE
-> LEGACY_REFERENCE_DAY_RESTORE
updatedAt 更新
```

这是内容修复后合理的 revision bump。

### turnover 6 字段恢复

```text
turnoverPrevious  = 24035.65
turnoverDelta     = 2513.93
turnoverChangePct = 10.46
volumeState       = EXPANSION
previousMethod    = LEGACY_UNKNOWN
comparisonStatus  = COMPARABLE
```

独立算术复核：

```text
26549.58 - 24035.65 = 2513.93
2513.93 / 24035.65 ×100 = 10.46%
```

与 `template-standard.json` 的 07-17 referenceAssertions 完全一致。

### summary

diff 仅恢复：

- trackConclusion
- marketEnvironment
- northbound
- riskWarning

未见其他模块大范围重写。

从 diff 形态上属于外科式恢复。

---

## 9.3 为什么仍不能 CLOSED：R15 ZIP 缺失最终字节

送审说明明确声称本轮包包含：

```text
collector/jobs/reconcile_turnover_chain.py
collector/tests/test_core.py
web/public/data/daily/2026/2026-07-17.json
```

实际 ZIP 文件列表中**这三个文件均不存在**。

当前只能从：

```text
review/r15_diff_0e2cfbf.patch
```

看到它们的变更 hunk。

diff 不能证明：

- HEAD `ebac337` 中最终文件字节与 hunk 完全一致；
- 文件没有其它未展示/后续变更；
- revision 8 的最终 JSON 实际存在于送审归档；
- 新 `test_reconcile_legacy_day_exempt_from_overwrite` 实际存在于最终测试文件。

此外，07-17 summary 的“Excel 原文”并没有原始 Excel 附件可供本轮再核；当前标准只对 turnover 数字做精确 referenceAssertions，对 summary 主要是语义约束。

### 裁定

**方案/补丁逻辑：ACCEPTABLE。**  
**最终包闭环：NOT_CLOSED。**

该证据交付问题统一登记为 `R15-P2-01`，不再重复另立 N01 代码问题。

---

# 10. R15-N02 — 死变量清理

**自查严重度：P3**  
**R15 裁定：CLOSED**

当前 `collector/modules/tracks.py` 搜索不到：

```text
all_scores_present
```

且无相关消费路径。

**CLOSED。**

---

# 11. R15-N03 — template-standard notes

**自查严重度：P3**  
**R15 裁定：CLOSED**

当前 notes 已改为：

```text
核心主赛道
次主线/轮动主线
短线支线
一日游脉冲/回避
数据不足
```

不再沿用旧：

```text
核心防御主线 / 主跌浪 ...
```

**CLOSED。**

---

# 12. R15-P2-01 — 送审包缺失 N01 三个最终修订文件

**严重度：P2**  
**状态：NOT_CLOSED**

## 定位

R15 ZIP 文件清单 vs `work/SMI_R15_Review_Request.md §1`。

## 缺失文件

送审清单声称应包含，但 ZIP 实际不存在：

1. `smi/collector/jobs/reconcile_turnover_chain.py`
2. `smi/collector/tests/test_core.py`
3. `smi/web/public/data/daily/2026/2026-07-17.json`

这些恰好是 R15-N01 的三项核心最终产物：

- 修复代码；
- 回归测试；
- 修复后数据。

## 影响

- 无法从最终归档字节验证 N01；
- 无法证明 `ebac337` 的最终状态；
- R14/迭代纪律要求“最终材料”闭环时，diff 不能替代最终文件；
- 当前包无法独立复跑所有声称依赖 07-17 的 acceptance 测试。

## 建议

下一轮无需再发全包，只补最小 3 文件即可：

```text
collector/jobs/reconcile_turnover_chain.py
collector/tests/test_core.py
web/public/data/daily/2026/2026-07-17.json
```

并给三者 SHA-256 或由下一包直接携带。

---

# 13. R15-P3-01 — v4 acceptance 回归未进入 CI

**严重度：P3**  
**状态：NOT_CLOSED**

## 定位

`.github/workflows/ci.yml`

当前 Python CI：

```text
pytest -q collector/tests
```

但 v4 acceptance 测试位于：

```text
tools/acceptance/test_accept.py
```

因此当前 CI 不会执行本轮新增的 10 条 v4 acceptance 测试。

archive shell 自测已经单独加入 CI，这是正确的；但 acceptance v4 没有同样进入门禁。

## 影响

即使后续本地修好 v4 矩阵，未来某次 PR 把它回归掉，CI 仍可能绿色。

## 建议

CI Python test step 至少改为等价：

```text
pytest -q collector/tests tools/acceptance/test_accept.py
```

或增加独立 `Acceptance tests` step。

---

# 14. R14 §19 六类负向回归裁定

| R14 要求 | 本轮结论 |
|---|---|
| FAIL→PASS→FAIL 不得出池 | **到位，PASS** |
| forced spawn + 真实 decorator syntax | **到位，真实形态，4/4 PASS** |
| optional membership absent/match/mismatch | **到位，4 场景 PASS** |
| final!=null + closeComplete=null 必须 FAIL | **到位，PASS** |
| PARTIAL/SUFFICIENT 与 PARTIAL/DEGRADED 正例 | **到位，PASS** |
| frontend typecheck 覆盖 TRACKS_DEGRADED/WARMING_UP | **源码消费已到位；送审方声明 vue-tsc PASS，本最小包不含完整安装环境，本端未独立重跑** |

但 v4 的**负向空间仍不完整**，详见 `R14-P2-01`。

---

# 15. v4 契约与生产模型最终专项结论

## 已一致

- PARTIAL/SUFFICIENT/DEGRADED 三态方向；
- WARMING_UP 输出 null score；
- 前端展示；
- allowedStatuses；
- 新四级中文 item decision；
- excessReturn20d nullable；
- minFormalItems 设计目标；
- seed 定性列约束方向。

## 仍失配

1. PARTIAL 可携带 INSUFFICIENT；
2. UNAVAILABLE 可无 decision；
3. UNAVAILABLE 可使用旧 `"INSUFFICIENT"`；
4. FINAL coverage 未门禁；
5. module dataReadiness 可缺失；
6. target/floor 可缺失且未与 contract 对齐；
7. INSUFFICIENT/FETCH_FAILED 被当作 formal item；
8. WARMING_UP 的 item.coveragePct/dimensionPass 未校验 null；
9. 旧 3.0 08-20 数据通过 v4，不是显式版本兼容，而是 optionality 放行。

因此 **R14-P2-01 不能 CLOSED。**

---

# 16. universe 完整性门禁专项结论

`peak × 0.5` 不是完整性证明，只是相对异常检测。

### 当前适用场景

如果历史里已经存在可信完整日：

```text
今天突然只剩过去峰值的 20%
```

能够识别为部分响应。

### 当前不适用场景

- archive 第一日就是部分响应；
- 连续几天都以相近比例部分响应；
- 上游恢复后峰值突然抬高；
- 上游合法 universe 规模发生结构性变化。

特别是“后来的峰值重定义过去完整性”会使全历史递推发生非因果跳变。

### 裁定

**需要继续修，故 R13-P2-01 NOT_CLOSED。**

---

# 17. 已知边界 4 项裁定

| 边界 | 是否登记新问题 | 裁定 |
|---|---|---|
| coverage floor=65 临时标定 | 否 | 已明确参数债务；满 20~30 日回放后再标定即可 |
| sentiment/fundFlow 历史源缺口 | 否 | historical-profile 已披露，属数据源能力边界 |
| margin/turnover/northbound/summary 存量上游失败 | 否 | 本轮未发现证据证明是新代码回归 |
| manifest closeComplete/final 仍停 07-17 | 否 | 与“之后没有全模块完整成功日”的 D0/FINAL 语义一致 |

---

# 18. 下一轮最小复送建议

为了快速收敛，无需再提交全仓。

建议只补：

## A. R13-P2-01

- `collector/modules/tracks.py`
- `config/tracks.yaml`
- 新增两条 universe gate 回归：
  - cold-start tiny universe 不得作为证据；
  - partial→partial→full 不得产生无解释的回溯池清空。

## B. R14-P2-01

- `docs/acceptance/template-standard.json`
- `tools/acceptance/accept.py`
- `tools/acceptance/test_accept.py`

至少补负向：

```text
PARTIAL + INSUFFICIENT => FAIL
UNAVAILABLE + decision missing => FAIL
UNAVAILABLE + legacy INSUFFICIENT => FAIL
FINAL + coverage<target => FAIL
FINAL + coverage missing => FAIL
formal item readiness=INSUFFICIENT/FETCH_FAILED 不计 minFormalItems
WARMING_UP coveragePct/dimensionPass 非 null => FAIL
```

## C. R15-N01 / R15-P2-01

只补三个最终文件：

```text
collector/jobs/reconcile_turnover_chain.py
collector/tests/test_core.py
web/public/data/daily/2026/2026-07-17.json
```

## D. R15-P3-01

- `.github/workflows/ci.yml`

让 CI 实际执行 acceptance tests。

---

# 19. 最终裁定汇总

## R14 六项

```text
R14-P1-01  CLOSED
R13-P2-01  NOT_CLOSED
R13-P3-04  CLOSED
R14-P2-01  NOT_CLOSED
R14-P3-01  CLOSED
R14-P3-02  CLOSED
```

## R15 自查三项

```text
R15-N01  NOT_CLOSED（修复逻辑可接受，但最终文件未随 ZIP 交付）
R15-N02  CLOSED
R15-N03  CLOSED
```

## 新增

```text
R15-P2-01  NOT_CLOSED — N01 最终修订文件缺失
R15-P3-01  NOT_CLOSED — acceptance v4 tests 未进入 CI
```

**新增问题：P1=0 / P2=1 / P3=1。**

**R15 最终结论：HOLD。**

**本轮不能声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

再次声明：**未修改调用方本地工作区。**
