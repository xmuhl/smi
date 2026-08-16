# SMI R12 P0.5 复审：P03-001 唯一剩余项收口

- 轮次：R12 P0.5（对 R12 P0.4 HOLD 的第五修订轮；P0.4 已裁决 P0-003/007/008 全部 CLOSED）
- 送审输入 commit：99dc2a9（基线报告 ece8874 之后顺序提交；报告另行提交）
- 前置复核链：…→ P0.4（HOLD，仅 P3：P03-001）→ 本轮

## 一、本轮唯一改动

P03-001 评审要求 turnover.unit 与 margin.unit **两条**删除 mutation，上轮只覆盖 turnover。本轮补齐：

- 新增 test_p04_unit_deleted_margin_invariant：删除 08-14 快照 margin.unit → INV-UNIT-亿元 必须 false；
- 测试总数 29 → 30（tools/acceptance/test_accept.py 30/30 全绿）；
- 07-17 验收 PASS（9/9 模块 + 9/9 不变量）不变。

## 二、请复核

1. P03-001 是否可判 CLOSED；
2. 若收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
