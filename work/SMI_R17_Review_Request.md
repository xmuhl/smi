# SMI R17 送审请求（R16 修复包复核 · 迭代收敛轮）

R16 结论 HOLD：R15 四项全部 CLOSED（R13-P2-01 / R14-P2-01 / R15-P2-01+R15-N01 / R15-P3-01），唯一新增 R16-P2-01（P2：旧版本兼容只信任快照自报 configVersion，无权威时间边界）。本轮送审该项修复（main HEAD=见下，基线链 0e2cfbf→ebac337→a3a706c→本轮），请裁定 CLOSED 与否；若无新 NOT_CLOSED，请按迭代纪律写明收敛。

## 修复对照（完整版见附件 work/SMI_R17_Fix_Notes.md）

按 R16 §5.6 建议实现权威版本时间表：

| 项 | 内容 |
|---|---|
| 标准 | template-standard.json tracks spec 新增 tracksVersionSchedule：through=2026-08-20（allowedConfigVersions=[legacy,1.0,2.0,3.0,3.1,3.2]——历史实际版本全集）；from=2026-08-21（minConfigVersion=3.2，3.2 代码 ebac337 之后首个可产数据交易日为 cutoff） |
| 验收器 | accept.py 矩阵块 1b：按 trade_date 匹配时间表；窗口内不在白名单 FAIL；cutoff 后低于 minConfigVersion FAIL（"版本降级旁路"）；非数值版本由白名单裁决 |
| 测试 | 负向 2 条：2026-08-24 自报 3.0 → FAIL；2026-08-19 自报 "9.9" 不在白名单 → FAIL。正例修正：3.0 存量形态合法 PASS 的日期改为真实 2026-08-20（原测试误用 08-21——该日在 cutoff 后，自报 3.0 现在必须 FAIL） |

## 验证证据（2026-08-22）

- pytest 全量 293 passed + 1 skipped（R16 后 291 净增 2）；
- acceptance --all：PASS=2（07-17、08-20）不变，08-20 3.0 经 through 规则合法 PASS 行为保持；
- shell 自测 4/4；vue-tsc 通过（本轮未触及前端）。

## 请复核要点

1. R16-P2-01 裁定（时间表语义/白名单完备性/cutoff 选择）；
2. 08-20 3.0 历史兼容行为不变；
3. 若无新问题，请写明"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。

## 输出契约

- 正文 ≤300 字概要：本轮结论、裁定汇总、新增问题数量；
- 详细内容整理为 SMI_R17_Review_Report.md 附件下载；
- 若收敛，正文只需状态结论。

附件：SMI_R17_source_20260822.zip（R16 §12 最小复送：template-standard.json / accept.py / test_accept.py + work 文档 + 累计 diff）。
