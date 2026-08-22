# SMI R17 送审复核报告

**项目：** SMI — A股收盘全景 Web 看板  
**轮次：** R17（R16 修复包复核 · 迭代收敛轮）  
**送审包：** `SMI_R17_source_20260822.zip`  
**送审声明 HEAD：** `ab76aeb`  
**复核日期：** 2026-08-22  
**复核性质：** 只读复核

> **工作区声明：未修改调用方本地工作区；未更新 manifest；未重新打包；未向调用方仓库写入任何文件。**

---

# 1. 总体结论

## 1.1 R16-P2-01 裁定

**R16-P2-01：CLOSED。**

本轮已经真正加入了快照之外的权威版本时间表：

```text
through 2026-08-20:
  allowedConfigVersions =
  legacy / 1.0 / 2.0 / 3.0 / 3.1 / 3.2

from 2026-08-21:
  minConfigVersion = 3.2
```

并在验收器中按 `trade_date` 匹配该时间表。

本轮独立复验确认：

- `2026-08-20 + configVersion=3.0` → **PASS**
- `2026-08-24 + configVersion=3.0` → **FAIL**
- `2026-08-19 + configVersion=9.9` → **FAIL**

因此 R16 所指出的具体缺陷：

> “未来新快照错误自报 3.0，可以伪装历史兼容而绕过 3.2 strict 契约”

已经闭环。

---

## 1.2 新增问题

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| **R17-P2-01** | P2 | **NOT_CLOSED** | cutoff 后的非数值 configVersion（如 `"legacy"`、`"3.x"`）仍可绕过 `minConfigVersion=3.2`；代码解析失败后直接 `pass`，而 cutoff 规则没有 `allowedConfigVersions` 可兜底 |

**新增：P1=0 / P2=1 / P3=0。**

因此：

**R17 结论：HOLD。**

本轮不能声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。

---

# 2. 本轮定点复核范围

按 R16 §12 最小复送原则，重点读取和复验：

1. `docs/acceptance/template-standard.json`
2. `tools/acceptance/accept.py`
3. `tools/acceptance/test_accept.py`
4. `web/public/data/daily/2026/2026-08-20.json`
5. `web/public/data/daily/2026/2026-07-17.json`
6. `web/public/data/manifest.json`
7. `work/SMI_R17_Fix_Notes.md`
8. `work/SMI_R17_Review_Request.md`

未重新展开此前已 CLOSED 的 netguard、tracks 因果门禁、archive sync、前端等问题。

---

# 3. 独立复验结果

## 3.1 v4 专项测试

本端执行：

```text
pytest -q tools/acceptance/test_accept.py -k tracks_v4
```

结果：

```text
23 passed
```

其中当前源码实际包含：

- R16 既有 21 条；
- R17 新增 2 条。

与送审说明“291 后净增 2”逻辑一致。

---

## 3.2 08-20 真实生产快照

R17 包内真实：

```text
tradeDate = 2026-08-20
tracks.configVersion = 3.0
```

直接调用当前 `check_tracks()`：

```text
PASS
```

没有 contract gap。

因此：

> **08-20 3.0 历史兼容行为保持正确。**

---

# 4. 权威版本时间表复核

## 4.1 标准层已经从“自证”升级为外部契约

`template-standard.json` 新增：

```text
tracksVersionSchedule
```

这一步是正确的。

它解决了 R16 的根问题：

原来：

```text
快照自己说自己是 3.0
→ checker 决定使用宽松 3.0 验收
```

现在增加：

```text
trade_date
→ 外部标准决定该日期允许什么版本
```

因此 `configVersion` 不再是唯一决定验收强度的来源。

---

## 4.2 through=2026-08-20 的历史白名单

当前：

```text
legacy
1.0
2.0
3.0
3.1
3.2
```

R17 最小包只能直接确认：

```text
2026-07-17 = legacy
2026-08-20 = 3.0
```

其他历史日期的真实 configVersion 没有全部随本轮最小包提供，因此本端不能重新逐日独立证明白名单与 25 个历史快照完全一一对应。

但：

- 白名单与 Fix Notes 中披露的历史版本集合一致；
- 该历史规则的目标是兼容存量数据；
- 对 R16 原阻断项最关键的是 cutoff 后不能再降级。

因此这个证据范围限制本身不构成本轮新 NOT_CLOSED。

---

# 5. cutoff=2026-08-21 是否合理

## 5.1 结论

**可接受。**

当前 manifest 最后一个已捕获日期是：

```text
2026-08-20
```

因此把：

```text
2026-08-20 及以前
```

定义为存量兼容窗口，把：

```text
2026-08-21 及以后
```

定义为新契约窗口，是清晰且 fail-closed 的切分。

它还有一个优点：

> 即使以后人工 backfill 2026-08-21，也必须产出至少 3.2，而不能再生成旧 3.0 形态。

因此无需把 cutoff 推迟到下一次 cron 实际执行日。

---

# 6. R17-P2-01 — cutoff 后非数值版本仍可绕过

**严重度：P2**  
**状态：NOT_CLOSED**

## 6.1 定位

`tools/acceptance/accept.py` 的 `tracksVersionSchedule` 检查。

当前 cutoff 规则：

```json
{
  "from": "2026-08-21",
  "minConfigVersion": "3.2"
}
```

没有：

```text
allowedConfigVersions
```

---

## 6.2 当前实现

逻辑等价于：

