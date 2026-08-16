# 《范本验收标准》 template-standard

> 参照范本：**2026-07-17**（Excel `A股收盘全景_20260717.xlsx` 与当日网站数据快照 `web/public/data/daily/2026/2026-07-17.json`）。
> 用途：供后续自动化验收器逐日期比对。机器可读版见同目录 `template-standard.json`。

- version: 1
- referenceDate: 2026-07-17
- referenceXlsx: A股收盘全景_20260717.xlsx
- referenceSnapshot: web/public/data/daily/2026/2026-07-17.json
- 通用约束：除备注明确允许外，各模块 `requiredStatus` 均为 FINAL；数值一律取自范本，不得编造。

---

## 1. marketIndex — 宽基指数收盘数据

- **面板**：`MarketIndexPanel.vue`　**XLSX sheet**：`1-宽基指数收盘数据`
- **XLSX 列**：指数名称 / 收盘点位 / 当日涨跌幅
- **快照顶层字段**：items、dataDate、source、status
- **items 每项字段**：code、name、close、changePct（另含 previousClose、source）
- **最小行数**：6
- **口径注意**：
  - 快照 items 每项必含 code/name/close/changePct，代码以快照为准。
  - 最小 6 项：上证(000001)、深证(399001)、创业板(399006)、科创50(000688)、沪深300(000300)、北证50(899050)。
  - 范本 07-17 快照实际有 **8 项**，另含国证1000(399311)、国证2000(399303)，并对应 xlsx 中的科创综合等扩展项。
  - previousClose 均为 null（Legacy 导入，属预期）。

## 2. turnover — 两市成交量

- **面板**：`TurnoverPanel.vue`　**XLSX sheet**：`2-两市成交量`
- **XLSX 列**：当日两市合计成交额 / 前一交易日成交额 / 成交额增减金额 / 成交变化幅度 / 量能定性
- **快照顶层字段**：turnoverToday、turnoverPrevious、turnoverDelta、turnoverChangePct、volumeState
- **最小行数**：无（无 items 列表）
- **口径注意**：
  - 当日为 FINAL 时，turnoverToday / turnoverDelta / turnoverChangePct 必须为有限数值（非 null）。
  - **例外**：范本 07-17 为 `TONGDAXIN_LEGACY` 导入，previousMethod=LEGACY_UNKNOWN、volumeState=UNKNOWN、turnoverPrevious / turnoverDelta / turnoverChangePct 均为 null，comparisonStatus=PREVIOUS_UNAVAILABLE。此例外仅适用于 Legacy 日，非 Legacy 日期不得为 null。
  - unit：亿元。

## 3. sentiment — 市场情绪指标

- **面板**：`SentimentPanel.vue`　**XLSX sheet**：`3-市场情绪指标`
- **XLSX 列**：全市场上涨家数 / 全市场下跌家数 / 平盘家数 / 非ST涨停数量 / ST涨停数量 / 非ST跌停数量 / ST跌停数量 / 炸板数量 / 涨停封板率 / 市场最高连板高度
- **快照顶层字段**：riseCount、fallCount、flatCount、nonStLimitUpCount、stLimitUpCount、nonStLimitDownCount、stLimitDownCount、brokenLimitCount
- **最小行数**：无（无 items 列表）
- **口径注意**：
  - 范本快照 `stLimitUpCount` 与 `nonStLimitUpCount` 均为 25、`stLimitDownCount` 与 `nonStLimitDownCount` 均为 180 —— 这是 Legacy 导入时字段重复产生的伪值。
  - **以 XLSX 为准**：非ST涨停 25 / ST涨停 10 / 非ST跌停 180 / ST跌停 32。验收时应识别重复并按 XLSX 校正。
  - 封板率(43.75%)、最高连板高度(2连板)仅存在于 XLSX，快照未展开。

## 4. sectorPerformance — 板块行情表现

- **面板**：`SectorPanel.vue`　**XLSX sheet**：`4-板块行情表现`
- **XLSX 列**：一、通达信行业板块-涨幅前5 / 跌幅前5；二、通达信概念板块-涨幅前5 / 跌幅前5
- **快照顶层字段**：industryTop5、industryBottom5、conceptTop5、conceptBottom5
- **每项字段**：name、changePct
- **最小行数**：5（每类）
- **口径注意**：
  - method=TONGDAXIN_LEGACY，页脚展示“数据口径：通达信 Legacy（历史导入）”。
  - 页面提供行业/概念双 Tab，每 Tab 渲染涨幅榜 TOP5 与跌幅榜 TOP5。

## 5. fundFlow — 主力资金流向

- **面板**：`FundFlowPanel.vue`　**XLSX sheet**：`5-主力资金流向`
- **XLSX 列**：一、行业板块-主力净流入TOP10/净流出TOP10；二、概念板块 TOP10；三、个股 TOP10（大单+特大单）
- **快照顶层字段**：industryInflowTop10、industryOutflowTop10、conceptInflowTop10、conceptOutflowTop10、stockInflowTop10、stockOutflowTop10
- **每项字段**：name、netInflowYi
- **最小行数**：10（每类）
- **口径注意**：
  - 口径：大单+特大单（通达信标准），单位亿元。
  - 净流出项 netInflowYi 为负值；页面按 行业/概念/个股 三 Tab，各渲染 净流入TOP10 与 净流出TOP10。

## 6. northbound — 北向资金数据

