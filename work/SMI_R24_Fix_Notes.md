# SMI R24 修复说明（R23 裁定收口 · 3.5）

## 1. R22-P2-01 收口（R23 §4.5 最简语义）

- **当日前5直接入池**：`QUALIFIED_TODAY` = 今日 rank≤entryRankMax(5) 的每日
  范本真理源，**无 2/3 确认门槛**（entryWindowDays/entryMinDays 入池确认
  语义退役，配置键保留仅为兼容诊断）；
- 每日监测表 = 当日前5 ∪ 观察保留（历史池成员 rank>5 未满出池确认）；
- 防抖完全由出池确认承担（连续 2 日 >12），语义不变；
- 回归：test_r24_entry_direct_top5_no_confirmation（单日翻至第4立即入选；
  D2 直入后跌至第6 → 观察保留，分层断言）。

## 2. R22-P2-03 收口（B1 方案 B + B2 显式化）

- **口径改名（方案 B）**：UI 空表文案与所有文档改称"监测口径前5
  （行业板块全景 + 已配置概念赛道联合排名）"，不再自称"全市场前5"；
  完整概念 universe（方案 A）列为产品增强决策，未实施（375 概念逐日
  采集 + taxonomy 去重规则属产品级工作量，超出本轮）；
- **复合赛道显式资格腿（B2）**：tracks.yaml 新增
  `qualification: {taxonomy: industry, boardCode: BK1036, legName: 半导体}`；
  选池只认显式 leg（不在 descs → fail-closed 剔除），不再名称模糊命中；
  power/healthcare 显式 `taxonomy: industry`；
- **rankScope 元数据**：items 新增三分枚举
  INDUSTRY_UNIVERSE / CONCEPT_INJECTED / INDUSTRY_LEG——主腿排名
  不得误称复合合成排名，注入排名不得误称全市场排名。

## 3. R23-P3-01 收口

- acceptance 代码层条件必填（版本守卫）：
  - cfg≥3.4：正式项 poolQualification ∈ {QUALIFIED_TODAY,
    RETAINED_OBSERVATION} 必填（删除字段即 FAIL）；
  - cfg≥3.5：正式项 rankScope 三枚举必填；
  - legacy/3.0-3.3 存量豁免（按当期契约验收原则）。

## 4. 版本与验证

- configVersion 3.5；schedule 白名单 +3.5、cutoff minConfigVersion 3.5；
- 测试 311 绿（collector 248+1skip + acceptance 63；新增直入/分层/
  rankScope 用例，旧 2/3 确认用例退役重写）；前端构建绿；CI 绿
  （58e89c1）；
- 08-20/21 重生成（--replace-modules=tracks）：
  - 08-20（SUFFICIENT/80.5/7）：前5 QUALIFIED（半导体①[INDUSTRY_LEG]
    通信②[INDUSTRY_UNIVERSE] 高股息③[CONCEPT_INJECTED] 元件④ 化学⑤）
    + 电力(25)/医药生物(20) 观察保留；
  - 08-21（DEGRADED/76.4/5）：**当日监测口径前5** = 半导体① 通信②
    元件③ 高股息④ 化学制药⑤（电力/医药连续 2 日>12 出池）；
- acceptance --all：PASS=3（07-17、08-20、08-21）。

## 5. 本轮新决策假设（请继续挑战）

- C1 出池确认（连续2日>12）与当日前5直接入池并存——某板块单日暴跌
  出前5但未满 2 日 → 观察保留（表内）；第 2 日仍>12 → 出池。边界：
  前一日前5、后一日 rank 13 → 单日观察保留即消失于"当日资格"但保留
  在表——是否符合产品预期？
- C2 方案 A（完整概念 universe 联合排名）作为后续增强的产品决策点，
  本轮以方案 B 改名合规——是否可接受为收敛状态？

## 6. 请复核要点

1. R22-P2-01/P2-03、R23-P3-01 裁定：CLOSED / NOT_CLOSED；
2. C1/C2 假设评估；
3. 若无新 NOT_CLOSED，请写明"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