```python
min_ver = rule.get("minConfigVersion")

if isinstance(min_ver, str) and isinstance(cfg_version, str):
    try:
        cfg_t = tuple(int(x) for x in cfg_version.split(".")[:2])
        min_t = tuple(int(x) for x in min_ver.split(".")[:2])

        if cfg_t < min_t:
            FAIL

    except ValueError:
        pass
        # 注释：非数值版本由 allowedConfigVersions 裁决
```

问题在于：

> cutoff 规则没有 `allowedConfigVersions`。

因此 ValueError 后没有任何第二道裁决。

---

## 6.3 独立最小反例

本轮构造：

```text
tradeDate = 2026-08-24
status = UNAVAILABLE
configVersion = "legacy"
effectiveFrom = 2026-08-20
effectiveTo = 2026-12-31
sourceSystem = THS_UNIVERSE
decision = TRACKS_INSUFFICIENT
coveragePct = 71.4
items = []
```

不携带 strict 3.2 字段：

```text
dataReadiness
coverageTargetPct
coverageHardFloorPct
warmingUpBoards
```

当前验收结果：

```text
PASS
```

也就是说：

```text
future + 3.0   => FAIL
future + legacy => PASS
```

版本降级旁路仍然存在，只是从“数值旧版本”缩小成“非数值旧版本”。

同理：

```text
configVersion = "3.x"
```

这类解析失败值也可能走同一路径。

---

# 7. 为什么这是新编号，不复活 R16-P2-01

R16-P2-01 的明确反例是：

```text
未来新快照自报 3.0
```

R17 已经：

- 增加外部时间表；
- 成功阻断未来 3.0；
- 增加对应负向测试。

所以原问题可以 CLOSED。

本轮发现的是该新实现中的独立变体：

> `minConfigVersion` 只对可解析数值版本 fail-closed，非数值版本 fail-open。

按迭代纪律应登记：

```text
R17-P2-01
```

而不是复活 R16-P2-01。

---

# 8. 根因

当前实现同时支持两类历史 configVersion：

```text
数值版本：1.0 / 2.0 / 3.0 / 3.1 / 3.2
非数值版本：legacy
```

但 cutoff 后规则只表达：

```text
minimum numeric version
```

没有表达：

```text
cutoff 后禁止任何非数值版本
```

实现又把解析失败当成：

```text
交给白名单
```

而该规则恰好没有白名单。

最终形成 fail-open。

---

# 9. 影响

如果未来出现：

- 旧 worker 回退到 `"legacy"`；
- 版本常量错误；
- configVersion 拼写损坏；
- `"3.x"` 等非规范值；

验收器可能：

1. 判定 `strict_v42=False`；
2. 跳过 3.2 必填字段；
3. 又绕过 minConfigVersion；
4. 最终 PASS。

因此 R16 要解决的“不能让快照自报旧版本降低验收强度”的安全目标还没有对**完整版本状态空间**闭合。

---

# 10. 修复建议

不需要改变当前 cutoff，也不需要改变 08-20 历史兼容。

建议把 cutoff 规则改成 fail-closed 二选一。

## 方案 A：推荐

标准：

```text
from 2026-08-21:
  minConfigVersion = 3.2
  numericOnly = true
```

验收器：

```text
如果 cfg_version 不能严格解析为 x.y
→ FAIL

如果可解析但 <3.2
→ FAIL
```

这样：

```text
legacy
3.x
unknown
空字符串
```

全部 FAIL。

---

## 方案 B

cutoff 后同时提供明确白名单，例如：

```text
from 2026-08-21:
  allowedConfigVersions = ["3.2"]
```

若未来升级 3.3，再更新时间表：

```text
from <3.3 cutoff>:
  minConfigVersion = 3.3
```

对于当前项目，**A 更适合长期演进**，因为不必每次 patch version 都更新精确白名单。

---

# 11. 必补负向测试

至少新增：

```text
2026-08-24 + configVersion="legacy"
=> FAIL
```

建议再补：

```text
2026-08-24 + configVersion="3.x"
=> FAIL
```

保留现有：

```text
2026-08-20 + 3.0
=> PASS

2026-08-24 + 3.0
=> FAIL

2026-08-19 + 9.9
=> FAIL
```

这样时间表状态空间才真正完整覆盖：

```text
historical allowed numeric
historical allowed nonnumeric legacy
historical unknown version
future numeric downgrade
future nonnumeric downgrade
future malformed version
```

---

# 12. 08-20 历史兼容最终裁定

**符合预期契约。**

R17 不应为了修新问题而回头强迫 08-20 使用 3.2。

正确目标应是：

```text
<= 2026-08-20:
  按历史白名单兼容

>= 2026-08-21:
  必须是严格可解析且 >=3.2
```

这样既不修改历史，又阻断未来降级。

---

# 13. 下一轮最小复送

只需：

1. `tools/acceptance/accept.py`
2. `tools/acceptance/test_accept.py`
3. 若标准新增 `numericOnly` 或其他字段：
   `docs/acceptance/template-standard.json`

无需再提交 tracks、netguard、前端、archive、N01 等已闭环材料。

---

# 14. 最终裁定

```text
R16-P2-01  CLOSED
R17-P2-01  NOT_CLOSED
```

新增问题：

```text
P1 = 0
P2 = 1
P3 = 0
```

**R17 最终结论：HOLD。**

**本轮不能声明“本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”。**

再次声明：**未修改调用方本地工作区。**