- **面板**：`NorthboundPanel.vue`　**XLSX sheet**：`6-北向资金数据`
- **XLSX 列**：一、北向资金整体流向（合计/沪股通/深股通净流入）；二、北向净买入TOP10/净卖出TOP10；三、主力&北向资金重合个股（同步流入/同步流出）
- **快照顶层字段**：legacyNetFlow、legacyImportedFields、dailyTurnover、quarterlyHolding
- **最小行数**：无
- **口径注意**（重要）：
  - 官方日度披露自 **2024-08-19 起停止**。
  - 范本为 Legacy 导入（mode=POST_20240819_LEGACY_IMPORTED）：dailyTurnover / quarterlyHolding / legacyNetFlow 均 UNAVAILABLE，真实数值在 `legacyImportedFields`（totalNetInflow=-156.32 / shanghaiNetInflow=-68.54 / shenzhenNetInflow=-87.78 / netBuyTop10 / netSellTop10 / sameDirectionIn / sameDirectionOut），且 excludeFromOfficialTimeSeries / excludeFromTrackScoring 均为 true。
  - **非 Legacy 日期**页面必须展示“最近官方披露（季度持仓）+ 日度已停发”的诚实标注（POST_20240819_QUARTERLY_ONLY），**不得伪造日度数字**。

## 7. margin — 两融数据

- **面板**：`MarginPanel.vue`　**XLSX sheet**：`7-两融数据`
- **XLSX 列**：融资余额（亿元）/ 融券余额（亿元）/ 两融总余额（亿元）/ 较前一交易日余额变动（亿元）/ 融资净买入（亿元）/ 融券净卖出（亿元）
- **快照顶层字段**：financingBalance、securitiesLendingBalance、marginBalance、marginBalanceChange、financingNetBuyAmount、legacySecuritiesLendingNetSellAmount
- **最小行数**：无
- **口径注意**：
  - 交易所 **T+1 披露**：当日快照允许 status=PENDING 并携带 latestPublishedReference（最近已披露参考值，可能 T-1 或更早回退）；次日 t1-reconcile 后必须 FINAL。
  - 范本为 FINAL（Legacy）：financingBalance=27927.01、securitiesLendingBalance=212.0、marginBalance=28139.01、marginBalanceChange=-442.55、financingNetBuyAmount.value=-450(LEGACY)、legacySecuritiesLendingNetSellAmount.value=7.45(LEGACY)、marginTradeAmount=3902.79、marginTradeSharePct=14.7。
  - FINAL 时 financingBalance / securitiesLendingBalance / marginBalance 必须为有限数值。

## 8. tracks — 主赛道每日监测表

- **面板**：`TrackMonitorPanel.vue`　**XLSX sheet**：`8-主赛道每日监测表`
- **XLSX 列（16 列）**：监测日期 / 板块名称 / 板块定位 / 近5日成交额排名 / 今日主力净流入(亿) / 连续净流入天数 / 5-10-20日多头排列 / 60日RPS数值 / 近10日跑赢沪深300 / 板块涨停家数 / 连板梯队完整度 / 红盘个股占比 / 核心催化逻辑 / 业绩兑现情况 / 综合达标率 / 最终判定
- **快照顶层字段**：items、configVersion、sourceSystem、dataDate、status
- **items 每项字段**：trackId、trackName、positioning、turnoverRank、mainNetInflow、continuousInflowDays、maAlignment、rps60、excessReturn20d、limitUpCount、ladderCompleteness、redStockRatio、coreCatalyst、earningsRealization、score、decision（另含 date、coveragePct）
- **最小行数**：4
- **口径注意**：
  - 需 4 条赛道：高股息_中特估 / 电力_火电_水电 / 医药生物_创新药_CRO / 半导体_CPO_AI算力。
  - 页面只渲染可展示列：赛道/定位/主力净流入/连流入/RPS60/涨停/综合分/判定。
  - xlsx“综合达标率/最终判定”对应快照 score（综合分）与 decision。

## 9. summary — 综合总结

- **面板**：`SummaryPanel.vue`　**XLSX sheet**：`9-综合总结`
- **XLSX 五段**：一、指数与量能总结；二、市场情绪总结；三、资金流向总结；四、赛道监测结论；五、操作建议；风险提示
- **快照顶层字段**：indexAndTurnover、sentiment、fundFlow、trackConclusion、marketEnvironment、northbound、margin、riskWarning
- **最小行数**：无
- **口径注意**：
  - 每段必须为非空中文文本。
  - 范本由 RULE_ENGINE_V1 生成，含 indexAndTurnover / sentiment / fundFlow / margin / trackConclusion / marketEnvironment / northbound / riskWarning。
  - 页面渲染块：指数与量能/市场情绪/资金流向/两融/赛道监测/北向资金/市场环境/风险提示；margin / marketEnvironment / northbound 仅在字段存在时渲染（v-if）。

---

## 附：口径疑点汇总

1. **sentiment**：快照 stLimitUpCount=nonStLimitUpCount=25、stLimitDownCount=nonStLimitDownCount=180，为 Legacy 导入重复；以 XLSX 为准（ST涨停10、ST跌停32）。
2. **turnover**：范本前日/增减/幅度为 null（Legacy 例外），非 Legacy 日必须为有限值。
3. **northbound**：官方日度停发，Legacy 值仅还原报表，页面须诚实标注，不得伪造。
4. **margin**：T+1 披露，PENDING 需 latestPublishedReference，次日须 FINAL。
