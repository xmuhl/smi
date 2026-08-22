# SMI R19 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R19（R18 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R19_source_20260822.zip`  
**送审声明 HEAD：** `dbc0fae`  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**

---

# 1. 最终结论

**R19：HOLD。**

本轮唯一待裁项：

```text
R17-P2-01  NOT_CLOSED
```

新增问题：

```text
P1=0 / P2=0 / P3=0
```

这里仍不是新编号，而是 **R17-P2-01 的“configVersion 必须是唯一规范、严格 x.y 版本字符串”状态空间尚未完全闭合**。

R19 已修复 R18 报告中列出的主要 ASCII 畸形值，但当前唯一解析器仍存在两个可复验的格式旁路：

1. `3.2\n`：Python 正则 `$` 可在末尾单个换行前匹配；
2. `3２.2` / `3٢.2`：`\d` 是 Unicode 数字类，可使非 ASCII 数字与 ASCII 版本映射到同一版本元组。

因此本轮不能声明：

> **“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

---

# 2. 本轮定点复核范围

R19 ZIP 实际包含 6 个文件：

1. `smi/docs/acceptance/template-standard.json`
2. `smi/tools/acceptance/accept.py`
3. `smi/tools/acceptance/test_accept.py`
4. `smi/work/SMI_R18_Review_Report.md`
5. `smi/work/SMI_R19_Fix_Notes.md`
6. `smi/review/r19_diff_0e2cfbf.patch`

符合 R18 的最小复送原则。

本轮重点只复核：

- `_parse_strict_version()`；
- `strict_v42` 是否统一调用它；
- `tracksVersionSchedule.minConfigVersion` 是否统一调用它；
- cutoff 后畸形版本是否 fail-closed；
- `<=2026-08-20` 历史精确白名单是否保持。

---

# 3. 已确认正确的 R19 修复

## 3.1 已建立唯一解析器

`accept.py` 当前为：

```python
_STRICT_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)

def _parse_strict_version(value):
    if not isinstance(value, str):
        return None
    m = _STRICT_VERSION_RE.match(value)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))
```

相比 R18 的 `split(".")[:2]`，这是实质改进。

---

## 3.2 两处版本语义已统一消费同一解析器

当前：

### strict_v42

```text
_v42 = _parse_strict_version(cfg_version)
strict_v42 = _v42 is not None and _v42 >= (3, 2)
```

### tracksVersionSchedule

```text
cfg_t = _parse_strict_version(cfg_version)
min_t = _parse_strict_version(min_ver)
```

已经消除了 R18 指出的：

> strict 分支与版本下限比较分别手写宽松解析

这一语义分叉。

---

## 3.3 R18 直接列出的 ASCII 畸形值已被阻断

R19 测试当前覆盖：

```text
3.2.1
3.2.
4
3.2<尾空格>
<前空格>3.2
03.02
空串
```

并保留：

```text
future + 3.0     => FAIL
future + legacy  => FAIL
future + 3.x     => FAIL
08-20 + 3.0      => PASS
future + 3.2     => PASS
future + 4.0     => PASS
```

这些方向均正确。

---

# 4. 专项测试独立复验

本端直接从 R19 ZIP 抽取最小包执行：

```text
pytest -q tools/acceptance/test_accept.py -k tracks_v4
```

结果：

```text
27 passed
```

当前 R19 专项用例本身均有效。

由于 R19 是最小复送包，没有完整：

```text
web/public/data/manifest.json
完整 daily 历史样本
```

所以直接运行整个：

```text
tools/acceptance/test_accept.py
```

时，其余 30 条依赖全项目样本的测试因文件缺失报 setup error。

这只是最小包证据边界，不登记项目缺陷。

本报告记录送审方：

```text
297 passed + 1 skipped
```

但不把该数字冒充为本端独立全量复验结果。

---

# 5. R17-P2-01 仍未闭环：`$` 允许末尾换行

## 5.1 当前规范声称

R19 Fix Notes 明确将 `_parse_strict_version()` 定义为：

> 仅接受规范 x.y；无前导零、空白、多段、尾点；字符串与版本元组一一映射。

但 Python `re` 中：

```text
$
```

不仅匹配字符串绝对结尾，也可以匹配：

> 字符串末尾单个 `\n` 之前的位置。

因此：

```python
_STRICT_VERSION_RE.match("3.2\n")
```

可以成功。

---

## 5.2 独立复验

直接调用 R19 最终解析器：

```text
_parse_strict_version("3.2")
=> (3, 2)

_parse_strict_version("3.2\n")
=> (3, 2)
```

这已经违反：

```text
无空白
字符串与元组一一映射
```

两个声明。

---

## 5.3 完整验收链反例

本端使用 R19 当前合法 strict 3.2 模块数据，只把：

```text
configVersion
```

替换成：

```text
"3.2\n"
```

在 cutoff 后日期执行 `check_tracks()`：

```text
PASS
```

即：

```text
future + "3.2\n"
=> 可通过整个 v4 验收
```

这不是解析器单元层的理论问题，而是可到达最终 acceptance PASS 的真实旁路。

---

# 6. R17-P2-01 仍未闭环：`\d` 接受 Unicode 十进制数字

## 6.1 当前正则

```regex
^(0|[1-9]\d*)\.(0|[1-9]\d*)$
```

其中：

```text
[1-9]
```

是 ASCII，

但：

```text
\d
```

在 Python 默认 Unicode 正则语义下不是 `[0-9]`，而是 Unicode decimal digit。

