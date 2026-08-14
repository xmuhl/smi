# SMI R6 送审：方案最优性评审 + 每日完整数据目标

- 送审日期：2026-08-14
- 送审范围：最新代码（含 R6 多源降级改动）+ 数据快照 + 方案讨论
- 请求：评审当前方案是否为最优，并给出实现"每日完整 9 模块数据"的路径

## 一、项目目标

A股收盘全景 Web 看板：**每个交易日收盘后自动生成当日完整快照（9 大模块）**，支持历史回查。
07-17 基线为手工 Excel 导入的完整范本（LEGACY_EXCEL_IMPORT，9 模块全部 FINAL，含 4 个赛道评分）；
此后自动链路一直未产出同等完整度的快照。

## 二、当前架构（V1.1 + R6）

GitHub Actions（唯一数据/发布权威，cron 16:23 UTC+8）
  └─ close_snapshot.py（Python + AKShare 1.18.88）
       ├─ marketIndex  东财→腾讯→新浪 三级降级（国证 CNINDEX→腾讯→新浪）
       ├─ turnover     东财 spot → 新浪全市场 spot（口径过滤沪/深）
       ├─ sentiment    东财 spot → 新浪 spot；涨停/跌停/炸板池=东财独有
       ├─ sectorPerformance  东财独有（行业/概念板块 TOP5）
       ├─ fundFlow    东财独有（主力资金流）
       ├─ northbound  HKEX 官方季度持仓（QUARTERLY_ONLY）
       ├─ margin      SSE+SZSE 官方（T+1 披露，t1-reconcile 次日补）
       ├─ tracks      占位（UNAVAILABLE，真实采集器未实现）
       └─ summary     规则引擎
  └─ 校验通过 → 写 JSON 快照 → commit/push → build → wrangler pages deploy
Cloudflare Pages：https://smi-6s2.pages.dev/

## 三、R6 本轮改动（已本地验证并部署）

1. 新增 collector/adapters/sources.py：真正消费 config/sources.yaml 的 primary/fallback（R5-P2-01 落地）；
2. market_index/turnover/sentiment 接入多源降级（腾讯/新浪源已实测可用，含当日数据）；
3. close_snapshot 增加任务级有限重试（可重试错误退避 4 次：+2/+5/+10min，--no-retry 测试开关）；
4. pytest 21/21 通过；
5. 2026-08-14 快照成功生成并部署（指数走 TENCENT、成交额/情绪走 SINA）。

## 四、用户实测发现的两个问题

### 问题 1：历史数据缺失
- 现状：availableDates 只有 [2026-07-17, 2026-08-14]，中间所有交易日无数据；
- 根因：V1 采集器口径为"仅当日"——历史日期模块直接返回 UNAVAILABLE（HISTORICAL_*_NOT_SUPPORTED）；
  manual_backfill 对历史日期也无法补全（同样受限于模块口径）；
- 用户期望：每天都有一份完整快照，历史可回查。

### 问题 2：当日数据不完整（vs 07-17 范本）
- 08-14 快照：指数/成交额/情绪/北向 FINAL；板块、资金流 ERROR（东财 push2* 封禁中，无降级源）；
  两融 PENDING（T+1 预期）；tracks UNAVAILABLE（占位）；
- 07-17 范本：9 模块全部 FINAL（含板块 TOP5、资金流 TOP10、两融、4 赛道评分）；
- 用户期望：每天都像 07-17 一样完整。

## 五、候选替代方案评估（用户提出）

| 仓库 | 活跃度 | 数据源 | 结论 |
|---|---|---|---|
| akfamily/akshare | 22k★，2026-08-13 更新 | 东财/新浪/腾讯/国证等 | 现方案基石，保留；问题在源不在库 |
| DannyWongIsAvailable/real-time-stock-mcp-service | 53★，2026-07-06 | 东财+雪球爬虫（需浏览器 Cookie） | 不能替代：与东财同风险、Cookie 过期维护、交互式 MCP 不适合 cron 批处理、禁商用 |
| 24mlight/a-share-mcp-is-just-i-need | 646★，2025-12-25 停更 | Baostock | 不能替代：Baostock 缺涨停池/资金流/板块实时/北向/两融，与 9 模块需求错配；交互式 MCP |
| 腾讯/新浪直连 | - | 已验证可用 | 已接入为降级源（指数/全市场 spot） |
| Baostock 库（非 MCP 包装） | - | 日K/财务/宏观 | 仅可作为指数日K的备用源，覆盖不了资金流等模块 |
| Tushare | 活跃 | 积分制 | 需积分/付费，部分接口有门槛，未采用 |

## 六、请评审的核心问题（Q1-Q4）

1. Q1：当前方案（AKShare 多源降级 + GitHub Actions 单一权威 + Pages）是否为满足"每日完整快照"目标的最优方案？有无更优替代（数据源、执行环境、架构层面）？
2. Q2："每日 9 模块完整"目标下，板块行情、主力资金流这两个东财独有模块的正确姿势是什么？（新浪/腾讯口径漂移 vs 等待东财恢复 vs 其他源？）
3. Q3：历史数据补全策略是否合理？（方案：未来每日自动积累 + 对缺失历史日期用可降级模块补跑，东财独有模块标注缺失）
4. Q4：tracks（赛道指标）真实采集器是否应在 V1 实现？若应实现，最小可行数据源组合是什么？

## 七、附送审包内容

- collector/（含 R6 改动与测试）
- config/、web/（含 07-17、08-14 快照数据）、.github/workflows/、pyproject.toml、README.md
- 数据快照：web/public/data/daily/2026/2026-07-17.json（Legacy 完整范本）、2026-08-14.json（R6 降级快照）
- manifest.json / status.json / latest.json
