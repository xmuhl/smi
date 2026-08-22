# SMI R18 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R18（R17 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R18_source_20260822.zip`  
**送审声明 HEAD：** `f2b1813`  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**

---

# 1. 最终结论

**R18：HOLD。**

本轮唯一待裁项：

```text
R17-P2-01  NOT_CLOSED
```

新增问题：

```text
P1=0 / P2=0 / P3=0
```

这里不是新编号，而是 **R17-P2-01 原问题的“损坏版本值完整状态空间”仍未闭合**。

因此本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

---

# 2. 本轮定点复核范围

R18 ZIP 实际仅包含 6 个文件，符合最小复送方向：

1. `docs/acceptance/template-standard.json`
2. `tools/acceptance/accept.py`
3. `tools/acceptance/test_accept.py`
4. `work/SMI_R17_Review_Report.md`
5. `work/SMI_R18_Fix_Notes.md`
6. `review/r18_diff_0e2cfbf.patch`

本轮重点只复核：

- cutoff 版本时间表；
- `numericOnly` fail-closed；
- 版本解析是否真的“严格 x.y”；
- `<=2026-08-20` 历史白名单是否保持。

---

# 3. 已确认正确的修复

## 3.1 标准已增加 numericOnly

`template-standard.json` 当前 cutoff 规则：

```text
from = 2026-08-21
minConfigVersion = 3.2
numericOnly = true
```

历史窗口保持：

```text
through = 2026-08-20
allowedConfigVersions =
legacy / 1.0 / 2.0 / 3.0 / 3.1 / 3.2
```

因此设计方向符合 R17 建议。

---

## 3.2 原 R17 三个直接反例已被阻断

本端独立调用当前验收器验证：

| tradeDate | configVersion | 当前结果 | 预期 |
|---|---|---:|---:|
| 2026-08-24 | `3.0` | FAIL | FAIL |
| 2026-08-24 | `legacy` | FAIL | FAIL |
| 2026-08-24 | `3.x` | FAIL | FAIL |
| 2026-08-24 | `""` | FAIL | FAIL |

因此 R17 指出的：

> “ValueError 后静默 pass”

这一具体 fail-open 分支已经消失。

---

## 3.3 历史 08-20 兼容行为未被破坏

当前测试仍明确覆盖：

```text
2026-08-20 + configVersion=3.0
→ PASS
```

历史白名单规则未改。

这一行为符合既有裁决：

> 旧生产快照不应因后续契约升级而被强制补写当时不存在的 3.2 字段。

---

# 4. 专项测试独立复验

本端执行：

```text
pytest -q tools/acceptance/test_accept.py -k tracks_v4
```

结果：

```text
25 passed
```

数量与当前源码一致：

- R17：23 条；
- R18：新增 2 条；
- 合计：25 条。

因此送审方新增的：

- future + `legacy` → FAIL；
- future + `3.x` → FAIL；

两条测试本身均有效。

---

# 5. R17-P2-01 为什么仍 NOT_CLOSED

## 5.1 规范声明的是“严格 x.y”

R18 Fix Notes 和源码错误文案均明确使用：

```text
严格 x.y 数值版本
```

但当前实现不是严格解析。

代码核心仍是等价逻辑：

```python
tuple(int(x) for x in cfg_version.split(".")[:2])
```

这只解析**前两段**，不会验证整个字符串是否正好由：

```text
数字 + "." + 数字
```

组成。

---

## 5.2 新反例：前两段合法、整体格式损坏时仍被接受

本端构造一个完整合法的 strict 模块：

```text
status = UNAVAILABLE
decision = TRACKS_INSUFFICIENT
dataReadiness = FAILED
coveragePct = 40
coverageTargetPct = 80
coverageHardFloorPct = 65
warmingUpBoards = []
items = []
```

仅替换 `configVersion`。

结果：

| configVersion | 当前验收结果 | 按“严格 x.y”应为 |
|---|---:|---:|
| `3.2` | PASS | PASS |
| `3.2.1` | **PASS** | FAIL |
| `3.2.` | **PASS** | FAIL |
| `3.2.x` | **PASS** | FAIL |
| `3.2 ` | **PASS** | FAIL |
| `4` | **PASS** | FAIL |
| `4 ` | **PASS** | FAIL |
| `4.0.0` | **PASS** | FAIL |
| `03.02` | PASS | 取决于是否允许前导零 |
| `3.02` | PASS | 取决于版本规范 |

最关键的是：

```text
3.2.1
3.2.
3.2.x
4
4.0.0
```

都不是严格 `x.y`，但当前可以通过版本门禁。

---

# 6. 根因

存在两个同源解析点：

