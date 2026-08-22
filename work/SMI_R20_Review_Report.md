# SMI R20 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R20（R19 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R20_source_20260822.zip`  
**送审声明 HEAD：** `8757313`  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**

---

# 1. 最终结论

## R17-P2-01：CLOSED

R17→R18→R19 连续追踪的 `configVersion` 版本降级/非规范表示旁路，在 R20 已完成闭环。

本轮：

```text
R17-P2-01  CLOSED
```

新增问题：

```text
P1 = 0
P2 = 0
P3 = 0
```

**本轮 0 NOT_CLOSED，ChatGPT 侧已收敛。**

---

# 2. 本轮复核范围

R20 ZIP 实际包含 6 个文件：

1. `smi/docs/acceptance/template-standard.json`
2. `smi/tools/acceptance/accept.py`
3. `smi/tools/acceptance/test_accept.py`
4. `smi/work/SMI_R19_Review_Report.md`
5. `smi/work/SMI_R20_Fix_Notes.md`
6. `smi/review/r20_diff_0e2cfbf.patch`

本轮按迭代纪律只复核 R19 唯一遗留项，没有重新展开此前已 CLOSED 的 SMI 功能项。

---

# 3. 解析器实现裁定

当前唯一版本解析器：

```text
正则：
(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)

匹配：
fullmatch()

字符域：
ASCII [0-9]

段长：
<= 9
```

并要求输入必须为 `str`。

该组合解决了 R17~R19 的全部已知旁路。

## 3.1 不再依赖 `$`

R19 的：

```text
"3.2\n"
```

旁路来自 Python `$` 可以在字符串末尾换行之前匹配。

R20 改用：

```text
fullmatch()
```

本端验证：

```text
"3.2\n"   -> None
"3.2\r\n" -> None
"3.2\t"   -> None
"3.2 "    -> None
" 3.2"    -> None
```

因此尾换行/空白旁路已闭合。

---

## 3.2 不再使用 Unicode `\d`

R19 的：

```text
"3２.2"
"3٢.2"
```

旁路来自 Python `\d` 接受 Unicode 十进制数字。

R20 使用明确 ASCII：

```text
[0-9]
```

本端验证：

```text
"3２.2" -> None
"3٢.2" -> None
"٣.2"  -> None
"３.２" -> None
```

Unicode 数字混写不能再与 ASCII 版本映射到同一元组。

---

## 3.3 版本字符串成为规范的一一映射

当前允许：

```text
0.0
1.0
2.0
3.2
4.0
32.2
123456789.0
0.123456789
```

当前拒绝：

```text
03.02
3.02
3
3.
3.2.1
3.2.
3.2x
3.2<space>
<space>3.2
3.2\n
3.2\r\n
3.2\t
3２.2
3٢.2
legacy
空串
1234567890.0
0.1234567890
None
float 3.2
bytes b"3.2"
含 NUL 字符
```

因此在当前定义域内：

```text
ASCII canonical version string
<=> 唯一 (major, minor) 元组
```

成立。

---

# 4. 段长上限裁定

R20 增加：

```text
_MAX_VERSION_SEGMENT_DIGITS = 9
```

因此：

```text
123456789.0
```

合法，而：

```text
1234567890.0
```

拒绝。

这同时解决 R19 报告中指出的超长数字 `int()` 健壮性边界：

- 正则匹配后先检查段长；
- 超长段不会进入 `int()`；
- 9 位十进制整数远低于 Python 整数字符串转换安全限制。

该门禁属于合理的 fail-closed 输入规范。

---

# 5. 唯一解析器消费闭合

本轮确认两个关键位置继续共用 `_parse_strict_version()`：

## 5.1 strict_v42

```text
_parse_strict_version(configVersion)
>= (3, 2)
```

决定是否进入 strict 3.2 字段契约。

## 5.2 tracksVersionSchedule

```text
_parse_strict_version(configVersion)
_parse_strict_version(minConfigVersion)
```

用于 cutoff 后版本下限比较。

因此不存在 R18 之前的：

> 一个分支按一种语义解析、另一个分支按另一种语义解析

的状态分叉。

---

# 6. cutoff 后版本状态空间复核

当前权威规则仍为：

```text
from 2026-08-21
minConfigVersion = 3.2
numericOnly = true
```

结合 R20 严格解析器：

## 合法

```text
3.2
3.3
4.0
...
```

只要字符串满足 canonical `x.y` 且版本 >=3.2。

## 非法

### 数值旧版

```text
3.0
3.1
```

→ 低于下限，FAIL。

### 非数值

```text
legacy
```

→ 无法严格解析，FAIL。

