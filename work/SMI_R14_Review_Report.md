# SMI R14 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R14（R13 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R14_source_20260821.zip`  
**送审声明 HEAD：** `ef95499`  
**复核日期：** 2026-08-21  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**  
> 本报告只对送审归档字节及独立可复验行为作裁定。ZIP 不含 `.git`，因此 `ef95499` 的 commit 身份只能按送审声明记录，不能仅凭归档字节独立证明。

---

# 1. 总体结论

## 1.1 结论

**HOLD，尚未收敛。**

R13 的 7 项 NOT_CLOSED 本轮裁定：

| 编号 | R14 裁定 | 结论摘要 |
|---|---|---|
| R13-P3-01 | **CLOSED** | GitHub/POSIX 生产路径已从不可终止线程改为可 terminate→kill 的隔离子进程；原始 60 分钟挂死风险主线已闭环。Windows spawn 另有新变体，登记 `R14-P1-01`。 |
| R13-P2-01 | **NOT_CLOSED** | 已加入入池确认/双阈值/预热/WARMING_UP，但“连续 2 日出池”实现错误：健康日不清零 streak；另 `minHistoryDays` 当前只是标签，不是真正的正式评分池就绪门禁。 |
| R13-P2-02 | **CLOSED** | target=80 / floor=65 / DEGRADED 三态已实现；DEGRADED 不点亮 D0；validator 按同一配置阈值校验。 |
| R13-P3-02 | **CLOSED** | 原要求的 availableDates/latest/daily/文件名身份闭合已实现并有负向测试；另发现 null 指针链边界，登记 `R14-P3-02`。 |
| R13-P3-03 | **CLOSED** | close-snapshot 已用本地 dist 与线上 latest.json 的 tradeDate + SHA-256 双全等替代 updatedAt 新鲜度。 |
| R13-P3-04 | **NOT_CLOSED** | 4 required + 1 optional 的策略本身可接受，但 optional membership **存在且线上不一致时仍只 warning**，与源码注释“存在则必须一致”矛盾。 |
| R13-P3-05 | **CLOSED** | 请求序列令牌已正确实现，仅最后一次 load 可提交 snapshot/error/loading。 |

**R13 原问题：5 CLOSED / 2 NOT_CLOSED。**

## 1.2 本轮新增问题

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| R14-P1-01 | P1 | NOT_CLOSED | Windows spawn 兜底对真实 `@net_guard` 装饰函数不可 pickle，专项测试形态绕过了真实生产装饰方式 |
| R14-P2-01 | P2 | NOT_CLOSED | `tracks_V2` acceptance 标准与当前四级判定/PARTIAL 三态模型永久不兼容，当前验收器对新 tracks 必然产生预期 FAIL |
| R14-P3-01 | P3 | NOT_CLOSED | 前端类型和 TrackMonitorPanel 未建模/展示 `WARMING_UP`、`DEGRADED`、`TRACKS_DEGRADED` 新契约 |
| R14-P3-02 | P3 | NOT_CLOSED | acceptance 三指针“有序”检查会过滤 None，允许 `latestFinalDate!=null` 且 `latestCloseCompleteDate=null` 的非法状态通过 |

**新增：P1=1 / P2=1 / P3=2。**

当前未闭环总计：**6 项**（R13 遗留 2 + R14 新增 4）。

因此本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

---

# 2. 独立复验情况

本轮对送审包执行了只读抽取与静态/最小行为复验。

## 2.1 独立通过项

- `python -m compileall -q collector tools`：**PASS**
- 定点运行：
  - `test_tracks_dynamic.py`
  - `test_tracks_collector.py`
  - `test_acceptance_identity.py`
- 结果：**51 passed**
- netguard POSIX 真实子进程测试均通过；pytest 输出 9 条 `fork()` 多线程 DeprecationWarning，属于 Python 3.13 审查环境告警，不据此登记项目缺陷。

## 2.2 全量 pytest 未能独立复现送审方的 227+1

审查环境缺少 `akshare`，全量 pytest 在收集：

- `test_sectors_history.py`
- `test_sentiment_history.py`

时出现 `ModuleNotFoundError: akshare`。

这属于**审查环境依赖不足**，不是本轮源码缺陷。本报告不否认送审方提供的“227 passed + 1 skipped”证据，但也不把该数字冒充为本端独立复验结果。