因此第一位后的数字可以不是 ASCII。

---

## 6.2 独立复验

例如：

```text
"3２.2"
```

其中 `２` 是全角数字 2。

R19 当前解析器：

```text
_parse_strict_version("3２.2")
=> (32, 2)
```

而规范 ASCII 字符串：

```text
"32.2"
=> (32, 2)
```

两个不同字符串映射到同一版本元组。

同样：

```text
"3٢.2"
```

其中 `٢` 是阿拉伯-印度数字 2，

当前也得到：

```text
(32, 2)
```

---

## 6.3 完整验收链反例

本端以完整 strict 模块数据验证：

```text
future + configVersion="3２.2"
=> PASS

future + configVersion="3٢.2"
=> PASS
```

因此：

> R19 声称的“字符串与版本元组一一映射”目前并不成立。

---

# 7. 为什么本轮仍沿用 R17-P2-01，不登记新编号

R17-P2-01 的根目标是：

> cutoff 后 `configVersion` 必须是规范且可唯一比较的严格版本字符串；任何非规范/损坏值必须 fail-closed，不能通过版本表示差异绕过权威版本门禁。

R18 报告又进一步要求：

> 唯一严格解析器，字符串与版本元组一一映射。

R19 当前已经按该要求重写解析器，但解析器仍接受：

```text
尾换行
Unicode 数字混写
```

因此这是**同一问题修订仍不完整**，而不是另一个独立功能问题。

故：

```text
R17-P2-01 保持 NOT_CLOSED
新增问题数仍为 0
```

---

# 8. 额外健壮性边界：超长数字可抛 ValueError

本轮还验证到一个低概率健壮性边界。

当前正则允许任意长度的数字段。

在当前 Python 中，如果版本段超过整数转换安全上限，例如约 5000 位数字：

```text
"11111...(5000位).0"
```

正则可以匹配，但：

```python
int(...)
```

可能抛：

```text
ValueError:
Exceeds the limit (...) for integer string conversion
```

即 `_parse_strict_version()` 本身不是完全 total/fail-closed 函数。

这与前两项属于同一个“严格解析器没有完全规范化输入空间”的根因，本轮不另立编号，也不单独提高严重度。

推荐在最终修复时一并通过：

- 字符串长度上限；
- 或捕获 `ValueError` 返回 `None`

收口，避免后续再出现解析器边界轮次。

---

# 9. 建议最终修复方式

无需改变：

- cutoff；
- tracksVersionSchedule；
- 历史 allowedConfigVersions；
- strict v4 状态机。

只需把解析器变成真正的**ASCII 全串匹配**。

## 推荐语义

使用等价：

```text
fullmatch(
  (0|[1-9][0-9]*)\.(0|[1-9][0-9]*)
)
```

关键点：

1. 用 `fullmatch()`，不要依赖 `$`；
2. 用 `[0-9]`，不要用 Unicode `\d`；
3. 必要时限制总长度/单段长度；
4. `int()` 转换异常统一返回 `None`；
5. 仍保持唯一解析器供：
   - `strict_v42`
   - `minConfigVersion`
   两处消费。

建议语义：

```text
0.0     PASS
3.2     PASS
4.0     PASS
32.2    PASS

03.02   FAIL
3.02    FAIL
3       FAIL
3.      FAIL
3.2.1   FAIL
3.2.    FAIL
3.2x    FAIL
3.2<space> FAIL
<space>3.2 FAIL
3.2\n   FAIL
3２.2   FAIL
3٢.2    FAIL
legacy  FAIL（cutoff 后）
空串    FAIL
```

---

# 10. 建议补充的最后一组回归

为了避免再逐轮出现同一解析器变体，建议一次补齐：

```text
"3.2\n"    => FAIL
"3２.2"    => FAIL
"3٢.2"     => FAIL
```

以及可选健壮性：

```text
超长数字版本 => FAIL，不得抛异常
```

同时保留：

```text
3.2  => PASS
4.0  => PASS
0.0  => PASS（若版本域允许）
```

这样才能真正证明：

```text
ASCII canonical version string
<=> 唯一版本元组
```

---

# 11. 历史白名单复核

R19 本轮没有改：

```text
through 2026-08-20
allowedConfigVersions =
legacy / 1.0 / 2.0 / 3.0 / 3.1 / 3.2
```

该窗口采用：

```text
精确字符串白名单
```

因此上述：

```text
3.2\n
3２.2
```

在历史窗口本来也不属于白名单。

本轮发现的旁路只影响：

```text
from 2026-08-21
numericOnly=true
minConfigVersion=3.2
```

所以：

**`<=2026-08-20` 历史兼容行为未见回归。**

---

# 12. 下一轮最小复送建议

仍只需：

1. `tools/acceptance/accept.py`
2. `tools/acceptance/test_accept.py`

如果不修改标准 JSON，则连 `template-standard.json` 都无需重复提交。

建议下一轮直接证明：

```text
_parse_strict_version 使用 ASCII + fullmatch
```

并附：

```text
newline / Unicode digit / 超长数字
```

负向。

无需再次提交此前已经 CLOSED 的任何 SMI 功能材料。

---

# 13. 最终裁定

```text
R17-P2-01  NOT_CLOSED
```

新增：

```text
P1 = 0
P2 = 0
P3 = 0
```

**R19 最终结论：HOLD。**

本轮仍不能声明：

> **“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

再次声明：**未修改调用方本地工作区。**