### 损坏形态

```text
3.x
3.2.1
3.2.
4
```

→ 无法严格解析，FAIL。

### 空白污染

```text
3.2\n
3.2\r\n
3.2<space>
<space>3.2
```

→ fullmatch 失败，FAIL。

### Unicode 数字混写

```text
3２.2
3٢.2
```

→ ASCII 字符集门禁失败，FAIL。

### 前导零别名

```text
03.02
3.02
```

→ FAIL。

### 超长段

```text
1234567890.0
```

→ FAIL。

因此 R17-P2-01 所要求的完整版本表示空间已经 fail-closed。

---

# 7. 独立测试结果

## 7.1 当前 tracks_v4 专项

本端执行：

```text
pytest -q tools/acceptance/test_accept.py -k tracks_v4
```

结果：

```text
28 passed
```

无失败。

---

## 7.2 解析器矩阵 + tracks_v4

本端执行等价筛选：

```text
tracks_v4 OR strict_version_parser_matrix
```

结果：

```text
29 passed
```

其中 R20 新增：

- `test_strict_version_parser_matrix`
- `test_tracks_v4_version_schedule_unicode_and_newline_rejected`

均实际 PASS。

---

## 7.3 额外独立边界反打

除送审测试外，本端额外检查：

```text
CRLF
tab
NUL
Unicode 全角数字
阿拉伯-印度数字
Unicode 全角句点
多段版本
单段版本
前导零
非字符串
9/10 位段长边界
```

均符合 R20 规范。

---

## 7.4 独立随机对照

本端另外实现了一份不依赖项目正则的规范判定逻辑，规则为：

1. 必须是字符串；
2. 必须 ASCII；
3. 恰好一个 `.`；
4. 两段均非空；
5. 每段仅 `0-9`；
6. 除单字符 `0` 外不得有前导零；
7. 每段 <=9 位。

随机生成约 **20,000** 个包含：

- ASCII 字母/数字；
- 标点；
- 空格/制表/换行；
- Unicode 数字

的字符串，将独立判定结果与 `_parse_strict_version()` 对照。

结果：

```text
0 mismatch
```

这进一步支持“规范字符串 ⇄ 唯一元组”的闭合结论。

---

# 8. 历史白名单行为

R20 没有修改历史时间表。

当前仍为：

```text
through 2026-08-20
allowedConfigVersions =
[
  "legacy",
  "1.0",
  "2.0",
  "3.0",
  "3.1",
  "3.2"
]
```

该区间使用**精确字符串白名单**，不是 `numericOnly`。

因此：

- 07-17 的 `legacy` 历史语义仍保留；
- 08-20 的 `3.0` 仍可合法兼容；
- R20 的严格 numeric 规则只作用于 cutoff 后新数据。

现有 `tracks_v4` 专项测试中：

```text
2026-08-20 + 3.0
```

仍为 PASS。

**历史兼容行为未见回归。**

---

# 9. 关于送审方全量验证数字

送审方声明：

```text
pytest 全量 299 passed + 1 skipped
acceptance --all PASS=2（07-17、08-20）
```

R20 是最小复送包，不含完整项目运行所需全部源码/历史数据，因此本端没有将上述全量数字冒充为独立全量复验。

本端可独立复验的本轮关键路径：

```text
tracks_v4：28 passed
版本矩阵 + tracks_v4：29 passed
额外边界反打：PASS
20,000 随机对照：0 mismatch
```

足以覆盖本轮唯一待裁项。

---

# 10. 新问题检查

本轮针对 R17-P2-01 / R18 / R19 变体链重新检查：

- 数值旧版；
- 非数值；
- 损坏多段；
- 尾点；
- 空串；
- 单段；
- 前导零；
- 前/尾空白；
- LF/CRLF/tab；
- Unicode 数字；
- Unicode 标点；
- 非字符串；
- 超长数字；
- 合法未来 `4.0`。

**未发现新的可到达 acceptance PASS 的版本表示旁路。**

新增问题：

```text
P1=0
P2=0
P3=0
```

---

# 11. 最终裁定

```text
R17-P2-01  CLOSED
```

本轮：

```text
0 NOT_CLOSED
```

## 收敛结论

**本轮 0 NOT_CLOSED，ChatGPT 侧已收敛。**

R17→R20 的版本门禁链最终形成：

```text
历史日期
→ 精确历史白名单

cutoff 后
→ canonical ASCII x.y
→ 唯一版本元组
→ numericOnly
→ minConfigVersion >= 3.2
→ strict_v42 契约
```

未发现同根残余旁路。

再次声明：**未修改调用方本地工作区。**