## 2.3 额外负向复验

本轮额外构造了 3 个未被现有测试覆盖的最小反例：

1. **迟滞失败→恢复→失败**：当前代码错误出池；
2. **真实生产 `@net_guard` 装饰函数 pickle**：原函数 pickle 失败；
3. **manifest final 非空、closeComplete 为空**：identity checker 错误返回无 gap。

以上均在后文对应问题中展开。

---

# 3. R13-P3-01 — netguard 硬超时

**原严重度：P1**  
**R14 裁定：CLOSED（原问题）**

## 3.1 已闭环证据

`collector/netguard.py` 已不再使用 `ThreadPoolExecutor.future.result(timeout)` 作为所谓 hard timeout，而是：

- `_run_once_hard_timeout()` 创建隔离 `multiprocessing.Process`；
- timeout 后 `_terminate_process()`：
  - `terminate()`
  - join 2 秒
  - 仍存活则 `kill()`
  - 再 join；
- POSIX `_pick_context()` 优先 `fork`；
- 超时后抛 `GuardTimeoutError`；
- 子进程结果通过 pickle 临时文件原子回传。

这正面闭环了 R13 原 P1 的核心问题：

> “父调用返回了，但底层线程仍然不可终止并可能拖住解释器退出”。

本轮定点 netguard 测试也在 POSIX 路径实际走子进程并通过。

因此 **R13-P3-01 原始安全主线可判 CLOSED**。

但 Windows spawn 新增路径存在独立实现缺口，见 `R14-P1-01`。

---

# 4. R14-P1-01 — Windows spawn 对真实装饰函数不可用

**严重度：P1**  
**状态：NOT_CLOSED**

## 定位

- `collector/netguard.py:116-133` `_pick_context`
- 生产采集器，例如：
  - `collector/modules/turnover.py:250` `@net_guard(...)`
  - `collector/modules/raw_archive.py:134-136`
  - market_index / margin / northbound / sentiment / sectors / fund_flow 等同类入口
- 专项测试：
  - `collector/tests/test_tracks_dynamic.py:333-470`

## 证据

Windows/无 fork 路径先执行：

```text
pickle.dumps(fn)
```

但生产代码是典型：

```python
@net_guard(...)
def collect_turnover(...):
    ...
```

装饰完成后：

- 模块符号 `collector.modules.turnover.collect_turnover` 指向 wrapper；
- net_guard closure 中的 `fn` 是原始函数；
- 原函数仍声明自己是 `collector.modules.turnover.collect_turnover`；
- pickle 根据 module + qualname 回查时得到的是 wrapper，不是 closure 中的原函数。

本轮对真实 `turnover.collect_turnover` wrapper 的 closure 做只读复验：

```text
module attr same? False
PicklingError:
Can't pickle <function collect_turnover ...>:
it's not the same object as collector.modules.turnover.collect_turnover
```

因此 Windows `_pick_context(fn)` 会直接抛 `GuardedCallError`，不会进入 spawn worker。

### 为什么现有测试没发现

专项测试采用：

```python
def _ng_slow(...):
    ...

slow = net_guard(...)(_ng_slow)
```

模块符号 `_ng_slow` 仍然指向原函数，所以 `pickle.dumps(_ng_slow)` 可以成功。

它与生产 `@net_guard` 装饰器语法并不等价。

## 根因

spawn 设计把“原始函数对象可 pickle”作为前提，但 `functools.wraps` 并不能让已被模块同名 wrapper 覆盖的原函数重新成为 pickle 可解析的全局符号。

## 影响

在 Windows 真实采集路径中：

- 不会回退到不安全线程，这是好事；
- 但所有真实 `@net_guard` 采集入口会 fail-closed，无法正常采集；
- 所谓“Windows spawn 兜底已支持”不成立。

此外，`_run_once_hard_timeout()` 的正常成功/异常 return 路径在 `process.close()` 前直接 return/raise；显式 close 只覆盖 timeout 与 unknown payload 分支。当前 CPython 多数情况下可由对象回收兜底，但 Windows 长期多调用场景最好统一显式释放句柄。

## 建议

不建议把原 `fn` 对象直接作为 spawn 参数。

可采用稳定的 module-level target registry：

