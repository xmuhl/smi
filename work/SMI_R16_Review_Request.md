# SMI R16 送审请求（R15 修复包复核 · 迭代收敛轮）

R15 结论 HOLD：R14 六项 4 CLOSED / 2 NOT_CLOSED（R13-P2-01、R14-P2-01），R15-N01 因送审包证据缺口未闭环，新增 R15-P2-01（包缺 N01 三个最终文件）、R15-P3-01（acceptance 测试未进 CI）。本轮送审全部 4 项的修复（main HEAD=`a3a706c`，基线链 0e2cfbf→ebac337→a3a706c），请**逐项裁定 CLOSED 与否**。

## 修复对照表（完整版见附件 work/SMI_R16_Fix_Notes.md）

| 编号 | 修订摘要 |
|---|---|
| R13-P2-01(P2) | 门禁**因果化**：证据日判定只依赖严格早于当日的前向峰值，且前向峰值只由已过门禁的完整日抬高（可信基线）；绝对下限改**有据非零值** `minUniverseBoards: 45`（2026-08-20 已验证 THS universe 90 板块快照之半，配置注释注明来源）。R15 复现的两个反例（首日 1 板块立案；D3 峰值 6 回溯清空 D1/D2 池）均不可再发生。新增回归 2 条：`test_r15_universe_cold_start_tiny_not_evidence_day`（真实配置下首日 2 板块 → 空池）、`test_r15_universe_gate_causal_no_retro_clear`（partial/partial/full → 池籍保留） |
| R14-P2-01(P2) | v4 矩阵重写为**穷举状态机** + **显式版本分支** `strict_v42`（configVersion>=3.2 全字段契约 / 2.0~3.1 状态配对 / "legacy" 非 strict）：A) PARTIAL 显式拒 TRACKS_INSUFFICIENT；B) decision 存在性扩到所有状态 + UNAVAILABLE 必须精确 TRACKS_INSUFFICIENT + 旧值 "INSUFFICIENT" 拒；C) FINAL 验有限 coverage>=target；D) strict 下 dataReadiness/coverageTargetPct/coverageHardFloorPct/warmingUpBoards 必填且与 decisionContract 单一真源一致；E) strict 下 formal 仅计 READY/DEGRADED（INSUFFICIENT/FETCH_FAILED 不充数 minFormalItems）；F) WARMING_UP 四字段（score/coveragePct/dimensionPass/decision）全检。新增负向 11 条 + 3.0 存量形态正例（真实 08-20 快照形态合法 PASS，不再是 optionality 偶然放行） |
| R15-P2-01(P2) | R16 包补齐三个最终文件（归档字节非 diff）：`collector/jobs/reconcile_turnover_chain.py`、`collector/tests/test_core.py`、`web/public/data/daily/2026/2026-07-17.json`（revision 8）；随包请求 R15-N01 一并裁定闭环 |
| R15-P3-01(P3) | ci.yml 新增独立 step `pytest -q tools/acceptance/test_accept.py` |

## 计数更正（R15 §6.8）

R15 送审正文"v4 13 条"系笔误：diff 实际 10 条（Fix Notes 亦写 10 条，正文数字错）。本轮后 v4 测试共 **21 条**（10 存量 + 11 新增，含 R15 §18 B 列出的全部负向场景）。

## 验证证据（2026-08-22，win32 本机）

- pytest 全量 **291 passed + 1 skipped**（R15 后 278 → 净增 13：门禁回归 2 + v4 负向 11）；
- `tools/deploy/test_verify_archive_sync.sh` 4/4 PASS；vue-tsc 通过；
- acceptance：07-17 范本日与 08-20 当前生产日均 9 模块全 PASS（08-20 走 3.0 版本分支显式合法通过）。

## 请复核要点

1. R15 四项 NOT_CLOSED 逐项裁定（R13-P2-01 / R14-P2-01 / R15-P2-01+R15-N01 / R15-P3-01）；
2. 因果门禁语义：前向峰值只由完整日抬高是否有新边界漏洞；
3. v4 穷举矩阵 + strict_v42 版本分支是否闭合 R15 §15 列出的 9 项失配；
4. 08-20 生产日（3.0 形态）经版本分支合法 PASS 是否符合预期契约。

## 输出契约

- 正文 ≤300 字概要：本轮结论（收敛/HOLD）、4+1 项裁定一行汇总、新增问题 P1/P2/P3 数量、主要新问题编号+一句话。
- 详细审核内容整理为一份完整 Markdown 文档作为附件提供下载，命名 SMI_R16_Review_Report.md；不在正文粘贴大段代码。
- 若无新 NOT_CLOSED，请按迭代纪律写明"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。

附件：SMI_R16_source_20260822.zip（R15 §18 A~D 最小复送 + N01 三最终文件 + 支撑测试/脚本 + 数据样本 + work 三份文档 + 累计 diff 0e2cfbf..a3a706c）。