## 6.1 strict_v42 判定

当前逻辑：

```text
split(".")[:2]
```

只看前两段。

因此：

```text
3.2.x
3.2.1
3.2.
```

都会被视为：

```text
(3, 2)
```

从而进入 strict 3.2 分支。

如果调用方同时提供所有 strict 必填字段，最终整个模块可以 PASS。

---

## 6.2 时间表 minConfigVersion 比较

同样只比较前两段：

```text
cfg_t >= min_t
```

因此：

```text
4
4.0.0
3.2.x
```

等非 `x.y` 形态也可满足下限。

---

# 7. 为什么这仍属于 R17-P2-01，而不是新编号

R17-P2-01 的范围是：

> cutoff 后 `configVersion` 必须 fail-closed，不能让非规范/损坏版本绕过 3.2 契约。

R18 本身又明确声称：

> “cfg 非严格 x.y 数值（legacy/3.x/损坏值/空串）→ FAIL”

因此：

- `legacy` 已修；
- `3.x` 已修；
- 空串已修；
- **损坏值并未完整修复**。

这是同一问题尚未完成，不应另立 R18 新编号。

---

# 8. 影响

这已经不是纯格式洁癖。

如果未来出现：

```text
configVersion = "3.2.x"
configVersion = "3.2.1"
configVersion = "4"
```

验收器会：

1. 把版本视作满足 cutoff；
2. 可能进入 strict 分支；
3. 如果其它字段合法，则最终 PASS。

于是权威版本表仍不能证明：

> “生产快照使用了一个规范、可比较、受契约定义的版本标识。”

版本字段依然存在一部分自解释歧义。

---

# 9. 建议修复

不需要改变时间表，不需要改变 cutoff，也不需要改变历史白名单。

只需要统一版本解析。

## 9.1 建议新增唯一严格解析器

语义：

```text
仅接受 ^\d+\.\d+$
```

然后：

```text
"3.2"   -> (3,2)
"4.0"   -> (4,0)

"3"     -> invalid
"3."    -> invalid
"3.2."  -> invalid
"3.2.1" -> invalid
"3.2.x" -> invalid
" 3.2"  -> invalid
"3.2 "  -> invalid
"legacy"-> invalid numeric version
""      -> invalid
```

是否允许：

```text
03.02
3.02
```

建议产品一次性明确；若无特殊需求，可进一步规范为：

```text
^(0|[1-9]\d*)\.(0|[1-9]\d*)$
```

避免多种字符串映射到同一个版本元组。

---

## 9.2 必须统一消费同一个解析器

至少两个位置不能再各自手写解析：

1. `strict_v42` 判断；
2. `tracksVersionSchedule.minConfigVersion` 比较。

否则会再次出现：

```text
一个分支认为合法，
另一个分支认为非法
```

的版本语义分叉。

---

# 10. 必补测试

建议至少补：

```text
future + "3.2.1" => FAIL
future + "3.2."  => FAIL
future + "4"     => FAIL
future + "3.2 "  => FAIL
```

保留现有：

```text
future + 3.0    => FAIL
future + legacy => FAIL
future + 3.x    => FAIL
future + ""     => FAIL（建议正式固化）
08-20 + 3.0     => PASS
future + 3.2    => PASS（完整 strict 字段）
future + 4.0    => PASS（若未来版本允许）
```

这样才能真正覆盖：

- 合法历史版本；
- 旧数值版本；
- 非数值版本；
- 空串；
- 单段数值；
- 多段版本；
- 尾点；
- 尾随垃圾；
- 空白污染；
- 合法 cutoff 新版本。

---

# 11. 历史白名单最终裁定

`<=2026-08-20` 的行为本轮没有发现回归。

规则仍然是：

```text
allowedConfigVersions 精确字符串白名单
```

因此历史窗口中的：

```text
legacy
1.0
2.0
3.0
3.1
3.2
```

按既有契约处理。

R18 所需修复只应作用于：

```text
from 2026-08-21
numericOnly = true
```

不应回头修改历史文件。

---

# 12. 下一轮最小复送建议

仍只需要三文件：

1. `docs/acceptance/template-standard.json`（如果版本格式规则写入标准）
2. `tools/acceptance/accept.py`
3. `tools/acceptance/test_accept.py`

无需再次提交此前所有已 CLOSED 的 tracks、netguard、archive、前端、N01 等材料。

---

# 13. 最终裁定

```text
R17-P2-01  NOT_CLOSED
```

新增：

```text
P1=0
P2=0
P3=0
```

**R18 最终结论：HOLD。**

**本轮不能声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

再次声明：**未修改调用方本地工作区。**