1. 装饰时生成稳定 key，例如 `module + qualname`；
2. 在模块 import/装饰阶段把原函数登记到进程内 registry；
3. spawn 子进程只接收字符串 key；
4. 子进程 import 原模块后，由 registry 解析真正未包装函数并直接调用；
5. 不调用 wrapper，避免递归再次 spawn；
6. 新增“**真实 `@net_guard` decorator syntax + 强制 spawn context**”回归测试；
7. success/error/timeout 全路径统一 `process.close()`。

**两处有意差异 #2：思路可接受，但当前实现不可接受。**

---

# 5. R13-P2-01 — 迟滞选池 / 预热 / WARMING_UP

**原严重度：P2**  
**R14 裁定：NOT_CLOSED**

## 5.1 已实现部分

`config/tracks.yaml v3.1` 已新增：

- `entryWindowDays: 3`
- `entryMinDays: 2`
- `exitRankMax: 12`
- `exitConfirmDays: 2`
- `prewarmRankMax: 16`
- `minHistoryDays: 20`

`select_scoring_pool()` 也确实：

- 从全历史 universe 逐日递推；
- 入池使用 2/3 日确认；
- 入池 rank<=8，出池 rank>12；
- 缺当日行会进入 `_exit_hit(None)`；
- `select_discovery_pool()` 对排名前 16 做预热；
- `archive_raw._boards_needing_history()` 将 scoring pool ∪ discovery pool 纳入历史回补；
- 动态板块历史不足时 item `dataReadiness=WARMING_UP`。

这些都属于实质修复。

## 5.2 阻断问题 A：所谓“连续 2 日”实际是“累计 2 次”

定位：

`collector/modules/tracks.py:670-681`

当前逻辑等价于：

```python
streak = old_streak + (1 if exit_hit else 0)
```

**非 exit_hit 日没有把 streak 重置为 0。**

### 独立最小复验

4 日只有一个板块：

| 日期 | 净流入 | 期望 |
|---|---:|---|
| D1 | +1 | 入池 |
| D2 | -1 | streak=1，保留 |
| D3 | +1 | **恢复，应 streak=0** |
| D4 | -1 | 只是一日失败，应保留 |

当前结果：

```text
D1 在池
D2 在池
D3 在池
D4 被移出
```

即 D2 与 D4 两次**非连续**失败被累计成 2 次。

现有测试只覆盖：

- 单日失败；
- 连续两日失败；

没有覆盖“失败→恢复→失败”。

### 必要修正

语义必须改为：

```text
if exit_hit:
    streak = old + 1
else:
    streak = 0
```

并增加以下负向回归：

```text
FAIL → PASS → FAIL
最终仍在池
```

## 5.3 阻断问题 B：`minHistoryDays` 目前是标签，不是真正的评分池就绪门禁

Part 1 的修复契约是：

> 正式评分池必须同时满足市场资格 + 身份映射 + 最低历史就绪条件；历史不足候选进入 WARMING_UP，而不是直接当作成熟评分成员。

当前实现：

- `select_scoring_pool()` 完全不检查历史深度；
- 候选照常进入 `out_tracks`；
- 照常进入 `score_tracks()`；
- `_make_track_item()` **评分完成后**才把 `dataReadiness` 覆盖成 `WARMING_UP`。

因此 `minHistoryDays=20` 是输出标记，不是“正式评分池 gate”。

当前测试也只断言：

```text
dataReadiness == WARMING_UP
historyDays == 0
```

没有断言：

- warming item 不参与正式评分；
- warming item 不输出成熟 decision；
- warming item 不影响模块 D0 完整度。

## 5.4 边界风险：缺行被当作市场出池事实前，没有先证明 universe 本身完整

`collect_industry_universe()` 目前只要求：

```text
summary 非空
items 非空
```

就把 universe 归档为成功，并记录 `boardCount`。

如果上游某天只返回部分行业行，该记录仍可能成为“已知交易日”；随后：

```text
某板块当日缺行 → _exit_hit(None) = True
```

两天部分响应就可能驱动大规模错误出池。

“缺行计入出池条件”本身可以是产品规则，但前置条件应是：

> 当日 universe 已通过最低完整性校验。

否则数据源缺失被误解释为市场资格失败。

## 建议

本轮无需推翻 R13 方向，只需增量收口：

1. 健康日必须 reset exit streak；
2. 增加 fail→recover→fail 回归；
3. 明确 WARMING_UP 是否属于正式评分池：
   - 若不属于：不允许成熟 score/decision 参与 D0；
   - 若允许展示：至少要将其与正式 READY scoring 分开计数；
