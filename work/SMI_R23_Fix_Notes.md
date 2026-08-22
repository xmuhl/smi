# SMI R23 修复说明（R22-P2-01/02/03 + R22-P3-01 · 范本严格口径收敛）

## 0. 本轮定位

R22 裁定 HOLD：R22-DEF-01 CLOSED，但假设清单 A1/A2/A4/A5 全部升级为正式问题。
本轮按 R22 §12 建议顺序修复全部四项（HEAD=d77cdd7，configVersion 3.3→3.4）。

## 1. R22-P2-02（第一优先）：入池去净流入硬门

- `_entry_ok()` 与 `select_candidate_boards()` 改为**仅排名准入**（R22 §4.4
  推荐语义）；`requirePositiveInflow` 配置项删除。
- 净流入只参与：资金维度评分（25% 权重）、评级、风险提示。
- 回归锚点：test_r13_p2_01_entry_needs_two_of_three_days（医药生物全程
  净流出仍入池）+ test_select_candidates_rank_only_filter（净流出板块入选）。

## 2. R22-P2-01（第二优先）：两层资格模型

- 准入阈值 poolSize=8 → **entryRankMax=5**（严格等于范本"近5日成交额全市场前5"）；
  防抖不再通过放宽入池实现，由观察保留层承担。
- 输出分层（`items[].poolQualification`，验收标准 v4 字段契约新增 enum）：
  - `QUALIFIED_TODAY`：turnoverRank ≤ 5（当日范本资格，"当日入选"）；
  - `RETAINED_OBSERVATION`：曾入选、rank∈(5, exitRankMax=12]、未满出池
    确认（迟滞观察保留）。
- 出池规则不变（连续 2 日 rank>12），grandfather 承继不变。
- 前端：板块名列"观察保留"徽标（title 说明迟滞语义），rank 10 留池项与
  rank 3 当日入选不再等价呈现。
- 回归：test_r23_p2_01_two_layer_qualification（分层断言+承继出池对照）。

## 3. R22-P2-03（第三优先）：概念/复合赛道跨 taxonomy 可比资格

数据源探测结论（R22 §7 要求明确产品范围）：
- THS 概念汇总（stock_board_concept_summary_ths）：仅热门 50 概念，无
  成交额/净流入——不可作 universe；
- 东财 push2 概念现货/资金流（push2.eastmoney.com）：代理与直连均不可达
  （已知 push2 封禁边界族，同 fundFlow）；
- **THS 概念指数（stock_board_concept_index_ths）**：单概念全历史
  收盘/成交量/**成交额**（元），与行业汇总同源同单位 → 可比资格可行。

实施（`_concept_qualification_injection`）：
- `board_type=concept` 的赛道（高股息中特估→同花顺中特估100，boardCode
  改 309062 → 归档去重键变更 → archive_raw 自动重补同源序列）以
  **close 归档成交额（元/1e8→亿）注入行业 universe 联合排名**；
- 注入仅限**行业 universe 已有日期**（证据日上参与排名）——close 更早
  历史不扩展证据日历（否则 close-only 历史日会成为低完整性"证据日"，
  行业成员缺行误计出池 streak；玩具门限下已复现并回归覆盖）；
- 注入行不带净流入/涨跌家数（概念指数无此口径，评分层诚实缺口；
  资金流本就不参与资格判定）；
- 复合赛道（半导体/AI算力）：**资格按行业主腿（半导体）参与行业口径
  排名，评分按复合结构**——R22 指出的"选池身份与评分身份不一致"由
  隐式行为升级为显式产品规则（tracks.yaml qualification 配置文档化）；
- 概念腿由此获得市场名次并随状态机统一出入池，**不再永久剔除**；
  无 close 归档的概念腿仍 fail-closed + errors 披露（不变）。

## 4. R22-P3-01：空表文案语义分层

前端 emptyText 两分支：
- UNAVAILABLE →"上游赛道数据暂不可用（板块快照缺失或未过完整性校验），
  无法判断当日主线"；
- 数据完整但无合格板块 →"今日暂无符合筛选条件的主赛道（近5日成交额
  全市场前5）"。

## 5. 版本与验收

- configVersion 3.4（effectiveFrom 2026-07-20 不变）；schedule 历史白名单
  +3.4、cutoff(≥08-21) minConfigVersion → 3.4；
- 验收标准 items 字段新增 `poolQualification`（enum，optional；UNAVAILABLE
  空池日与 legacy 参照日可缺省）；
- 测试 310 绿（collector 247+1skip + acceptance 63）：重写准入确认
  （排名驱动）/候选发现（仅排名）/双阈值→两层资格用例；新增概念注入
  端到端（850亿/日概念腿联合排名第2、QUALIFIED_TODAY、unmapped 披露
  消失）与两层资格分层用例；前端构建绿。

## 6. 数据终态（2026-08-23，HEAD=0ce27c5）

- 概念腿归档补全：同花顺中特估100 全历史 154 日（2026-01-05..08-21，
  THS 概念指数，元）入档（e402381）；
- 08-20（3.4/SUFFICIENT/80.5/7 项）：
  - QUALIFIED_TODAY：半导体① 通信设备② 高股息中特估③（概念口径
    联合排名）元件④ 化学制药⑤
  - RETAINED_OBSERVATION：电力(25)·医药生物(20)——承继宽限 streak=1
  - unmapped 披露清零
- 08-21（3.4/DEGRADED/76.4/5 项）：**联合排名精确前5** = 半导体①
  通信设备② 元件③ 高股息中特估④ 化学制药⑤；电力(25)/医药生物(20)
  连续 2 日 >12 出池；医疗服务⑥因准入前5口径未入池（R23-P2-02 修除
  净流入门槛后元件③回归的直接对照）
- 契约微调（0ce27c5）：items.mainNetInflow 声明改 optional + 正式项
  条件必填（代码层，同 redStockRatio 模式）——概念腿 INSUFFICIENT 项
  资金流诚实缺列合法
- acceptance --all：**PASS=3（07-17、08-20、08-21）**；测试全绿
  （collector 247+1skip + acceptance 63）；CI 绿（d77cdd7/e402381/0ce27c5）

## 7. 请复核要点

1. R22-P2-01/02/03/P3-01 四项裁定：CLOSED / NOT_CLOSED；
2. 概念联合排名的口径决策：概念指数成交额（THS 同源）插入行业 universe
   分布重排——是否满足"跨 taxonomy 可比资格"要求；
3. 复合赛道"资格按行业主腿/评分按复合"显式规则是否可接受为产品规则；
4. 新问题按 P1/P2/P3 分级。
