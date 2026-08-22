# SMI R18 修复对照说明（Fix Notes）

- 基线：R17 送审 HEAD `ab76aeb`
- 本轮范围：R17 唯一新增项 R17-P2-01（cutoff 后非数值版本 fail-open 旁路）
- 日期：2026-08-22

## R17-P2-01 → 已修复（方案 A：numericOnly fail-closed）

**裁定：采纳。** cutoff 规则（from 2026-08-21）只有 minConfigVersion 没有白名单；旧实现对非数值 configVersion（legacy/3.x/损坏值）解析失败后静默 pass，构成 fail-open：future+3.0 FAIL 但 future+legacy PASS。

按 R17 §10 方案 A 修复：

1. **标准**：from 规则新增 `"numericOnly": true`；
2. **验收器**：cfg 与 min 分别独立解析；cfg 非严格 x.y 数值 → FAIL（"非严格 x.y 数值版本…版本降级旁路"）；可解析但 < 下限 → FAIL。解析失败不再静默 pass；
3. **测试**：新增负向 2 条——cutoff 后自报 `legacy` → FAIL、自报 `3.x` → FAIL。连同 R17 的 future+3.0 负向，R17 §11 要求的三类降级形态（数值/非数值/损坏）全部覆盖。

行为保持：`<=2026-08-20` 历史白名单（legacy/1.0/2.0/3.0/3.1/3.2）不变；08-20 3.0 合法 PASS 不变。

## 验证证据（2026-08-22）

- pytest 全量 **295 passed + 1 skipped**（R17 后 293 净增 2）；
- acceptance --all：PASS=2（07-17、08-20）不变。

## 已知边界（不变）

沿用 R15/R16/R17 裁定。