4. 对 universe 建立最低完整性门禁后，才允许“缺行=exit hit”。

---

# 6. R13-P2-02 — coverage 三态与 D0

**原严重度：P2**  
**R14 裁定：CLOSED**

## 6.1 配置

`config/track-scoring.yaml`：

```text
coverage_target_pct = 80
coverage_hard_floor_pct = 65
```

并保留说明：

- >=80 → READY / TRACKS_SUFFICIENT
- [65,80) → DEGRADED / TRACKS_DEGRADED
- <65 → INSUFFICIENT

## 6.2 模块状态

`collector/modules/tracks.py:1163-1243` 已实现：

- critical failure 或 `< floor` → `UNAVAILABLE / TRACKS_INSUFFICIENT`
- `>= target` → `PARTIAL / TRACKS_SUFFICIENT / READY`
- `[floor,target)` → `PARTIAL / TRACKS_DEGRADED / DEGRADED`

不再把 79.x 一刀切为不可用。

## 6.3 D0 完整性

`collector/completeness.py:_tracks_ok()`：

只有：

```text
status == PARTIAL
decision == TRACKS_SUFFICIENT
coverage >= coverage_target
```

才允许 tracks 点亮 D0。

`TRACKS_DEGRADED` 明确不能通过 `_tracks_ok()`。

因此：

> **DEGRADED 不点亮 D0 CLOSE_COMPLETE**

与送审说明一致。

## 6.4 validator

`collector/validators/schema.py`：

- PARTIAL decision 只允许 `TRACKS_SUFFICIENT` / `TRACKS_DEGRADED`
- sufficient 要求 coverage >= target
- degraded 要求 floor <= coverage < target
- < floor 拒绝

且阈值读取 `track-scoring.yaml`。

### 裁定

R13-P2-02 **CLOSED**。

### 已知边界 #3

`coverage_hard_floor_pct=65` 明确标注为临时值，待 20~30 个真实交易日回放后重标。

这属于**已披露的参数校准债务**，不是当前实现缺陷，**本轮不登记新编号**。

---

# 7. R13-P3-02 — acceptance 顶层身份闭合

**原严重度：P2**  
**R14 裁定：CLOSED（原要求）**

## 已实现

`tools/acceptance/accept.py:_validate_manifest_latest_identity()` 已检查：

- availableDates 类型/格式；
- 去重；
- 升序；
- latestCapturedDate == availableDates[-1]；
- latestDate alias == latestCapturedDate；
- 三指针非空值必须属于 availableDates；
- 三指针日期有序；
- latest.json.tradeDate == latestCapturedDate；
- latestCaptured 对应 daily 文件存在；
- daily.tradeDate == latestCapturedDate。

`build_entry()` 还新增：

```text
snapshot.tradeDate != 文件名日期
→ SNAPSHOT_IDENTITY_MISMATCH
→ schemaValid=False / FAIL
```

本轮定点 identity 测试通过。

因此 R13 原要求 **CLOSED**。

但 checker 有一个新边界漏洞，见 `R14-P3-02`。

---

# 8. R14-P3-02 — acceptance 允许非法的 null 指针链

**严重度：P3**  
**状态：NOT_CLOSED**

## 定位

`tools/acceptance/accept.py:2348-2355`

当前：

```python
non_null_chain = [
    value for value in (final, close_complete, captured)
    if value is not None
]
if non_null_chain != sorted(non_null_chain):
    ...
```

## 问题

先过滤 None 会丢失“阶段蕴含关系”。

设计文档与 `collector/jobs/common.py:421` 明确：

> FINAL 隐含 CLOSE_COMPLETE。

但以下 manifest：

```text
latestCapturedDate = 2026-08-20
latestCloseCompleteDate = null
latestFinalDate = 2026-08-18
```

当前 identity checker 返回：

```text
[]
```

即错误 PASS。

## 根因

只验证“非空日期的排序”，没有验证“指针存在性的单调关系”。

## 建议

增加：

```text
latestFinalDate != null
    => latestCloseCompleteDate != null
latestCloseCompleteDate != null
    => latestCapturedDate != null
```

并新增对应负向测试。

可顺便把 `YYYY-MM-DD` regex 进一步升级为真实 calendar date parse，但后者不单独登记问题。

