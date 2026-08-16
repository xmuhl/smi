# SMI R12 P0.5 复审报告

- 复审轮次：R12 P0.5
- Review 深度：只读复核
- 送审输入 commit：`99dc2a949654cd9a3f702ba2da1a828c9b857289`
- 前轮基线报告 commit：`ece88749ffb28675a6d4c8275fc4e10709e62fa3`
- 前轮唯一待闭环：`SMI-R12-P03-001`
- 本轮结论：**PASS / 收敛**
- 当前 NOT_CLOSED：**P1=0 / P2=0 / P3=0**

> 本轮为只读复核。未修改调用方工作区，也未声称在调用方本地重新执行 pytest。
> 送审方声明 acceptance suite `30/30` 全绿；本轮对源码做静态核验，测试函数数由前轮确认的 29 个增加 1 个，和“30 tests”口径一致。

---

## 1. 送审范围与增量边界

P0.4 已裁决：

- `SMI-R12-P0-003`：CLOSED
- `SMI-R12-P0-007`：CLOSED
- `SMI-R12-P0-008`：CLOSED
- `SMI-R12-P03-001`：NOT_CLOSED（仅缺 `margin.unit` 删除 mutation）

依迭代纪律，本轮不重复复审已经 CLOSED 的前三项，只核验 `P03-001` 的唯一剩余条件及是否出现与该增量直接相关的新问题。

独立 GitHub compare：

- base：`ece8874`
- head：`99dc2a9`
- `ahead_by = 1`
- 变更文件：
  1. `tools/acceptance/test_accept.py`：+8 / -0
  2. `work/SMI_R12_P04_Review_Report.md`：归档新增
  3. `work/SMI_R12_P04_Review_Request.md`：归档新增

因此本轮功能性变更只有一个：在 acceptance 测试中补 `margin.unit` 删除 mutation。生产验收器 `accept.py`、验收标准 `template-standard.json`、manifest、daily snapshots、baseline-report 均未修改。

---

## 2. SMI-R12-P03-001 — CLOSED

- **严重度**：P3（沿用）
- **状态**：**CLOSED**
- **定位**：`tools/acceptance/test_accept.py::test_p04_unit_deleted_margin_invariant`

### 2.1 前轮唯一缺口

P0.4 的最终裁决要求 `INV-UNIT-亿元` 的两个曾经可能形成假阳性的分支均被 mutation 锁死：

1. 删除 `turnover.unit` → invariant 必须为 `false`
2. 删除 `margin.unit` → invariant 必须为 `false`

前轮已有第 1 条，但缺第 2 条，因此 `P03-001` 保留为唯一 P3 NOT_CLOSED。

### 2.2 本轮实际新增测试

`99dc2a9` 中新增：

```python
def test_p04_unit_deleted_margin_invariant(standard, manifest):
    snap = _official_nb_snapshot()
    del snap["modules"]["margin"]["unit"]
    _, _, inv = accept.evaluate_modules(
        snap, standard, "2026-08-14", manifest
    )
    assert inv.get("INV-UNIT-亿元") is False, inv
```

该测试满足上一轮闭环条件：

- 使用可验收的 08-14 OFFICIAL fixture；
- 明确删除 `modules.margin.unit`；
- 经过正式 `evaluate_modules(...)` 验收入口；
- 对目标跨模块不变量 `INV-UNIT-亿元` 做 fail-closed 断言；
- 若未来 margin unit 门禁单独退化，该测试会直接失败。

上一轮已有 `test_p04_unit_deleted_invariant` 覆盖 turnover 分支，因此 turnover + margin 两条删除路径现均有专项 mutation。

### 2.3 关于是否还必须断言 margin 模块自身 FAIL

P0.4 报告中的修复建议写的是：

- `inv["INV-UNIT-亿元"] is False`：闭环必需；
- `checks["margin"]["pass"] is False`：**建议同时锁**。

本问题 `P03-001` 的根因是“`INV-UNIT-亿元` 关键门禁缺专项 regression/mutation”，并非 margin 模块 checker 缺功能实现。P0.4 已独立裁决 `P0-008` 功能逻辑 CLOSED。

因此，本轮新增测试已经精确锁住 P03-001 要求的 invariant 失败语义；未额外断言 `checks["margin"]["pass"]` 不构成新的 NOT_CLOSED。

### 2.4 测试数量核对

P0.4 已静态确认 `test_accept.py` 有 29 个 pytest 测试函数。

本轮 diff 只新增一个 `def test_p04_unit_deleted_margin_invariant(...)`，未删除或参数化现有测试，因此源码静态计数为：

- 前轮：29
- 本轮新增：1
- 当前：**30 个测试函数 / 30 个 pytest 收集节点（按当前无 parametrize 结构）**

这与送审方声明的 `30/30` 数量口径一致。

但本轮没有执行调用方本地 pytest，因此“30/30 全绿”仍属于送审方执行证据；ChatGPT 独立确认的是源码测试数量与测试逻辑均吻合，没有发现数字或覆盖口径矛盾。

### 2.5 裁决

`SMI-R12-P03-001`：**CLOSED**。

---

## 3. 07-17 baseline 不变核对

前轮 `ece8874` 的 `work/acceptance/baseline-report.json` 记录：

- `2026-07-17.overall = PASS`
- 9 个 module 全部 `pass = true`
- 9 个 invariant 全部 `true`

本轮 `ece8874 → 99dc2a9` 没有修改：

- `accept.py`
- `template-standard.json`
- manifest
- daily snapshot
- baseline-report

唯一逻辑变更位于测试文件，不会改变 `build_entry()` 或 baseline 计算输入。

因此，在本轮增量范围内，“07-17 PASS（9/9 模块 + 9/9 invariants）不变”与仓库 diff 一致，没有发现回归证据。

---

## 4. 新发现问题

**无。**

本轮仅针对 P0.4 唯一剩余 P3 覆盖缺口做增量复核，未发现与该变更相关的新变体、数字不一致或回归。

---

## 5. 最终收敛裁决

| 编号 | 严重度 | 本轮状态 | 结论 |
|---|---:|---|---|
| SMI-R12-P03-001 | P3 | **CLOSED** | `margin.unit` 删除 mutation 已补齐并锁住 `INV-UNIT-亿元=false` |

当前问题统计：

- P1 NOT_CLOSED：0
- P2 NOT_CLOSED：0
- P3 NOT_CLOSED：0
- **合计 NOT_CLOSED：0**

**本轮 0 NOT_CLOSED，ChatGPT 侧已收敛。**

---

## 6. 只读复核边界

本报告不表示：

- 已修改调用方本地工作区；
- 已在调用方环境重新执行 pytest；
- 已重新生成 baseline-report；
- 已重新打包或发布项目。

本轮独立可复验事实包括：

1. `99dc2a9` 的实际 GitHub diff；
2. 新增 `margin.unit` mutation 的源码逻辑；
3. 前后测试函数数量关系 29 → 30；
4. 本轮未触及 baseline 计算代码和输入；
5. `ece8874` 中 07-17 的既有 PASS / 9 invariants=true 记录。
