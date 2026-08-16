# SMI R12 P0 送审：范本验收标准与基线报告（"任意日期 = 范本 07-17 效果"）

- 送审轮次：R12 P0（本轮大升级的第 0 阶段：验收基线与自动化验收平台）
- 送审日期：2026-08-16 之后
- 送审范围：新增的验收标准、验收器代码与 21 日基线跑分；**本阶段未改任何采集/前端代码**
- 仓库：github.com/xmuhl/smi，分支 feat/p0-acceptance-baseline（commit 3306ba7）

## 一、背景与总目标（用户本轮新要求）

用户要求对 SMI（A股收盘全景 Web 看板）做全面修订升级，最终验收标准是：
**指定任意历史日期（包括之后每日更新出的新日期），网页上显示的数据内容都要达到范本
《A股收盘全景_20260717.xlsx》（2026-07-17）的数据效果**；自动验收不达标时允许回退
并重新研究新方案（用户已授权自主决策）。

范本 07-17 的 9 个 sheet = 网页 9 大模块：宽基指数 / 两市成交量 / 市场情绪 / 板块行情 /
主力资金流向 / 北向资金 / 两融 / 主赛道监测（4 赛道×16 列） / 综合总结（五段式+风险提示）。
07-17 当日快照为 Legacy Excel 导入，9/9 模块 FINAL，是目前唯一达到范本效果的日期。

## 二、P0 阶段交付物

1. `docs/acceptance/template-standard.json`：机器可读《范本验收标准》——每模块的 xlsx 列、
   快照必检字段、item 必检字段、最小行数、口径注意事项；
2. `docs/acceptance/template-standard.md`：人类可读版；
3. `tools/acceptance/accept.py`：数据侧自动验收器（纯标准库）——
   对任一日期执行 validate_snapshot + 9 模块规则校验，输出 PASS/FAIL 与逐项缺口；
4. `work/acceptance/baseline-report.json`：21 个交易日基线跑分报告。

## 三、验收器逐模块规则（请重点复核）

| 模块 | 规则要点 |
|---|---|
| marketIndex | FINAL；≥6 项；必需代码 000001/399001/399006/000688/000300/899050 的 close、changePct 有限 |
| turnover | FINAL；turnoverToday 有限；非 Legacy 日期 turnoverPrevious/Delta/ChangePct 必须有限、volumeState ∈ 放量/缩量/平量；Legacy 仅要求 today 有限 |
| sentiment | FINAL；涨/跌/平家数、非ST涨停、ST涨停、非ST跌停有限；涨+跌+平 ≥4000；brokenLimitCount 有限或 null |
| sectorPerformance | FINAL；行业/概念 涨幅前5+跌幅前5 各 ≥5 项，name+changePct 有效 |
| fundFlow | FINAL；行业/概念/个股 流入+流出 TOP10 各 ≥10 项，name+netInflowYi 有效 |
| northbound | Legacy：legacyImportedFields 三项净流入有限 → PASS；非 Legacy：quarterlyHolding.status=FINAL 且 items 非空（真实季度持仓）且 mode 含 POST_20240819 → PASS；否则 FAIL |
| margin | FINAL 且三项余额有限 → PASS；PENDING + 带 latestPublishedReference + 日期==latestCapturedDate → PASS（D0 规则）；其余 FAIL |
| tracks | FINAL；≥4 赛道；每行 16 个字段（trackId…decision）齐全；mainNetInflow 有限；score/decision 非空 |
| summary | FINAL；8 个总结段（指数量能/情绪/资金流/赛道/市场环境/北向/两融/风险提示）均为 ≥10 字中文 |

## 四、基线跑分结果（21 个交易日）

- **PASS：1 个** —— 2026-07-17（范本，9/9 FINAL）
- **FAIL：20 个**，分布：
  - 2026-08-14（最新采集日）：8/9 通过，仅 tracks UNAVAILABLE（TRACK_METRICS_COLLECTOR_NOT_IMPLEMENTED）
  - 2026-07-20：turnover（跨口径 MISMATCH，详见 Q2）+ sentiment/sectors/fundFlow/northbound/tracks 缺口
  - 2026-07-21~08-13（18 日）：marketIndex/turnover/margin/summary 通过；
    sentiment（07-27 起 PARTIAL=东财涨停池历史窗口内、之前 UNAVAILABLE）、
    sectorPerformance（HISTORICAL_BOARD_RANK_NOT_SUPPORTED）、
    fundFlow（HISTORICAL_TODAY_RANK_NOT_SUPPORTED）、
    northbound（季度占位无真实数据）、tracks（未实现）未达标

各模块失败日期数：tracks 20；sentiment/sectorPerformance/fundFlow/northbound 各 19；
turnover 1；marketIndex/margin/summary 0。

## 五、请评审的口径问题

### Q1：北向资金——官方日度披露已停发，如何"达到范本效果"？
- 事实：北向资金日度净流入自 2024-08-19 起官方停止披露；07-17 范本的日度数字来自手工
  Excel（TONGDAXIN_LEGACY，legacyImportedFields），不可复现于其他日期；