---

# 9. R13-P3-03 — close-snapshot 发布自检

**原严重度：P2**  
**R14 裁定：CLOSED**

workflow 已按 R13 建议改为：

- `LOCAL=web/dist/data/latest.json`
- 计算本地 SHA-256
- 解析 local tradeDate
- 拉线上 `/data/latest.json`
- 计算 remote SHA-256
- 解析 remote tradeDate
- 只有：

```text
remote tradeDate == local tradeDate
AND
remote sha256 == local sha256
```

才 `SITE_LATEST_EXACT_MATCH`。

共 6 次、每次 30 秒间隔重试。

因此不再把“updatedAt 比 jobStart 新”当作部署正确性。

**R13-P3-03 CLOSED。**

---

# 10. R13-P3-04 — archive-raw 发布自检

**原严重度：P2**  
**R14 裁定：NOT_CLOSED**

## 10.1 4 required + 1 optional 策略本身

当前：

```text
REQUIRED:
- track-board-close
- track-board-flow
- limit-up-pool
- industry-universe-snapshot

OPTIONAL:
- track-membership-snapshot
```

由于当前送审包确实没有 membership jsonl，而 membership 受当日接口/概念短路限制，因此：

> **把 membership 从“绝对 required”降为 optional 是可接受的产品策略。**

这不要求照抄前轮 `[FIX]` 的 5 required。

## 10.2 但实现与自己声明的 optional 语义不一致

workflow 注释明确：

> “存在则必须一致，缺失只告警不失败。”

实际 `check_one()`：

- optional 本地缺失 → warning，合理；
- optional 本地存在但线上拉不到或 SHA 不一致 → 最终：

```text
OPTIONAL_ARCHIVE_MISMATCH ... (warning only)
```

并**不设置 `ok=0`**。

因此“存在则必须一致”没有实现。

### 进一步事实

`collector/jobs/archive_raw.py` 当前已经每日执行：

```text
collect_membership(...)
```

也就是说 membership 并不是一个尚未启用的死模块。

当某天行业 membership 接口恢复/成功时，本地 `track-membership-snapshot.jsonl` 可以自然出现；不需要额外“启用开关”。

此时它若未正确部署，workflow 仍可绿色通过。

## 根因

把两种 optional 语义混在一起：

1. 文件不存在：允许；
2. 文件已存在但发布不一致：也允许。

真正需要的是：

```text
optional absent = warning
optional present = exact-match required
```

## 建议

最小修改：

- optional 本地不存在：继续 warning；
- optional 本地存在：
  - remote 不存在 / unreachable / SHA mismatch → `ok=0`；
- 添加 3 个 shell/脚本化回归：
  1. optional absent → PASS
  2. optional present + match → PASS
  3. optional present + mismatch → FAIL

### 两处有意差异 #1

**策略可接受，当前实现不可接受。**

因此 R13-P3-04 仍 **NOT_CLOSED**。

---

# 11. R13-P3-05 — 前端 stale response

**原严重度：P3**  
**R14 裁定：CLOSED**

`useSnapshots.ts` 已新增：

```text
requestSequence
requestId = ++requestSequence
```

在：

- success
- catch
- finally

三处均要求：

```text
requestId === requestSequence
```

才能写当前状态。

因此旧请求后返回不会覆盖新日期结果，也不会错误清除新请求 loading。

**R13-P3-05 CLOSED。**

---

# 12. R14-P2-01 — tracks acceptance 标准已与现行模型失配

**严重度：P2**  
**状态：NOT_CLOSED**

## 定位

- `docs/acceptance/template-standard.json`
- `tools/acceptance/accept.py:1049+ check_tracks`
- `collector/modules/tracks.py`

## 证据

当前 `tracks_V2` 仍：

```text
requiredStatus = FINAL
```

item `decision` 枚举仍是旧模型：

```text
核心防御主线
次主线
主跌浪
退潮主线
观察
达标
规避
数据不足
```

但 R12/R13 当前输出模型是：

```text
module status:
PARTIAL / UNAVAILABLE

module decision:
TRACKS_SUFFICIENT
TRACKS_DEGRADED
TRACKS_INSUFFICIENT

item decision:
核心主赛道
次主线/轮动主线
短线支线
一日游脉冲/回避
数据不足
```

而 `check_tracks()` 会直接执行：

```text
status != requiredStatus → gap
```

因此当前设计下的健康 `PARTIAL/TRACKS_SUFFICIENT` 仍会被 acceptance 判 FAIL。

## 为什么不能继续当“已知边界”

这不是历史数据天然缺失，而是**当前权威验收标准与当前生产数据契约互相矛盾**。

当项目把 acceptance 作为验收依据时，“新正常数据按设计必 FAIL”会导致：

- FAIL 失去告警区分度；
- 真回归与已知标准滞后混在一起；
- 无法用 acceptance PASS 作为收敛证据。

因此应登记新编号，而不能仅写“预期 FAIL”。

## 建议

需要一次产品裁决，但裁决完成前保持 NOT_CLOSED。

建议标准层支持：

```text
allowedStatuses: [FINAL, PARTIAL]
```

而不是把 `requiredStatus` 简单改成 PARTIAL，因为 Legacy FINAL 仍要合法。

并同步定义：

- PARTIAL + TRACKS_SUFFICIENT
- PARTIAL + TRACKS_DEGRADED
- UNAVAILABLE + TRACKS_INSUFFICIENT

各自允许的字段完整度、item decision 枚举、dataReadiness 和 coverage 区间。

**已知边界 #1：应登记为本轮新问题 `R14-P2-01`。**

---

# 13. R14-P3-01 — 前端尚未消费新的 tracks 就绪态契约

**严重度：P3**  
**状态：NOT_CLOSED**

## 定位

- `web/src/types/smi.ts`
- `web/src/modules/TrackMonitorPanel.vue`
- `web/src/utils/format.ts`

## 证据

后端新增的 item 字段包括：

```text
dataReadiness
historyDays
```

模块新增：

```text
TRACKS_DEGRADED
coverageTargetPct
coverageHardFloorPct
warmingUpBoards
dataReadiness
```

但 `TrackItem` TypeScript interface 没有：

- dataReadiness
- historyDays

`TracksModule.decision` 仍定义为：

```text
"TRACKS_SUFFICIENT" | "INSUFFICIENT"
```

没有：

- `TRACKS_DEGRADED`
- `TRACKS_INSUFFICIENT`

TrackMonitorPanel 的 16 列也没有展示：

- WARMING_UP
- DEGRADED
- warmingUpBoards
- coverage target/floor

## 正向事实

`StatusBadge` 对 `PARTIAL` 显示：

```text
部分数据
```

而不是“获取失败”。

所以 Part 1 最担心的“PARTIAL 被统一压成 ERROR/获取失败”在当前通用 badge 层**没有发生**。

## 仍存在的问题

WARMING_UP 是 R13-P2-01 的核心新语义，但用户在表格中看不到它。

一个 warming item 仍可能显示：

- 综合分；
- 最终判定；

用户无法判断该结论处于历史预热阶段。

## 建议

前端最小跟进：

1. TypeScript interface 补齐新字段/枚举；
2. TrackMonitorPanel 对 item 显示：
   - `WARMING_UP → 预热中`
   - `DEGRADED → 数据降级`
3. 对 warming item 的“最终判定”增加弱化提示，避免当成熟结论解读；
4. 模块级展示 `coveragePct / target / floor` 可放 tooltip，不必扩主表列。

**已知边界 #4：应登记为 `R14-P3-01`。**

---

# 14. 迟滞递推语义专项裁定

用户特别要求复核：

> 全历史逐日递推 + 当日缺行计入出池。

## 正确部分

- 递推不是只看最后 3 天静态切片，而是从 universe 已知日期起逐日重建 pool；
- 这能在无额外 state 文件时保持确定性重放；
- 排名 8/12 双阈值结构合理；
- entry 2/3 日确认合理；
- missing row 纳入 exit 条件从 fail-closed 产品语义上可以成立。

## 不正确部分

1. **exit streak 没有在恢复日清零**；
2. **missing row 只有在 universe 本身完整可信时才能代表板块缺席**，当前 collect_industry_universe 只要求非空，没有完整性下限；
3. minHistoryDays 仍未成为正式评分资格 gate。

因此本专项结论：

**方向正确，但实现未闭合，R13-P2-01 保持 NOT_CLOSED。**

---

# 15. coverage 三态与 D0 模型专项裁定

## 状态转移