- 现状：08-14 有真实 HKEX 季度持仓（asOf 2026-06-30，items 非空，FINAL）；历史回补日
  只有占位（UNAVAILABLE）；
- 拟定方案：**所有 POST_20240819 日期统一展示"最近官方季度持仓（截至 2026-06-30）+ 日度
  披露已停发"的诚实标注**，历史日不再逐日区分；验收规则=季度持仓 FINAL+非空即 PASS；
- 问题：该口径是否满足"达到范本数据效果"（页面有真实数据内容、无空态、口径诚实）？
  有无更好的免费替代（如官方其他披露、估算源），或应维持逐日 UNAVAILABLE 并在验收标准
  中豁免该模块？

### Q2：成交额 07-20 跨口径比较（当前 FAIL 的根源之一）
- 事实：07-17 范本 turnoverToday=26549.58（LEGACY_UNKNOWN 口径），07-20 为官方
  沪深A股口径 27037.72（SH_SZ_A_NO_B_NO_BJ_V1）；因前一日口径不同，reconcile 链判定
  comparisonStatus=PREVIOUS_METHOD_MISMATCH，不计算增减/幅度，导致验收 FAIL；
- 拟定方案候选：a) 维持 MISMATCH 不环比，并在验收标准中将 07-20 例外化；
  b) 允许跨口径比较（26549.58→27037.72，+1.84%）并在页面标注"跨口径比较（Legacy→官方）"；
- 问题：为满足"任意日期页面都像范本一样显示前日/增减/幅度"，哪个方案更符合数据诚实原则？

### Q3：情绪指标 Legacy 字段重复的验收处理
- 事实：07-17 范本快照 stLimitUpCount 与 nonStLimitUpCount 均为 25（xlsx 实为 ST涨停10），
  stLimitDownCount 与 nonStLimitDownCount 均为 180（xlsx 实为 ST跌停32），系 Legacy 导入
  字段重复；验收器要求各计数有限即可，不纠正数值；
- 问题：验收器该"仅验有限性"还是"按 xlsx 校正后再验"？该重复是否需要在页面侧修正展示？

### Q4：tracks 16 列验收标准的免费路线可行性
- 事实：范本 tracks 为 4 赛道×16 列（成交额排名/主力净流入/连续流入天数/多头排列/RPS60/
  跑赢沪深300/涨停家数/连板梯队/红盘占比/催化逻辑/业绩兑现/综合达标率/最终判定等）；
  已建成的 daily raw archive（THS 板块历史指数、东财涨停池历史窗口、THS 当日资金流、
  板块成分快照）可支撑其中大部分指标；催化/业绩兑现为 config 定性列；
- 问题：验收要求"16 字段齐全 + score/decision 非空"是否合理？免费数据下哪些指标只能
  从上线日起积累、哪些历史窗口受限（如涨停池仅 07-27 起），验收标准应如何表述才既严格
  又不把不可达目标写成硬门禁？

### Q5：验收器规则本身的完备性
- 是否有遗漏（如 summary 五段内容质量、板块口径一致性、单位）、过严（如 fundFlow 六类
  TOP10 是否必须全部、概念板块是否必须）、过松（如 tracks 字段存在但内容为空占位）之处？

## 六、后续阶段计划（供上下文，无需逐项评审）

- P1 采集器修订：margin Length-mismatch bug、板块历史（THS 板块历史指数）、情绪历史源
  研究、资金流历史源研究（问财/THS/备用域）、北向季度口径落地 → 历史 19 日回补；
- P2 tracks 采集器（消费 archive）+ 前端赛道表对齐范本 16 列；
- P3 前端 9 面板对齐范本 + 每日链路（close_snapshot→archive-raw→t1-reconcile→build→deploy）
  硬化 + 验收器接入每日更新门禁；
- P4 全量自动验收（含页面侧 headless 验收）→ 不达标回退重研（上限 2 循环）→ 上线。

## 七、附：关键事实数据（供复核引用）

- 线上：Cloudflare Pages 双域名（smi-6s2.pages.dev / smi.gorestart.cn）；
- manifest 三指针：latestCapturedDate=2026-08-14、latestCloseCompleteDate=2026-07-17、
  latestFinalDate=2026-07-17；
- status.json：health=DEGRADED，margin 模块 errors 含
  "Length mismatch: Expected axis has 0 elements, new values have 13 elements"（P1 修）；
- 07-17 范本要点：6 指数（上证3764.15 -3.05% 等）、成交额 26549.58 亿（前日 24035.65）、
  情绪（涨482/跌5001/平40/涨停35/跌停212/炸板45）、行业涨前5（电力+1.85%等）、
  主力净流入TOP10（电力58.62 等）、北向合计 -156.32（沪-68.54/深-87.78）、
  两融总余额 28139.01 亿、4 赛道（高股息中特估90分/电力80分/医药10分/半导体5分）。