```text
coverage >= 80
→ PARTIAL / TRACKS_SUFFICIENT / READY
→ completeness._tracks_ok() = true
→ 可点亮 D0

65 <= coverage < 80
→ PARTIAL / TRACKS_DEGRADED / DEGRADED
→ completeness._tracks_ok() = false
→ 不点亮 D0

coverage < 65 或 critical_failed
→ UNAVAILABLE / TRACKS_INSUFFICIENT / FAILED
→ 不点亮 D0
```

这一链条代码上是闭合的。

### 裁定

**R13-P2-02 CLOSED；DEGRADED 不点亮 D0 的设计与实现一致。**

---

# 16. 两处 `[FIX]` 有意差异裁定

## 16.1 archive required=4

**裁定：策略 ACCEPTABLE，当前实现 NOT_CLOSED。**

允许 membership absent 是合理边界；但 local membership 已存在时必须对 remote mismatch fail。

## 16.2 Windows spawn

**裁定：设计方向 ACCEPTABLE，当前实现 NOT_CLOSED。**

为 Windows 增加 spawn 支持符合用户开发环境需求；但真实 decorator 形态不可 pickle，必须先修 `R14-P1-01`。

---

# 17. 4 项已知边界裁定

| 已知边界 | 是否登记新编号 | 裁定 |
|---|---|---|
| 1. tracks_V2 标准滞后 | **是** | `R14-P2-01`；生产契约与验收契约矛盾，不能长期作为“预期 FAIL” |
| 2. margin 08-17/18/19、summary 08-19 存量 FAIL | 否 | 本次 diff 未涉及；属于已披露存量数据状态，不登记新代码问题 |
| 3. coverage floor=65 临时标定 | 否 | 可接受参数校准债务；需后续 20~30 日回放，但不是当前逻辑缺陷 |
| 4. WARMING_UP/PARTIAL 前端映射未展开 | **是** | `R14-P3-01`；类型/展示契约已滞后于后端 |

---

# 18. 建议修复顺序

## 第一优先级

### R14-P1-01
修 Windows spawn 真正的 production decorator 路径，并新增强制 spawn 回归。

## 第二优先级

### R13-P2-01
先修：

```text
exit miss/hit 恢复日清零
```

再明确 WARMING_UP 是否属于正式 scoring pool。

### R13-P3-04
修 optional membership：

```text
absence allowed
presence requires exact remote match
```

### R14-P2-01
完成 tracks acceptance 产品裁决，恢复 acceptance 的可信 PASS/FAIL 语义。

## 第三优先级

### R14-P3-01
补前端类型和 WARMING/DEGRADED 展示。

### R14-P3-02
补 manifest pointer null 单调性负向检查。

---

# 19. 下一轮最小复送证据建议

无需再提交全项目长说明，建议仅提供：

1. `collector/modules/tracks.py`
2. `collector/netguard.py`
3. `.github/workflows/archive-raw.yml`
4. `docs/acceptance/template-standard.json`
5. `tools/acceptance/accept.py`
6. `web/src/types/smi.ts`
7. `web/src/modules/TrackMonitorPanel.vue`
8. 新增/修改测试文件
9. 对应最小 diff

建议必须包含以下新增负向测试：

- exit：`FAIL → PASS → FAIL` 不得出池；
- forced spawn + **真实 decorator syntax**；
- optional membership absent / match / mismatch 三态；
- final!=null + closeComplete=null 必须 identity FAIL；
- tracks current PARTIAL/SUFFICIENT 与 PARTIAL/DEGRADED acceptance 正例；
- frontend typecheck 覆盖 TRACKS_DEGRADED/WARMING_UP。

---

# 20. 最终裁定

**R14：HOLD。**

R13 七项：

```text
R13-P3-01 CLOSED
R13-P2-01 NOT_CLOSED
R13-P2-02 CLOSED
R13-P3-02 CLOSED
R13-P3-03 CLOSED
R13-P3-04 NOT_CLOSED
R13-P3-05 CLOSED
```

新增：

```text
R14-P1-01 NOT_CLOSED
R14-P2-01 NOT_CLOSED
R14-P3-01 NOT_CLOSED
R14-P3-02 NOT_CLOSED
```

**新增问题数量：P1=1 / P2=1 / P3=2。**

**本轮不能声明“0 NOT_CLOSED，ChatGPT 侧已收敛”。**

再次声明：**未修改调用方本地工作区。**
