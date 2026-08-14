# SMI V1 设计文档 V1.1

**项目名称：** SMI（Stock Market Intelligence）  
**文档名称：** 《SMI V1 设计文档 V1.1》  
**文档版本：** V1.1  
**设计基线日期：** 2026-08-14  
**文档语言：** 中文  
**目标：** 将现有每日生成的《A股收盘全景》Excel（9 大模块）改造成可自动更新、可历史回查、PC/移动端自适应、数据源与托管成本均为 0 的 Web 看板。

---


## 0. V1.1 八项实施确认结论

本节用于直接回答实施方提出的 8 个问题；后续各章节给出完整设计与验收细节。

### 0.1 北向资金自动获取

**结论：V1 只自动获取 2024-08-19 后的“最近一期季度持仓”；日度北向成交额、日度活跃证券、日度净流入/净买入在 V1 自动链路中全部标记 `UNAVAILABLE`。**

可在 GitHub Actions 无浏览器环境中直接 HTTP GET 的官方公开页面：

```text
上海股通北向季度持仓：
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh

深圳股通北向季度持仓：
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz
```

V1 使用 `requests/httpx + pandas.read_html` 或 BeautifulSoup 解析当前页面，至少校验：

- 页面声明的 `Shareholding Date`
- 股票代码
- 股票名称
- `Shareholding in CCASS`
- 持股占已上市交易证券数量比例

HKEX 官方页面当前明确说明：自 2024-08-19 起北向持股信息仅按季度提供，前一季度数据在季末后的第 5 个北向交易日发布；页面只保留可查询范围内的数据。

HKEX 仍提供“Historical Daily”网页：

```text
https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en
```

该网页能展示北向市场成交及活跃证券信息，但当前未发现 HKEX 对公众承诺的、稳定且免费的 CSV/REST 下载契约；页面数据为动态加载。**V1 不把未公开承诺的内部 AJAX 地址写成生产依赖。**

因此 V1 自动 Schema 固定为：

```text
mode = POST_20240819_QUARTERLY_ONLY

dailyTurnover.status       = UNAVAILABLE
activeSecurities.status    = UNAVAILABLE
legacyNetFlow.status       = UNAVAILABLE
overlap.status             = UNAVAILABLE
quarterlyHolding.status    = FINAL / STALE / ERROR
```

页面显示：

> 2024-08-19 起北向日度净买入/净流入不再按旧口径披露；SMI V1 自动版仅展示 HKEX 最近一期季度持仓。日度成交及活跃证券可前往 HKEX Historical Daily 页面人工查询，待未来验证稳定免费机器接口后再接入。

这条边界是 V1.1 的硬约束，不允许开发者用第三方推算值替代官方字段。

### 0.2 两融接口

**结论：截至 V1.1 核验日，AKShare 1.18.88 当前文档仍正式列出并描述以下接口，因此状态定义为 `DOC_VERIFIED`；正式上线前必须在 GitHub Actions Runner 上逐项通过 `RUNNER_VERIFIED` 烟雾测试。**

```text
stock_margin_sse(start_date, end_date)
stock_margin_detail_sse(date)
stock_margin_szse(date)
stock_margin_detail_szse(date)
```

本设计不虚构“本对话已经从 GitHub Runner 实跑成功”。实施验收必须真实调用。

降级顺序：

1. 固定 AKShare 版本重试；
2. 已通过验收的 SSE/SZSE 官方页面 Adapter；
3. 仍失败时保持上一份有效快照，并将目标日期字段置 `ERROR` 或 `STALE`；
4. T 日数据尚未按披露节奏出现时使用 `PENDING`；
5. 禁止用东方财富等第三方字段冒充交易所两融官方口径。

### 0.3 指数接口

**结论：**

- `index_hist_cni` 的 `symbol` 使用纯指数代码，例如 `399303`、`399311`，**不带 `.SZ`**。
- 国证2000：`index_hist_cni(symbol="399303", ...)`
- 国证1000：`index_hist_cni(symbol="399311", ...)`
- 北证50不依赖 `stock_zh_index_spot_em()` 是否恰好包含 899050。
- 北证50 V1 主接口固定为：

```text
stock_zh_index_daily_em(
    symbol="bj899050",
    start_date=YYYYMMDD,
    end_date=YYYYMMDD
)
```

AKShare 当前文档明确说明该历史接口代码前缀支持 `sh`、`sz`、`csi`、`bj`。

若北证50日线接口失败：

```text
Primary   = EASTMONEY_DAILY / bj899050
Fallback  = 已验收的北交所/其他公开指数日线 Adapter
Failure   = ERROR
```

不把未经运行验证的 `stock_zh_index_spot_em()` 覆盖能力作为上线前提。

### 0.4 前端与静态数据目录

**结论：确认采用实施方建议。V1 唯一正式数据目录改为 `web/public/data/`。**

Vite 构建时会将 `public` 目录内容原样复制到构建产物根目录，因此：

```text
web/public/data/manifest.json
                ↓ npm run build
web/dist/data/manifest.json
```

Cloudflare Pages：

```text
Root directory:          web
Build command:           npm ci && npm run build
Build output directory:  dist
Production branch:       main
```

浏览器统一请求：

```text
/web/public/data/manifest.json
/web/public/data/latest.json
/web/public/data/daily/2026/2026-08-13.json
```

V1 不再维护根目录第二份 `data/`，避免双副本漂移。

### 0.5 2026-07-17 Excel 基线导入

**结论：使用现有 2026-07-17 Excel 生成首个 daily JSON；全文件标记 `sourceSystem=TONGDAXIN_LEGACY`。**

北向数据不能放入官方 `POST_20240819_QUARTERLY_ONLY` 字段中冒充当前公开口径。使用专用模式：

```text
mode = POST_20240819_LEGACY_IMPORTED
```

Excel 原有“北向净流入/净买入 TOP10/净卖出 TOP10”等字段**原值保留**在：

```text
legacyImportedFields
```

并写入：

```text
officialDisclosureCompatible = false
excludeFromOfficialTimeSeries = true
excludeFromTrackScoring = true
```

页面固定提示：

> 历史 Legacy 数据：来自 2026-07-17 原 Excel，仅用于还原当日报表；2024-08-19 后官方披露口径已变化，该数据不作为 SMI 官方北向连续序列，也不参与主赛道评分或“主力×北向”重合计算。

### 0.6 本地自动化与 GitHub Actions 双方案

**结论：GitHub Actions 是推荐主方案；Windows 本地计划任务是开发/降级方案。**

本地标准链路仍优先：

```text
Windows Task Scheduler
→ Python Collector
→ JSON validation
→ git commit/push
→ Cloudflare Pages Git Integration
```

直接 `wrangler pages deploy` 仅作为应急发布手段，不作为日常双写链路，避免 Git 与线上版本分叉。

### 0.7 复合赛道

**结论：V1 给出可执行代理映射，并要求启动时验证“代码 + 名称”一致。**

首批建议：

| SMI 赛道 | V1 东方财富代理 |
|---|---|
| 高股息中特估 | 中特估 `BK1139`；仅代表“中特估”价格代理，高股息属性作为配置标签，不假装存在单一“高股息中特估”官方板块 |
| 电力 | 电力 `BK0428` |
| 医药生物 | 医药生物 `BK1216` |
| 半导体/AI算力 | 半导体 `BK1036` 50% + 算力概念 `BK1134` 50% |

复合赛道价格/RPS 使用固定目标权重的日收益链式合成；资金流、成交额、涨停数、红盘比例使用成分股并集去重后聚合，避免同一股票同时出现在多个板块时重复计数。

### 0.8 综合总结规则引擎

**结论：V1.1 增加完整规则清单与优先级。**

首期至少实现：

1. 指数广度规则
2. 成交量能规则
3. 市场情绪规则
4. 主力资金规则
5. 两融规则
6. 主赛道规则
7. 北向披露口径说明规则
8. 风险共振规则
9. 模块缺失降级规则
10. Legacy 快照提示规则

详细输入字段、条件与文案模板见第 9 节。

---

## 1. 项目概述

### 1.1 建设目标

SMI V1 的核心目标不是构建实时交易系统，而是构建一个稳定、可追溯、可历史回查的 **A 股收盘全景数据平台**。

V1 需要满足：

1. 每个 A 股交易日收盘后自动采集并生成当日全景数据。
2. 九大模块统一使用结构化 JSON 输出。
3. 前端支持按日期浏览任意已归档交易日。
4. 数据源优先使用官方公开数据，其次使用 AKShare 封装的免费公开接口。
5. 板块与主力资金统一采用 **东方财富口径**；历史 Excel 中已有的通达信数据标记为 `TONGDAXIN_LEGACY`。
6. 北向资金按 2024-08-16 前/2024-08-19 后实施双口径兼容；2024-08-19 后 V1 自动版仅保证 HKEX 季度持仓，日度成交/活跃证券/旧式净流量明确 `UNAVAILABLE`。
7. 两融数据按 T+1 披露处理，不阻塞当日收盘快照。
8. 主赛道名单、评分权重、阈值全部配置化，不写死在代码中。
9. 采集端、数据层、展示层彻底解耦。
10. 第一阶段不引入付费 API、数据库服务器、长期在线后端服务。

### 1.2 V1 推荐技术基线

- **数据采集：** Python 3.11+、AKShare、pandas、requests/httpx
- **任务调度：** GitHub Actions
- **数据存储：** `web/public/data/` 中的按日 JSON 快照，由 Vite 原样复制到 `dist/data/`
- **前端：** Vue 3 + Vite + TypeScript
- **图表：** Apache ECharts
- **托管：** Cloudflare Pages
- **历史查询：** `manifest.json + daily/YYYY/YYYY-MM-DD.json`
- **可选兼容层：** TongDaXin Adapter，仅用于旧数据迁移或后续兼容，不作为 SMI V1 主依赖

### 1.3 明确不在 V1 首期范围内的能力

- 实时盘中行情
- 付费行情/API
- 用户账号系统
- 云端自选股同步
- Cloudflare D1 主数据库
- Cloudflare Workers 作为核心数据采集器
- LLM 自动生成投资结论
- 强制复刻通达信资金流口径

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────┐
│                    GitHub Actions                   │
│                                                     │
│  close-snapshot     t1-reconcile     manual-backfill│
└──────────────┬──────────────┬──────────────┬────────┘
               │              │              │
               ▼              ▼              ▼
┌─────────────────────────────────────────────────────┐
│                 Python Collector                    │
│                                                     │
│  Eastmoney / AKShare                                │
│  SSE / SZSE                                         │
│  HKEX                                               │
│  Sina trade calendar                                │
│  Legacy TongDaXin adapter                           │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│             Normalizer / Validator / Calculator     │
│                                                     │
│  字段标准化                                          │
│  日期校验                                            │
│  单位转换                                            │
│  指标计算                                            │
│  数据状态判定                                        │
│  主赛道评分                                          │
│  综合总结模板                                        │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                    Static Data                      │
│                                                     │
│  web/public/data/daily/2026/2026-08-13.json                    │
│  web/public/data/latest.json                                   │
│  web/public/data/manifest.json                                 │
│  web/public/data/calendar/2026.json                            │
│  web/public/data/status.json                                   │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                Cloudflare Pages                     │
│                                                     │
│        Vue 3 + Vite + TypeScript + ECharts          │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
              PC / Tablet / Mobile
```

### 2.1 核心设计原则

#### A. 前端不直接调用第三方行情接口

浏览器只读取 SMI 自己的静态 JSON：

```text
/web/public/data/latest.json
/web/public/data/manifest.json
/web/public/data/daily/2026/2026-08-13.json
```

东方财富、交易所、HKEX、AKShare 的访问全部发生在 GitHub Actions 中。

这样可以避免：

- 浏览器跨域问题
- 第三方接口暴露
- 前端 IP 直接触发限流
- 数据口径随刷新时间变化
- 历史页面因上游接口失效而无法复现

#### B. 每个交易日一个不可变语义快照

每日文件以交易日命名：

```text
YYYY-MM-DD.json
```

同一天允许被 T+1 校正任务修订，但必须增加：

```json
{
  "revision": 2,
  "updatedAt": "..."
}
```

#### C. 数据源与展示解耦

前端只依赖 SMI Schema，不依赖任何 AKShare 中文列名。

例如上游：

```text
融资融券余额
```

采集器转换后：

```json
"marginBalance": 18345.67
```

---

## 3. 数据口径总原则

### 3.1 SMI V1 新数据统一口径

| 数据类别 | SMI V1 主口径 |
|---|---|
| 宽基指数 | 东方财富 / 国证指数 |
| 全市场行情 | 东方财富 |
| 行业板块 | 东方财富行业板块 |
| 概念板块 | 东方财富概念板块 |
| 主力资金 | 东方财富资金流 |
| 涨停/跌停/炸板 | 东方财富股池 + 乐咕市场活跃度 |
| 两融 | 上交所 + 深交所官方公开数据 |
| 北向 | HKEX 官方公开口径 |
| 交易日历 | AKShare/Sina 历史种子 + 本地快照 + 市场数据二次确认 |
| 旧 Excel | TongDaXin Legacy |

### 3.2 旧 Excel 迁移

旧 Excel 数据导入时必须保留：

```json
{
  "sourceSystem": "TONGDAXIN_LEGACY",
  "legacy": true
}
```

禁止把历史通达信数据无标识地混入东方财富时间序列。

---

# 4. 九大模块数据源与字段规范

## 4.1 模块 1：宽基指数收盘数据

### 4.1.1 指数清单与 V1 主接口

| 指数 | 代码 | V1 主接口/参数 | 备用原则 |
|---|---:|---|---|
| 上证指数 | 000001 | `stock_zh_index_daily_em("sh000001", ...)` | 同代码已验收指数 Adapter |
| 深证成指 | 399001 | `stock_zh_index_daily_em("sz399001", ...)` | 同上 |
| 创业板指 | 399006 | `stock_zh_index_daily_em("sz399006", ...)` | 同上 |
| 科创50 | 000688 | `stock_zh_index_daily_em("sh000688", ...)` | 同上 |
| 沪深300 | 000300 | `stock_zh_index_daily_em("sh000300", ...)` 或已验收中证源 | 同上 |
| 北证50 | 899050 | `stock_zh_index_daily_em("bj899050", ...)` | 已验收北交所/指数日线 Adapter |
| 国证1000 | 399311 | `index_hist_cni("399311", ...)` | `stock_zh_index_daily_em("sz399311", ...)` 经验收后启用 |
| 国证2000 | 399303 | `index_hist_cni("399303", ...)` | `stock_zh_index_daily_em("sz399303", ...)` 经验收后启用 |

> V1.1 对收盘快照优先采用“指定代码 + 指定日期”的日线接口，而不是依赖一个实时指数列表是否覆盖全部 8 个指数。这样可以直接校验 `dataDate == tradeDate`，也更适合历史补跑。

### 4.1.2 国证参数格式

AKShare 当前 `index_hist_cni` 文档定义：

```text
symbol = 国证指数代码字符串
```

示例为：

```text
symbol="399005"
```

因此 SMI 固定：

```text
国证1000 → symbol="399311"
国证2000 → symbol="399303"
```

**不使用：**

```text
399303.SZ
SZ399303
```

### 4.1.3 北证50策略

`stock_zh_index_spot_em()` 文档描述为“沪深京指数”，但其公开参数枚举并没有对 `899050` 的存在作单项契约承诺，因此 V1 不把“spot 列表必须返回北证50”作为依赖。

主路径：

```text
stock_zh_index_daily_em(
    symbol="bj899050",
    start_date=tradeDate,
    end_date=tradeDate
)
```

`bj` 前缀是当前 AKShare 文档明确支持的北交所指数前缀。

验收条件：

```text
返回 1 条目标日期记录
日期 == tradeDate
close > 0
code/name 校验通过
```

### 4.1.4 标准字段

```text
code
name
close
previousClose
changePct
source
sourceDate
sourceContract
```

涨跌幅统一按百分数保存，例如：

```json
"changePct": 1.26
```

代表 `+1.26%`。

## 4.2 模块 2：两市成交额

### 4.2.1 定义

SMI 中“**两市**”明确指：

- 上交所
- 深交所

不包含北交所。

### 4.2.2 推荐数据源

主接口：

```text
stock_zh_a_spot_em()
```

该接口包含：

```text
代码
成交额
```

采集后根据证券市场标识过滤沪深 A 股并求和。

### 4.2.3 指标

```text
turnoverToday
turnoverPrevious
turnoverDelta
turnoverChangePct
volumeState
```

### 4.2.4 公式

```text
turnoverDelta
= turnoverToday - turnoverPrevious
```

```text
turnoverChangePct
= turnoverDelta / turnoverPrevious × 100%
```

默认量能规则配置：

```yaml
volume_state:
  expansion_threshold_pct: 5
  contraction_threshold_pct: -5
```

判定：

```text
>= +5%  → EXPANSION（放量）
<= -5%  → CONTRACTION（缩量）
其他    → FLAT（平量）
```

阈值必须配置化。

---

## 4.3 模块 3：市场情绪指标

### 4.3.1 推荐接口

全市场状态：

```text
stock_zh_a_spot_em()
stock_market_activity_legu()
```

涨停：

```text
stock_zt_pool_em(date=YYYYMMDD)
```

炸板：

```text
stock_zt_pool_zbgc_em(date=YYYYMMDD)
```

跌停：

```text
stock_zt_pool_dtgc_em(date=YYYYMMDD)
```

### 4.3.2 字段

```text
riseCount
fallCount
flatCount
nonStLimitUpCount
stLimitUpCount
nonStLimitDownCount
stLimitDownCount
brokenLimitCount
suspendedCount
```

### 4.3.3 ST 分类

名称匹配规则：

```text
ST
*ST
S*ST
```

必须统一由 `security_classifier` 处理，避免不同模块重复实现。

### 4.3.4 注意

东方财富涨停、跌停、炸板池属于近期接口。

因此：

> SMI 每天必须归档当日结果，不应假设未来可以无损补回多年以前的炸板数据。

---

## 4.4 模块 4：板块行情表现

### 4.4.1 V1 口径

统一改为：

- 东方财富行业板块
- 东方财富概念板块

旧 Excel 中的通达信板块数据保留 `TONGDAXIN_LEGACY` 标识。

### 4.4.2 接口

行业：

```text
stock_board_industry_name_em()
```

概念：

```text
stock_board_concept_name_em()
```

### 4.4.3 上游主要字段

```text
板块名称
板块代码
最新价
涨跌额
涨跌幅
总市值
换手率
上涨家数
下跌家数
领涨股票
领涨股票-涨跌幅
```

### 4.4.4 SMI 输出

四组：

```text
industryTop5
industryBottom5
conceptTop5
conceptBottom5
```

每项：

```json
{
  "code": "BKxxxx",
  "name": "半导体",
  "changePct": 3.18,
  "turnoverRate": 2.41,
  "riseCount": 58,
  "fallCount": 9,
  "leader": "XXXX"
}
```

---

## 4.5 模块 5：主力资金流向

### 4.5.1 V1 口径

统一采用：

> 东方财富资金流口径

不得在页面上标注“通达信标准”。

### 4.5.2 接口

个股：

```text
stock_individual_fund_flow_rank(indicator="今日")
```

行业/概念：

```text
stock_sector_fund_flow_rank(
    indicator="今日",
    sector_type="行业资金流"
)

stock_sector_fund_flow_rank(
    indicator="今日",
    sector_type="概念资金流"
)
```

### 4.5.3 主要上游字段

包括：

```text
主力净流入-净额
主力净流入-净占比
超大单净流入-净额
大单净流入-净额
中单净流入-净额
小单净流入-净额
```

### 4.5.4 SMI 输出

```text
industryInflowTop10
industryOutflowTop10
conceptInflowTop10
conceptOutflowTop10
stockInflowTop10
stockOutflowTop10
```

统一换算为亿元：

```text
amountYi = amountYuan / 100000000
```

资金流字段必须附：

```json
"method": "EASTMONEY_MAIN_FORCE"
```

---

## 4.6 模块 6：北向资金

### 4.6.1 设计原则

北向模块必须区分：

1. **官方可自动落地字段**
2. **官方存在网页展示但 V1 未验证稳定机器接口的字段**
3. **旧披露口径已经终止的字段**
4. **Legacy Excel 导入字段**

不得为了保持 Excel 版字段外观而混用这些语义。

### 4.6.2 2024-08-16 及以前

历史快照可使用旧披露口径：

```text
mode = PRE_20240819_NET_FLOW
```

字段可包含：

```text
北向合计净流入
沪股通净流入
深股通净流入
净买入 TOP10
净卖出 TOP10
主力/北向同步流入
主力/北向同步流出
```

但历史补录时仍要记录真实来源与是否为 Legacy。

### 4.6.3 2024-08-19 起：V1 自动生产模式

V1.1 固定：

```text
mode = POST_20240819_QUARTERLY_ONLY
```

#### A. 可自动获取：季度持仓

官方公开 GET 页面：

```text
SH:
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh

SZ:
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz
```

GitHub Actions 无需浏览器，采用：

```text
HTTP GET
→ HTML parse
→ 提取 Shareholding Date
→ 提取持仓表
→ 校验字段和行数
```

标准字段：

```text
market
shareholdingDate
stockCode
stockName
shareholdingInCCASS
shareholdingPct
sourceUrl
```

页面当前说明：

- 自 2024-08-19 起北向持股只按季度提供；
- 前一季度信息在季末后第 5 个北向交易日发布；
- 页面查询历史范围受 HKEX 展示周期限制。

因此 SMI 必须在每次成功获取后自行永久归档季度快照。

#### B. V1 明确不自动接入：日度成交额

HKEX Historical Daily：

```text
https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en
```

官方网页存在日度市场统计展示，但当前未找到 HKEX 对公众承诺的稳定免费 CSV/REST 契约，网页内容为动态加载。

V1：

```text
dailyTurnover.status = UNAVAILABLE
dailyTurnover.reason = NO_VERIFIED_FREE_MACHINE_ENDPOINT
```

页面提供“查看 HKEX Historical Daily”外链说明，不抓取未公开承诺的内部 AJAX 地址。

#### C. V1 明确不自动接入：活跃证券

同理：

```text
activeSecurities.status = UNAVAILABLE
activeSecurities.reason = NO_VERIFIED_FREE_MACHINE_ENDPOINT
```

因此 V1 不计算：

```text
北向高活跃 ∩ 主力净流入
北向高活跃 ∩ 主力净流出
```

对应：

```text
overlap.status = UNAVAILABLE
```

#### D. 旧式日度净流量

2024-08-19 后：

```text
legacyNetFlow.status = UNAVAILABLE
legacyNetFlow.reason = DISCLOSURE_RULE_CHANGED
```

包括：

```text
北向合计净流入
沪股通净流入
深股通净流入
净买入 TOP10
净卖出 TOP10
```

在原官方语义下均不得继续自动生成。

### 4.6.4 页面展示规则

生产日期 >= 2024-08-19 时北向卡片默认显示：

```text
最近一期北向季度持仓
持仓日期
沪股通/深股通持仓明细入口
数据更新时间
```

其余区域显示：

> 日度北向净流入旧口径已停止披露；SMI V1 暂未接入可验证的免费机器化 Historical Daily 接口。

### 4.6.5 Legacy 例外

如果历史 Excel 在 2024-08-19 后仍保存了“北向净买入 TOP10”等字段，**只允许放入 `legacyImportedFields`**，详见第 29 节，不能写入本节的官方字段。

## 4.7 模块 7：两融数据

### 4.7.1 当前 AKShare 接口契约

V1.1 核验基线：

```text
AKShare 文档版本：1.18.88
核验日期：2026-08-14
契约状态：DOC_VERIFIED
```

当前文档仍列出：

```text
stock_margin_sse(start_date, end_date)
stock_margin_detail_sse(date)
stock_margin_szse(date)
stock_margin_detail_szse(date)
```

目标官方页面：

```text
SSE:
http://www.sse.com.cn/market/othersdata/margin/sum/

SZSE:
https://www.szse.cn/disclosure/margin/margin/index.html
```

**注意：`DOC_VERIFIED` 不等于生产 Runner 已实跑。** V1 上线门槛要求这些接口在 GitHub Actions Linux Runner 上通过 `RUNNER_VERIFIED`。

### 4.7.2 上交所可取得字段

汇总：

```text
融资余额
融资买入额
融券余量
融券余量金额
融券卖出量
融资融券余额
```

明细额外包含：

```text
融资偿还额
融券偿还量
```

### 4.7.3 深交所可取得字段

汇总：

```text
融资买入额
融资余额
融券卖出量
融券余量
融券余额
融资融券余额
```

当前公开封装的深交所明细不提供与 SSE 完全相同的融资偿还额/融券偿还量字段，因此相关净值继续按第 5 节定义为派生值并标记 `DERIVED`。

### 4.7.4 单位标准

SMI 内部金额统一：

```text
亿元
```

数量：

```text
亿股/亿份
```

先按接口实际单位转为基础值后再汇总，禁止直接混加 SSE/SZSE 不同单位。

### 4.7.5 降级策略

```text
Primary:
  AKShare pinned version

Fallback-A:
  retry + exponential backoff

Fallback-B:
  已单独通过 RUNNER_VERIFIED 的 SSEOfficialAdapter / SZSEOfficialAdapter

若 T 日尚未披露:
  PENDING

若应披露但上游仍返回 T-1:
  STALE

若请求/解析/Schema 破坏:
  ERROR
```

禁止：

```text
用第三方估算余额替换 SSE/SZSE 官方余额并标 FINAL
```

已有 FINAL 历史快照不得因当次失败而被空值覆盖。

# 5. 两融指标计算公式

## 5.1 融资余额

```text
融资余额
= SSE融资余额 + SZSE融资余额
```

## 5.2 融券余额

```text
融券余额
= SSE融券余量金额 + SZSE融券余额
```

## 5.3 两融总余额

优先：

```text
两融总余额
= SSE融资融券余额 + SZSE融资融券余额
```

并执行一致性校验：

```text
融资余额 + 融券余额 ≈ 两融总余额
```

允许极小的单位换算/四舍五入差异。

## 5.4 较前一交易日余额变动

```text
两融余额变动
= 两融总余额(T) - 两融总余额(T-1)
```

## 5.5 融资净买入

标准业务含义：

```text
融资净买入额
= 融资买入额 - 融资偿还额
```

### SSE

可以直接从 `stock_margin_detail_sse()` 汇总：

```text
Σ融资买入额 - Σ融资偿还额
```

### SZSE

AKShare 当前公开封装未直接输出“融资偿还额”。

因此 SMI V1 定义：

```text
SZSE融资净买入派生值
= SZSE融资余额(T) - SZSE融资余额(T-1)
```

根据余额恒等关系，其正常情况下等价于当期融资买入减偿还的净变化。

最终：

```text
融资净买入
= SSE直接净买入
+ SZSE融资余额净变化
```

必须附数据质量：

```json
"quality": "DERIVED"
```

若未来深交所/AKShare 提供可直接取得的融资偿还额，则切换为：

```json
"quality": "OFFICIAL"
```

并保留计算版本。

## 5.6 融券净卖出

由于沪深公开免费字段的结构并不完全一致，V1 不将其伪装为精确“金额”。

SMI 定义为：

```text
融券净卖出量
```

单位：

```text
亿股/亿份
```

SSE：

```text
SSE融券净卖出量
= Σ融券卖出量 - Σ融券偿还量
```

SZSE：

```text
SZSE融券净卖出量
≈ 融券余量(T) - 融券余量(T-1)
```

最终：

```text
融券净卖出量
= SSE融券净卖出量
+ SZSE融券余量变化
```

质量：

```text
DERIVED
```

如发生送转、拆并股等公司行为导致余量异常变化，应标记：

```text
quality = ESTIMATED
```

并记录异常说明。

## 5.7 两融成交额

严格意义应为：

```text
融资买入成交额 + 融券卖出成交额
```

其中融资买入额可直接获取；融券卖出公开免费接口通常提供数量而不是统一的成交金额。

因此 SMI V1 使用：

```text
融券卖出额估算
= Σ(证券融券卖出量 × 当日证券VWAP)
```

其中：

```text
VWAP
= 当日成交额 / 当日成交股数
```

注意 A 股行情的成交量若以“手”为单位，应乘 100 后再计算。

最终：

```text
两融成交额
= 融资买入额 + 融券卖出额估算
```

质量：

```text
ESTIMATED
```

前端 Tooltip 必须提示：

> 融券成交金额基于日均成交价估算，并非交易所逐笔成交金额。

## 5.8 两融成交占两市总成交比

```text
两融成交占比
= 两融成交额 / 沪深两市成交额 × 100%
```

其中分母必须与模块 2 使用同一“沪深两市”口径。

---

# 6. 模块 8：主赛道每日监测

## 6.1 赛道名单配置化

正式文件：

```text
config/tracks.yaml
```

V1 首批建议：

```yaml
tracks:
  - id: dividend_cnsoe
    name: 高股息中特估
    enabled: true
    positioning: 高股息/央国企价值
    proxy:
      type: single
      board_type: concept
      code: BK1139
      expected_name: 中特估
    proxy_note: "BK1139 只作为中特估行情代理；高股息属性为 SMI 标签，不宣称东方财富存在单一同名板块"

  - id: power
    name: 电力
    enabled: true
    positioning: 公用事业/高股息
    proxy:
      type: single
      board_type: industry
      code: BK0428
      expected_name: 电力

  - id: healthcare
    name: 医药生物
    enabled: true
    positioning: 防御+成长
    proxy:
      type: single
      board_type: industry
      code: BK1216
      expected_name: 医药生物

  - id: semiconductor_ai
    name: 半导体/AI算力
    enabled: true
    positioning: 科技成长
    proxy:
      type: composite
      components:
        - code: BK1036
          expected_name: 半导体
          board_type: industry
          weight: 0.50
        - code: BK1134
          expected_name: 算力概念
          board_type: concept
          weight: 0.50
```

代码与名称必须同时验证；若东方财富调整板块代码/名称：

```text
track.status = ERROR
```

不得自动寻找“名字相似”的替代板块。

## 6.2 单一代理赛道的计算

例如：

```text
电力 BK0428
医药生物 BK1216
中特估 BK1139
```

价格/RPS：

```text
直接使用代理板块的日收盘序列
```

成分股型指标统一从代理板块成分股集合计算：

```text
turnover
mainNetInflow
limitUpCount
redStockRatio
ladderCompleteness
```

这样与复合赛道保持同一统计逻辑。

## 6.3 复合赛道“半导体/AI算力”

### 6.3.1 价格代理

组件：

```text
BK1036 半导体   weight = 0.50
BK1134 算力概念 weight = 0.50
```

每日组件收益：

```text
r_i(t) = Close_i(t) / Close_i(t-1) - 1
```

复合赛道每日收益：

```text
r_track(t)
= 0.5 × r_BK1036(t)
+ 0.5 × r_BK1134(t)
```

构造链式指数：

```text
TrackIndex(base) = 1000

TrackIndex(t)
= TrackIndex(t-1) × (1 + r_track(t))
```

这相当于每日按目标权重再平衡，避免直接把两个不同点位尺度的板块指数相加。

### 6.3.2 RPS60

```text
TrackReturn60
= TrackIndex(T) / TrackIndex(T-60) - 1
```

然后与第 7 节规定的东方财富行业+概念板块 60 日收益分布做百分位比较。

### 6.3.3 成分股并集

```text
S_track
= Constituents(BK1036) ∪ Constituents(BK1134)
```

按证券代码去重。

不得：

```text
直接把两个板块主力净流入金额相加
```

因为同一股票可能同时属于两个板块，会重复计数。

### 6.3.4 资金流

对去重后的成分股集合：

```text
TrackMainNetInflow(t)
= Σ IndividualMainNetInflow_j(t)
```

个股主力资金来源仍为东方财富口径。

### 6.3.5 成交额

```text
TrackTurnover(t)
= Σ Turnover_j(t)
```

同一股票只计算一次。

### 6.3.6 红盘比例

```text
RedStockRatio
= 上涨成分股数 / 有效成分股数 × 100%
```

### 6.3.7 涨停与连板

对去重后的成分股集合与模块 3 的涨停/连板数据做交集。

### 6.3.8 连续净流入天数

不向上游倒查“连续板块资金流”：

```text
直接读取 SMI 自身 daily snapshots
```

从 T 日向前连续统计：

```text
TrackMainNetInflow > 0
```

的交易日数量。

## 6.4 高股息中特估的边界

V1 没有找到一个可验证且稳定对应“高股息中特估”完整语义的单一东方财富板块。

因此：

```text
价格代理 = BK1139 中特估
```

“高股息”只作为 SMI 业务标签。

如果未来要严格表达高股息，需要升级为：

```text
中特估成分 ∩ 股息率筛选
```

这属于 V1.2 以后功能，不在 V1 暗中推算。

## 6.5 主赛道基础字段

每条赛道：

```text
date
trackId
trackName
positioning
proxyDefinition
turnoverRank
mainNetInflow
continuousInflowDays
maAlignment
rps60
excessReturn20d
limitUpCount
limitUpRate
ladderCompleteness
redStockRatio
coreCatalyst
earningsRealization
score
coveragePct
decision
```

# 7. RPS60 定义

## 7.1 原始收益率

```text
Return60_i
= Close_i(T) / Close_i(T-60) - 1
```

使用 60 个交易日，不使用 60 个自然日。

## 7.2 比较 Universe

V1.1 固定默认：

```yaml
rps:
  universe: eastmoney_industry_and_concept_boards
```

即：

> 对当期可正常取得历史行情的东方财富行业板块 + 概念板块计算 60 个交易日收益率，形成统一横截面分布。

单一代理赛道直接把其 60 日收益放入该分布取百分位；复合赛道先按第 6.3 节生成合成 60 日收益，再放入同一分布取百分位。

必须保存：

```text
rpsUniverseSize
rpsUniverseHash
```

如果板块 Universe 因上游分类调整发生明显变化，应记录版本变化，避免历史 RPS 无提示漂移。

## 7.3 公式

设可比较板块数量为 `N`：

```text
RPS60_i
= PercentileRank(Return60_i) × 100
```

取值：

```text
0 ~ 100
```

解释：

```text
RPS60 = 90
```

表示该赛道过去 60 个交易日的表现超过约 90% 的比较对象。

---

# 8. 主赛道综合达标率与最终判定

## 8.1 V1 默认权重表

权重全部写入：

```text
config/track-scoring.yaml
```

| 指标 | 权重 |
|---|---:|
| 当日成交额排名 | 10 |
| 今日主力净流入 | 15 |
| 连续主力净流入天数 | 10 |
| 5/10/20 日多头排列 | 10 |
| RPS60 | 15 |
| 近20日跑赢沪深300 | 10 |
| 板块涨停表现 | 8 |
| 连板梯队完整性 | 7 |
| 红盘个股占比 | 5 |
| 核心催化逻辑 | 5 |
| 业绩兑现情况 | 5 |
| **总计** | **100** |

## 8.2 分项评分建议

### 成交额排名

先转换成横截面百分位。

```text
Top 20%      → 100
20%~40%      → 80
40%~60%      → 60
60%~80%      → 40
Bottom 20%   → 20
```

### 今日主力净流入

以赛道净流入金额和横截面排名联合判断：

```text
净流入且排名 Top20%  → 100
净流入且 Top20~50%   → 80
净流入且其余          → 60
接近 0                → 40
净流出                 → 0~30
```

具体净流入零值容差配置化。

### 连续净流入天数

```text
>= 5 日  → 100
3~4 日   → 80
2 日     → 60
1 日     → 40
0 日     → 0
```

### 5/10/20 日多头排列

```text
Close > MA5 > MA10 > MA20      → 100
Close > MA5、MA10、MA20        → 70
Close > 任意两条均线            → 40
其他                           → 0
```

### RPS60

直接使用：

```text
score = RPS60
```

### 近 20 日跑赢沪深300

```text
Excess20
= TrackReturn20 - CSI300Return20
```

评分：

```text
>= +5%       → 100
+2% ~ +5%    → 80
0 ~ +2%      → 60
-2% ~ 0      → 40
< -2%        → 0
```

### 板块涨停表现

保留原始：

```text
limitUpCount
```

评分建议按成分股比例：

```text
limitUpRate
= limitUpCount / validConstituentCount × 100%
```

```text
>= 3%        → 100
1.5%~3%      → 80
0.5%~1.5%    → 60
>0           → 40
0            → 0
```

### 连板梯队完整性

默认规则：

```text
存在 3板及以上 + 存在 2板 + 有首板梯队 → 100
存在 2板 + 首板                        → 70
只有首板                               → 40
无涨停                                 → 0
```

后续可配置更多梯队条件。

### 红盘个股占比

```text
redStockRatio
= 上涨成分股数量 / 有效成分股数量 × 100%
```

```text
>= 70%      → 100
60%~70%     → 80
50%~60%     → 60
40%~50%     → 40
<40%        → 0
```

### 核心催化逻辑

V1 初期允许配置/人工维护：

```text
STRONG       → 100
CONFIRMED    → 80
NEUTRAL      → 50
WEAK         → 20
NONE         → 0
UNKNOWN      → 不计入有效权重
```

### 业绩兑现情况

```text
STRONG       → 100
CONFIRMED    → 80
NEUTRAL      → 50
WEAK         → 20
NEGATIVE     → 0
UNKNOWN      → 不计入有效权重
```

---

## 8.3 缺失字段的权重处理

UNKNOWN 不按 0 分处理。

公式：

```text
综合达标率
= Σ(有效指标得分 × 指标权重)
  / Σ(有效指标权重)
```

因此：

```text
0 ~ 100
```

同时输出：

```text
coveragePct
= 有效权重 / 总权重 × 100%
```

建议：

```text
coveragePct < 80%
```

时前端显示：

> 数据覆盖不足，判定可信度降低

---

## 8.4 最终判定阈值

默认：

```yaml
decision:
  pass_min: 75
  watch_min: 55
```

对应：

```text
score >= 75        → PASS / 达标
55 <= score < 75   → WATCH / 观察
score < 55         → AVOID / 规避
```

页面中文：

```text
达标
观察
规避
```

注意：

> 该判定属于 SMI 自定义量化监测结果，不等于证券买卖建议。

---

# 9. 模块 9：综合总结规则引擎

V1 不依赖 LLM，统一使用确定性规则引擎。

配置建议：

```text
config/summary-rules.yaml
```

输出字段：

```text
indexAndTurnover
sentiment
fundFlow
margin
trackConclusion
marketEnvironment
riskWarning
dataNotice
```

## 9.1 执行顺序

规则优先级：

```text
P0 数据完整性 / Legacy 提示
P1 指数与量能
P2 市场情绪
P3 主力资金
P4 两融
P5 主赛道
P6 北向口径说明
P7 风险共振
```

同一段落允许多条规则贡献句子；出现数据 `ERROR/PENDING/UNAVAILABLE` 时，必须先通过可用性守卫，禁止引用无效字段。

---

## 9.2 规则 R01：指数广度偏强

**输入：**

```text
modules.marketIndex.items[*].changePct
沪深300.changePct
```

**条件：**

```text
8 个宽基指数中上涨数量 >= 6
AND 沪深300.changePct > 0
```

**输出模板：**

```text
今日宽基指数整体偏强，8 个监测指数中有 {upCount} 个收涨；
沪深300上涨 {csi300Pct}% ，市场指数广度较好。
```

反向规则：

```text
上涨数量 <= 2
```

模板：

```text
今日宽基指数整体承压，8 个监测指数中仅 {upCount} 个收涨，
指数层面的风险偏好偏弱。
```

---

## 9.3 规则 R02：成交量能

**输入：**

```text
turnoverToday
turnoverPrevious
turnoverDelta
turnoverChangePct
volumeState
```

**条件 A：**

```text
volumeState == EXPANSION
```

**模板：**

```text
沪深两市成交额 {turnoverToday} 亿元，较前一交易日增加
{turnoverDelta} 亿元（{turnoverChangePct}%），量能明显放大。
```

**条件 B：**

```text
volumeState == CONTRACTION
```

**模板：**

```text
沪深两市成交额 {turnoverToday} 亿元，较前一交易日减少
{abs(turnoverDelta)} 亿元（{abs(turnoverChangePct)}%），量能收缩。
```

**条件 C：**

```text
volumeState == FLAT
```

**模板：**

```text
今日两市成交额与前一交易日接近，量能整体平稳。
```

---

## 9.4 规则 R03：市场情绪偏强/偏弱

**输入：**

```text
riseCount
fallCount
nonStLimitUpCount
nonStLimitDownCount
brokenLimitCount
```

定义：

```text
breadthRatio = riseCount / max(fallCount, 1)
```

**偏强条件：**

```text
breadthRatio >= 1.5
AND nonStLimitUpCount >= 50
```

**模板：**

```text
市场赚钱效应偏强，上涨 {riseCount} 家、下跌 {fallCount} 家，
非 ST 涨停 {nonStLimitUpCount} 家，个股广度明显占优。
```

**偏弱条件：**

```text
breadthRatio <= 0.67
OR nonStLimitDownCount >= 20
```

**模板：**

```text
市场情绪偏弱，上涨 {riseCount} 家、下跌 {fallCount} 家，
非 ST 跌停 {nonStLimitDownCount} 家，需关注亏钱效应扩散。
```

阈值放入 `summary-rules.yaml`，不是代码常量。

---

## 9.5 规则 R04：主力资金方向

**输入：**

```text
fundFlow.industryInflowTop10
fundFlow.industryOutflowTop10
fundFlow.conceptInflowTop10
fundFlow.stockInflowTop10
```

V1 不用“TOP10 之和”冒充全市场资金净流入。

**条件：**

```text
fundFlow.status == FINAL
```

**模板：**

```text
东方财富主力资金口径下，行业净流入居前的是
{industryTop1Name}（{industryTop1Amount}亿元），
概念净流入居前的是 {conceptTop1Name}（{conceptTop1Amount}亿元）；
行业净流出居前的是 {industryOut1Name}。
```

如果模块非 FINAL：

```text
主力资金模块当前为 {status}，本次总结不对资金方向作确定性判断。
```

---

## 9.6 规则 R05：两融变化

**输入：**

```text
margin.status
margin.marginBalance
margin.marginBalanceChange
margin.financingNetBuyAmount.value
```

**条件 A：**

```text
margin.status == FINAL
AND marginBalanceChange > 0
```

**模板：**

```text
最新两融余额 {marginBalance} 亿元，较前一交易日增加
{marginBalanceChange} 亿元，杠杆资金余额边际上升。
```

**条件 B：**

```text
margin.status == FINAL
AND marginBalanceChange < 0
```

模板：

```text
最新两融余额 {marginBalance} 亿元，较前一交易日减少
{abs(marginBalanceChange)} 亿元，杠杆资金余额边际回落。
```

**条件 C：**

```text
margin.status == PENDING
```

模板：

```text
目标交易日两融数据尚处 T+1 披露窗口，本段暂沿用“待披露”状态，
不使用上一交易日数据冒充当日数据。
```

---

## 9.7 规则 R06：主赛道达标分布

**输入：**

```text
tracks.items[*].decision
tracks.items[*].score
tracks.items[*].coveragePct
```

计算：

```text
passCount
watchCount
avoidCount
validTrackCount
```

**条件：**

```text
passCount >= 2
```

**模板：**

```text
主赛道监测中共有 {passCount}/{validTrackCount} 个赛道达到“达标”阈值，
当前得分最高的是 {topTrackName}（{topTrackScore} 分）；
赛道结构具备一定集中度。
```

若：

```text
passCount == 0
```

模板：

```text
今日主赛道暂无赛道达到“达标”阈值，整体以观察或规避为主，
暂不支持强趋势环境判断。
```

---

## 9.8 规则 R07：北向披露口径固定说明

当：

```text
tradeDate >= 2024-08-19
AND northbound.mode == POST_20240819_QUARTERLY_ONLY
```

模板：

```text
北向资金按现行披露口径仅展示最近一期季度持仓；
SMI V1 不提供日度北向净流入、净买入及活跃证券自动值，
因此本次资金判断不引用旧式北向净流量。
```

如季度持仓可用：

```text
最近一期公开北向持仓日期为 {shareholdingDate}。
```

---

## 9.9 规则 R08：风险共振

**输入：**

```text
CSI300.changePct
ChiNext.changePct
turnover.volumeState
sentiment.breadthRatio
sentiment.nonStLimitDownCount
tracks.passCount
```

**高风险条件示例：**

```text
CSI300.changePct <= -1
AND ChiNext.changePct <= -1.5
AND breadthRatio < 0.7
AND nonStLimitDownCount >= 20
```

模板：

```text
指数、个股广度和跌停指标出现同步走弱，市场风险信号共振；
在数据恢复改善前，应将风险控制优先级置于进攻性判断之上。
```

另一条：

```text
volumeState == CONTRACTION
AND passCount == 0
AND breadthRatio < 1
```

模板：

```text
量能收缩且主赛道无达标项，当前市场缺少明确的增量资金与主线共振。
```

---

## 9.10 规则 R09：数据缺失降级

**输入：**

```text
所有 module.status
```

若任意被某段总结依赖的模块为：

```text
ERROR
PENDING
STALE
UNAVAILABLE
```

规则引擎不得读取其不可用字段。

模板：

```text
本次全景中 {moduleNames} 数据状态为 {statuses}，
相关结论已自动降级，不使用缺失或过期数据进行确定性推断。
```

---

## 9.11 规则 R10：Legacy 快照

当：

```text
meta.sourceSystem == TONGDAXIN_LEGACY
```

模板：

```text
本页为历史 Legacy 快照，部分板块、资金及北向字段沿用原 Excel 口径；
与 SMI V1 东方财富/现行官方口径存在差异，跨日期比较时需注意口径分界。
```

该规则优先级最高，必须在总结区和顶部状态区同时可见。

---

## 9.12 规则引擎输出约束

1. 不输出未被输入字段直接支持的事实。
2. 不从缺失字段猜测结论。
3. 不调用付费 AI。
4. 不生成个性化买卖指令。
5. 所有阈值配置化。
6. 每条输出记录 `ruleIds`，便于追溯：

```json
{
  "marketEnvironment": "...",
  "ruleIds": ["R01", "R02", "R03"]
}
```

# 10. 数据状态机

所有模块统一使用以下五种状态。

## 10.1 FINAL

含义：

> 目标交易日数据已经获取、日期匹配、核心字段验证通过。

示例：

```json
{
  "status": "FINAL",
  "dataDate": "2026-08-13"
}
```

## 10.2 PENDING

含义：

> 数据按披露规则预计稍后可取得。

典型：

```text
当日 16:20 的两融 T 日数据
```

页面：

```text
待披露
```

可同时显示上一有效交易日数据，但必须显示实际数据日期。

## 10.3 STALE

含义：

> 数据源应已提供目标日期，但实际返回的最新有效数据仍旧落后。

例如：

```text
目标：2026-08-13
实际：2026-08-12
```

页面：

```text
数据延迟
```

## 10.4 UNAVAILABLE

含义：

> 因制度、历史范围或数据源客观限制，本字段不可取得。

典型：

```text
2024-08-19 后北向净流入
```

页面：

```text
该口径已停止披露
```

UNAVAILABLE 不等于系统故障。

## 10.5 ERROR

含义：

> 按规则本应能取得，但采集、解析、验证发生错误。

页面：

```text
获取失败
```

必须记录：

```text
errorCode
errorMessage
attempts
```

---

## 10.6 状态转换

```text
             ┌───────────────┐
             │    PENDING    │
             └──────┬────────┘
                    │ 数据到达
                    ▼
             ┌───────────────┐
             │     FINAL     │
             └───────────────┘

ERROR ─────重试成功─────> FINAL

STALE ───上游完成更新───> FINAL

PENDING ─超过预期窗口───> STALE / ERROR

结构性不可取得──────────> UNAVAILABLE
```

### 10.7 FINAL 数据修订

FINAL 并非二进制不可修改。

若重新生成：

```text
revision = revision + 1
```

并保留：

```text
generatedAt
updatedAt
generationReason
```

---

# 11. 交易日历设计

## 11.1 本地交易日快照

目录：

```text
web/public/data/calendar/
├── 2024.json
├── 2025.json
├── 2026.json
└── ...
```

Schema：

```json
{
  "year": 2026,
  "source": [
    "AKSHARE_SINA",
    "LOCAL_VERIFICATION"
  ],
  "updatedAt": "2026-08-13T16:15:00+08:00",
  "dates": [
    "2026-01-05",
    "2026-01-06"
  ]
}
```

## 11.2 AKShare 接口

历史种子：

```text
tool_trade_date_hist_sina()
```

需要特别注意：

> 截至本设计文档核验时，AKShare 当前在线文档仍描述该接口的历史返回范围至 2024-12-31，因此 SMI 不得假定它天然覆盖所有未来年份。

因此该接口的正确定位是：

> 历史交易日种子 + 运行时可用性校验

而不是未来交易日唯一真源。

## 11.3 当前年份补强方案

依次使用：

1. 本地已验证快照
2. `tool_trade_date_hist_sina()` 返回范围
3. 上交所/深交所年度休市安排人工/脚本同步
4. 实际市场数据日期反证

未来可单独增加：

```text
calendar-updater
```

每年年初生成完整年度日历。

---

## 11.4 节假日双重校验

### 第一层：计划日历

```text
targetDate in localTradingCalendar
```

若否：

```text
close-snapshot 正常退出
```

不生成新日报。

### 第二层：市场事实校验

即使本地认为当天是交易日，也必须验证至少两个核心市场信号，例如：

```text
指数数据有当日收盘
AND
沪深A股有效证券数 > 最低阈值
AND
主要指数成交额 > 0
```

建议：

```text
market_validation:
  min_valid_stock_count: 4000
  required_indices:
    - 000001
    - 399001
    - 399006
```

股票数量阈值不能永久写死，应配置化并按市场扩容调整。

### 11.5 校验失败处理

若：

```text
calendar says trading day
but market data says no close
```

则：

```text
不发布 FINAL
```

记录：

```text
CALENDAR_MARKET_MISMATCH
```

---

# 12. 每日 JSON 数据模型

## 12.1 文件位置

```text
web/public/data/daily/YYYY/YYYY-MM-DD.json
```

例如：

```text
web/public/data/daily/2026/2026-08-13.json
```

## 12.2 完整 Schema 示例

以下为 V1 推荐完整示例。数值仅用于展示结构，不代表真实市场数据。

```json
{
  "schemaVersion": "1.0",
  "tradeDate": "2026-08-13",
  "generatedAt": "2026-08-13T16:25:31+08:00",
  "updatedAt": "2026-08-14T10:18:12+08:00",
  "revision": 2,
  "overallStatus": "FINAL",
  "generationReason": "T1_RECONCILE",
  "market": "CN_A",
  "timezone": "Asia/Shanghai",

  "meta": {
    "sourcePolicyVersion": "1.0",
    "indicatorSpecVersion": "1.0",
    "trackConfigVersion": "1.0",
    "legacy": false
  },

  "modules": {
    "marketIndex": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "source": ["EASTMONEY", "CNINDEX"],
      "items": [
        {
          "code": "000001",
          "name": "上证指数",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "399001",
          "name": "深证成指",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "399006",
          "name": "创业板指",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "000688",
          "name": "科创50",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "000300",
          "name": "沪深300",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "899050",
          "name": "北证50",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "EASTMONEY"
        },
        {
          "code": "399311",
          "name": "国证1000",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "CNINDEX"
        },
        {
          "code": "399303",
          "name": "国证2000",
          "close": 0,
          "previousClose": 0,
          "changePct": 0,
          "source": "CNINDEX"
        }
      ]
    },

    "turnover": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "source": ["EASTMONEY"],
      "unit": "亿元",
      "turnoverToday": 0,
      "turnoverPrevious": 0,
      "turnoverDelta": 0,
      "turnoverChangePct": 0,
      "volumeState": "FLAT"
    },

    "sentiment": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "source": ["EASTMONEY", "LEGULEGU"],
      "riseCount": 0,
      "fallCount": 0,
      "flatCount": 0,
      "suspendedCount": 0,
      "nonStLimitUpCount": 0,
      "stLimitUpCount": 0,
      "nonStLimitDownCount": 0,
      "stLimitDownCount": 0,
      "brokenLimitCount": 0
    },

    "sectorPerformance": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "method": "EASTMONEY",
      "industryTop5": [],
      "industryBottom5": [],
      "conceptTop5": [],
      "conceptBottom5": []
    },

    "fundFlow": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "method": "EASTMONEY_MAIN_FORCE",
      "unit": "亿元",
      "industryInflowTop10": [],
      "industryOutflowTop10": [],
      "conceptInflowTop10": [],
      "conceptOutflowTop10": [],
      "stockInflowTop10": [],
      "stockOutflowTop10": []
    },

    "northbound": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "mode": "POST_20240819_QUARTERLY_ONLY",
      "source": ["HKEX"],
      "dailyTurnover": {
        "status": "UNAVAILABLE",
        "value": null,
        "reason": "NO_VERIFIED_FREE_MACHINE_ENDPOINT"
      },
      "activeSecurities": {
        "status": "UNAVAILABLE",
        "items": [],
        "reason": "NO_VERIFIED_FREE_MACHINE_ENDPOINT"
      },
      "legacyNetFlow": {
        "status": "UNAVAILABLE",
        "reason": "DISCLOSURE_RULE_CHANGED",
        "totalNetInflow": null,
        "shanghaiNetInflow": null,
        "shenzhenNetInflow": null
      },
      "quarterlyHolding": {
        "status": "FINAL",
        "shareholdingDate": "2026-06-30",
        "sources": {
          "sh": "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh",
          "sz": "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz"
        },
        "items": []
      },
      "overlap": {
        "status": "UNAVAILABLE",
        "items": [],
        "reason": "DAILY_ACTIVE_SECURITIES_NOT_AUTOMATED"
      }
    },

    "margin": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "source": ["SSE", "SZSE"],
      "unit": "亿元",
      "financingBalance": 0,
      "securitiesLendingBalance": 0,
      "marginBalance": 0,
      "marginBalanceChange": 0,
      "financingBuyAmount": 0,
      "financingNetBuyAmount": {
        "value": 0,
        "quality": "DERIVED"
      },
      "securitiesLendingNetSellVolume": {
        "value": 0,
        "unit": "亿股/亿份",
        "quality": "DERIVED"
      },
      "marginTradeAmount": {
        "value": 0,
        "quality": "ESTIMATED"
      },
      "marginTradeSharePct": {
        "value": 0,
        "quality": "ESTIMATED"
      }
    },

    "tracks": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "configVersion": "1.0",
      "items": [
        {
          "trackId": "semiconductor_ai",
          "trackName": "半导体/AI算力",
          "positioning": "科技成长",
          "turnoverRank": 0,
          "mainNetInflow": 0,
          "continuousInflowDays": 0,
          "maAlignment": {
            "ma5": 0,
            "ma10": 0,
            "ma20": 0,
            "bullish": false
          },
          "rps60": 0,
          "excessReturn20d": 0,
          "limitUpCount": 0,
          "limitUpRate": 0,
          "ladderCompleteness": {
            "score": 0,
            "maxBoard": 0
          },
          "redStockRatio": 0,
          "coreCatalyst": {
            "state": "UNKNOWN",
            "text": ""
          },
          "earningsRealization": {
            "state": "UNKNOWN",
            "text": ""
          },
          "score": 0,
          "coveragePct": 0,
          "decision": "WATCH"
        }
      ]
    },

    "summary": {
      "status": "FINAL",
      "dataDate": "2026-08-13",
      "generator": "RULE_ENGINE_V1",
      "indexAndTurnover": "",
      "sentiment": "",
      "fundFlow": "",
      "trackConclusion": "",
      "marketEnvironment": "",
      "riskWarning": ""
    }
  },

  "validation": {
    "calendarExpectedTradingDay": true,
    "marketDateVerified": true,
    "requiredIndicesPresent": true,
    "stockUniverseCheckPassed": true,
    "criticalErrors": [],
    "warnings": []
  }
}
```

---

# 13. manifest.json

建议：

```json
{
  "schemaVersion": "1.0",
  "latestDate": "2026-08-13",
  "latestFinalDate": "2026-08-13",
  "updatedAt": "2026-08-14T10:18:12+08:00",
  "availableDates": [
    "2026-08-13",
    "2026-08-12",
    "2026-08-11"
  ]
}
```

日期选择器只允许选择：

```text
availableDates
```

中的日期。

---

# 14. status.json

用于首页快速判断采集系统是否正常：

```json
{
  "lastWorkflow": "t1-reconcile",
  "lastRunAt": "2026-08-14T10:18:12+08:00",
  "lastSuccessfulTradeDate": "2026-08-13",
  "latestDate": "2026-08-13",
  "health": "OK",
  "errors": []
}
```

---

# 15. 项目目录结构

V1.1 将静态数据唯一正式存储位置固定为：

```text
web/public/data/
```

完整建议：

```text
smi/
├── README.md
├── pyproject.toml
├── collector/
│   ├── requirements.txt
│   ├── adapters/
│   │   ├── eastmoney/
│   │   ├── akshare/
│   │   ├── sse/
│   │   ├── szse/
│   │   ├── hkex/
│   │   └── tongdaxin_legacy/
│   ├── modules/
│   │   ├── market_index.py
│   │   ├── turnover.py
│   │   ├── sentiment.py
│   │   ├── sectors.py
│   │   ├── fund_flow.py
│   │   ├── northbound.py
│   │   ├── margin.py
│   │   ├── tracks.py
│   │   └── summary.py
│   ├── calculators/
│   │   ├── margin.py
│   │   ├── rps.py
│   │   ├── tracks.py
│   │   └── summary.py
│   ├── validators/
│   │   ├── calendar.py
│   │   ├── market_close.py
│   │   ├── schema.py
│   │   └── sanity.py
│   ├── jobs/
│   │   ├── close_snapshot.py
│   │   ├── t1_reconcile.py
│   │   ├── manual_backfill.py
│   │   └── update_calendar.py
│   └── legacy/
│       └── import_excel.py
│
├── config/
│   ├── tracks.yaml
│   ├── track-scoring.yaml
│   ├── summary-rules.yaml
│   ├── market-rules.yaml
│   └── sources.yaml
│
├── scripts/
│   ├── run-close-snapshot.ps1
│   ├── run-t1-reconcile.ps1
│   └── run-manual-backfill.ps1
│
├── web/
│   ├── package.json
│   ├── vite.config.ts
│   ├── public/
│   │   └── data/
│   │       ├── daily/
│   │       │   └── 2026/
│   │       │       └── 2026-07-17.json
│   │       ├── calendar/
│   │       │   └── 2026.json
│   │       ├── latest.json
│   │       ├── manifest.json
│   │       └── status.json
│   ├── src/
│   │   ├── components/
│   │   ├── modules/
│   │   ├── composables/
│   │   ├── services/
│   │   ├── types/
│   │   └── utils/
│   └── dist/                  # build 产物，不作为源码数据真源
│       ├── index.html
│       ├── assets/
│       └── data/              # 由 public/data 原样复制
│
├── docs/
│   ├── SMI-V1.1-Design.md
│   ├── data-source-spec.md
│   ├── indicator-spec.md
│   ├── schema-spec.md
│   └── legacy-migration.md
│
└── .github/
    └── workflows/
        ├── close-snapshot.yml
        ├── t1-reconcile.yml
        └── manual-backfill.yml
```

**唯一数据真源：**

```text
web/public/data
```

禁止再同时维护：

```text
/data
web/public/data
```

两份生产副本。

# 16. 自动化工作流设计

GitHub Actions 的 `schedule` 使用 UTC。

中国大陆/台湾通常为 UTC+8，因此：

```text
16:20 Asia/Shanghai
≈ 08:20 UTC
```

考虑 GitHub scheduled workflow 可能延迟，并避免集中在整点，建议使用非整点分钟。

---

## 16.1 close-snapshot.yml

### 目标

每个工作日约 16:20 后执行当日收盘采集。

推荐 cron：

```yaml
on:
  schedule:
    - cron: "23 8 * * 1-5"
```

即：

```text
16:23 UTC+8
```

工作步骤：

```text
checkout
↓
setup-python
↓
install dependencies
↓
读取本地交易日历
↓
若非交易日：正常结束
↓
市场收盘二次校验
↓
采集模块 1~6、8
↓
模块 7 写 PENDING 或最近有效值
↓
计算模块 9
↓
Schema 验证
↓
生成 target-date JSON
↓
更新 latest / manifest / status
↓
语义 diff
↓
有变化才 commit
↓
push
```

---

## 16.2 t1-reconcile.yml

### 目标

补齐上一交易日 T+1 两融数据，并检查延迟字段。

推荐第一触发：

```yaml
on:
  schedule:
    - cron: "17 2 * * 1-5"
```

即：

```text
10:17 UTC+8
```

建议增加当天兜底：

```yaml
    - cron: "17 9 * * 1-5"
```

即：

```text
17:17 UTC+8
```

两次运行使用同一幂等逻辑。

目标日期不是“昨天自然日”，而是：

```text
previousTradingDate(today)
```

例如周一：

```text
target = 上周五
```

主要步骤：

```text
读取 previousTradingDate
↓
读取对应 daily JSON
↓
查询 SSE/SZSE 两融
↓
若仍未披露：
    保持 PENDING 或转 STALE
    不制造空值 FINAL
↓
若可取得：
    更新 margin 模块
    revision + 1
    updatedAt 更新
↓
重新计算与两融有关的 summary
↓
刷新 latest（仅当 target == latestDate）
↓
更新 status
↓
有变化才 commit
```

---

## 16.3 manual-backfill.yml

触发：

```yaml
on:
  workflow_dispatch:
    inputs:
      trade_date:
        description: "目标交易日 YYYY-MM-DD"
        required: true
        type: string
      force:
        description: "是否强制重建"
        required: false
        default: false
        type: boolean
```

功能：

```text
指定任意交易日
↓
验证是否为合法交易日
↓
重新采集所有可补历史模块
↓
对“近期接口已无法补回”的模块保留原快照
↓
生成新 revision
↓
写 generationReason = MANUAL_BACKFILL
```

对于炸板等只能取得近期数据的接口：

> 禁止用空数组覆盖历史已有有效数据。

---


## 16.4 Windows 本地计划任务：降级与开发方案

### 16.4.1 环境要求

推荐：

```text
Windows 10/11
Python 3.11
Git
Node.js LTS
```

Python 初始化：

```powershell
cd <SMI项目根目录>
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r collector\requirements.txt
```

V1.1 建议锁定依赖基线：

```text
akshare==1.18.88
pandas>=2.2,<3
requests>=2.32,<3
httpx>=0.27,<1
pydantic>=2.8,<3
PyYAML>=6,<7
openpyxl>=3.1,<4
lxml>=5,<7
beautifulsoup4>=4.12,<5
python-dateutil>=2.9,<3
```

上线前以实际锁定的 `requirements.txt` 和回归结果为准。

前端：

```powershell
cd web
npm ci
npm run build
```

构建结果：

```text
web\dist\
```

### 16.4.2 本地任务命令约定

设计 CLI：

```powershell
python -m collector.jobs.close_snapshot --date auto
python -m collector.jobs.t1_reconcile --date auto
python -m collector.jobs.manual_backfill --date 2026-07-17
```

### 16.4.3 Windows 计划任务时间

推荐：

```text
close-snapshot:
  周一~周五 16:25

t1-reconcile:
  周一~周五 10:20
```

脚本本身仍必须调用交易日历判断，所以“周一~周五”不是最终交易日判定。

### 16.4.4 本地主发布链路

推荐：

```text
Task Scheduler
→ collector
→ schema/semantic validation
→ git diff
→ 有变化才 commit
→ git pull --rebase
→ git push
→ Cloudflare Pages Git Integration 自动部署
```

此链路与 GitHub Actions 使用同一采集代码、同一数据目录、同一幂等规则。

### 16.4.5 Cloudflare 直接上传

仅作为应急操作：

```powershell
cd web
npm ci
npm run build
npx wrangler pages deploy dist --project-name=<SMI Pages 项目名>
```

需要 Cloudflare 授权配置。

**V1 不建议日常同时启用“git 自动部署”和“本地直接上传”两条生产写链路。**
标准生产源仍以 Git `main` 分支为准，直接上传只用于明确记录的应急发布。


# 17. 三个 Workflow 如何避免重复提交

## 17.1 全局 concurrency

三个数据写工作流使用相同组：

```yaml
concurrency:
  group: smi-data-write-${{ github.ref }}
  cancel-in-progress: false
```

目标：

> 同一时间只允许一个任务写 main 分支数据。

## 17.2 内容幂等

生成文件前后计算规范化 JSON Hash：

```text
canonical JSON
↓
SHA-256
```

若 Hash 相同：

```text
NO_CHANGE
```

不提交。

## 17.3 Git 层再次检查

提交前：

```text
git diff --quiet
```

无差异：

```text
exit 0
```

## 17.4 Push 前同步

建议：

```text
git pull --rebase
```

再执行最终 diff。

## 17.5 Revision 规则

只有实际语义变化才：

```text
revision + 1
```

以下情况不得增加 revision：

```text
重新运行但结果完全相同
格式化顺序变化
generatedAt 单独变化
```

因此 `generatedAt` 不应在 NO_CHANGE 重跑时无条件覆盖旧值。

---

# 18. 数据写入原子性

不能边采集边直接覆盖正式 JSON。

推荐：

```text
tmp/2026-08-13.json
↓
Schema validation
↓
Business validation
↓
Canonical serialize
↓
Atomic replace
↓
Update manifest
```

若任意关键校验失败：

```text
不得覆盖已有 FINAL 文件
```

---

# 19. 前端总体页面结构

V1 不采用“九个独立页面”，也不采用纯九 Tab。

推荐：

> 单页 Dashboard + 四大分组 + 模块内部折叠/切换

---

## 19.1 顶部区域

### Sticky Header

内容：

```text
SMI
Stock Market Intelligence
A股收盘全景
```

### 日期控制

```text
◀ 前一交易日
[ 2026-08-13 ▼ ]
最新
后一交易日 ▶
```

日期选择器：

- 读取 `manifest.availableDates`
- 非交易日不可选
- 无数据日期不可选
- 默认打开 `latestDate`
- URL 建议同步日期：

```text
/?date=2026-08-13
```

便于分享历史页面。

### 全局状态

例如：

```text
8 FINAL · 1 PENDING
最后更新 2026-08-13 16:25
```

---

# 20. 四大页面分组

## 20.1 市场总览

包含：

1. 宽基指数
2. 两市成交额
3. 市场情绪

PC：

```text
指数卡片网格
成交额图表
情绪统计
```

## 20.2 板块与资金

包含：

4. 板块表现
5. 主力资金
6. 北向数据

行业/概念内部可以使用二级 Tab：

```text
行业
概念
```

资金：

```text
净流入
净流出
```

## 20.3 杠杆与主赛道

包含：

7. 两融
8. 主赛道每日监测

模块 8 PC 优先表格。

移动端转换为赛道卡片。

## 20.4 今日结论

包含：

9. 综合总结

采用自然语言卡片。

---

# 21. 数据状态徽标 UI

统一组件：

```text
StatusBadge.vue
```

状态文案：

| 状态 | 中文 | UI 语义 |
|---|---|---|
| FINAL | 已更新 | 正常 |
| PENDING | 待披露 | 信息 |
| STALE | 数据延迟 | 警告 |
| UNAVAILABLE | 该口径不可得 | 中性 |
| ERROR | 获取失败 | 错误 |

颜色不要仅作为唯一识别方式。

徽标必须同时：

```text
颜色 + 图标 + 文字
```

例如：

```text
✓ 已更新
◷ 待披露
! 数据延迟
— 不再披露
× 获取失败
```

满足色弱用户可辨识性。

---

# 22. 移动端响应式设计

建议断点：

```text
>= 1200px   desktop-wide
768~1199px  tablet/desktop
< 768px     mobile
```

## 22.1 Desktop

采用 12 栅格：

```text
grid-template-columns: repeat(12, 1fr)
```

卡片可按：

```text
3/4/6/12 columns
```

布局。

## 22.2 Mobile

转换为：

```text
单列卡片
```

规则：

- 顶部日期导航保持固定
- 大表格禁止直接缩成极小字号
- TOP10 表格优先变成列表卡片
- 横向表格必要时允许内部横向滚动
- 主赛道表转换为每赛道一张评分卡
- ECharts 自动 resize
- 触控目标至少保持适当尺寸
- 重要数字字号优先于辅助字段

## 22.3 移动端模块 8

单条赛道：

```text
半导体 / AI 算力           达标
综合分 82
RPS60 91
20日超额 +6.2%
主力净流入 +18.3亿
连续流入 4日
红盘占比 76%

[展开详情]
```

---

# 23. ECharts 使用建议

模块：

```text
成交额：柱状图/趋势线
板块涨跌：双向水平柱状图
资金流：双向资金柱状图
两融：历史折线
RPS：进度条/雷达不优先
```

原则：

> 首页优先信息密度和可读性，不为“图表感”而增加图表。

对 TOP5/TOP10：

- 简单排行使用 HTML 表格往往比 ECharts 更清晰。
- 历史趋势才优先使用 ECharts。

---

# 24. 历史数据存储策略

## 24.1 每日一个 JSON

推荐：

```text
web/public/data/daily/2026/2026-08-13.json
```

而不是：

```text
每个模块一个文件
```

原因：

- 一个日期一次请求即可完整加载
- 历史回查天然映射
- 文件数量可控
- Git diff 清晰
- 一个交易日快照语义完整

## 24.2 不使用 SQLite 作为 V1 前端主存储

原因：

- 二进制 diff 差
- 每次更新整个 DB 文件
- 静态前端不能直接高效查询
- 数据量远未达到必须数据库化

## 24.3 未来升级条件

出现以下需求时考虑 D1/SQLite/API：

```text
按个股跨 5 年查询
复杂筛选
用户自选
统计回测
大量跨日期聚合
```

---

# 25. Cloudflare Pages 与 Vite 构建部署

## 25.1 V1 固定方案

采用：

```text
Vue 3 + Vite
静态 JSON：web/public/data/
Cloudflare Pages：单项目
```

Vite `public` 目录中的文件构建时原样复制到输出根目录。

源：

```text
web/public/data/daily/2026/2026-07-17.json
```

构建后：

```text
web/dist/data/daily/2026/2026-07-17.json
```

## 25.2 构建产物

典型：

```text
web/dist/
├── index.html
├── assets/
│   ├── index-<hash>.js
│   └── index-<hash>.css
└── data/
    ├── daily/
    ├── calendar/
    ├── latest.json
    ├── manifest.json
    └── status.json
```

`dist/` 是部署产物，不作为源码数据真源。

## 25.3 Cloudflare Pages 配置

```text
Production branch:       main
Root directory:          web
Build command:           npm ci && npm run build
Build output directory:  dist
```

前端 Fetch 路径固定为站点根路径：

```text
/web/public/data/manifest.json
/web/public/data/latest.json
/web/public/data/status.json
/data/daily/{YYYY}/{YYYY-MM-DD}.json
```

## 25.4 免费额度风险

V1 每个交易日通常触发 1~2 次数据变更部署，远低于典型个人项目规模；但仍应：

- 仅语义变更时 commit
- 避免无意义 revision
- 监控 Pages 构建次数
- 历史 JSON 文件数量接近平台限制前再考虑 R2/D1

## 25.5 为什么不做独立数据站点

V1 不把 JSON 拆成另一个 Pages/R2 项目，因为：

- 单项目路径最简单
- 同源 Fetch 无 CORS
- 数据与前端版本天然一致
- 日更规模足够小

未来大量历史数据或 API 查询出现后，再拆数据层。

# 26. 风险与容错设计

## 26.1 AKShare 不是稳定 SLA API

AKShare 很适合作为免费适配层，但其很多接口依赖公开网站。

风险：

- 上游页面改版
- 参数变化
- 中文列名变化
- 临时限流
- 防爬
- 返回空表
- 返回旧日期数据

应对：

```text
timeout
retry
schema check
date check
row-count check
fallback
module-level status
```

---

## 26.2 接口反爬

建议：

- 同一接口避免短时间重复调用
- 同类数据一次抓取后缓存
- 固定合理 User-Agent
- 指数/板块/个股抓取批量化
- 失败采用指数退避
- 不做高频轮询
- 不绕过网站明确的访问控制

---

## 26.3 模块级失败隔离

错误模块不能拖垮整份日报。

例如：

```text
marketIndex        FINAL
turnover           FINAL
sentiment          FINAL
sectorPerformance  ERROR
fundFlow           ERROR
northbound         FINAL
margin             PENDING
tracks             STALE
summary            FINAL
```

前端照常发布。

---

## 26.4 综合总结的依赖降级

如果资金流 ERROR：

模块 9 不应写：

```text
主力资金明显流入
```

而应：

```text
主力资金模块暂未取得有效数据，本项不作判断。
```

---

## 26.5 盘中/收盘区分

close-snapshot 不在 15:00 立即抓取。

推荐约：

```text
16:20+
```

校验：

```text
sourceDate == targetDate
required index close exists
market universe normal
turnover > 0
```

未通过不得标记 FINAL。

---

## 26.6 GitHub Actions 延迟

scheduled workflow 不是精确定时器。

因此：

- 使用 16:23 而不是整点
- 每次任务自行判断目标交易日
- 保留 manual-backfill
- `status.json` 显示最后成功运行时间
- 前端显示数据更新时间

---

## 26.7 北向历史断点

最重要风险之一。

必须永久保留：

```text
PRE_20240819_NET_FLOW
POST_20240819_QUARTERLY_ONLY
```

禁止未来开发者为了“字段连续”而把成交活跃误解释成净买入。

---

## 26.8 两融 T+1

close snapshot：

```text
margin.status = PENDING
```

页面可以展示：

```text
最新可用：上一交易日
```

但不得把上一日数据冒充目标日期。

---

## 26.9 Legacy 数据可比性

旧 Excel：

```text
TongDaXin
```

新数据：

```text
Eastmoney
```

跨口径做历史趋势图时：

- 显示口径分界线
- Tooltip 展示 source/method
- 默认避免将通达信资金绝对值和东方财富资金绝对值做无提示连续折线

---

# 27. 数据验证规则

## 27.1 指数

- 8 个指数必须齐全
- close > 0
- changePct 合理范围
- sourceDate == tradeDate

## 27.2 成交额

- > 0
- 与前一交易日变化不能出现明显单位级异常
- 股票 universe 不为空

## 27.3 市场情绪

检查：

```text
上涨 + 下跌 + 平盘 + 停牌 ≈ 有效证券总数
```

允许由于统计口径存在少量偏差。

## 27.4 板块

- 行业数量 > 最低值
- 概念数量 > 最低值
- TOP5 不允许重复
- NaN 排除后排序

## 27.5 资金

- TOP10 数量正常
- 流入榜按数值降序
- 流出榜按数值升序
- 金额单位转换后不允许 10^8 级错位

## 27.6 两融

- SSE/SZSE 日期一致
- 总余额 > 0
- 两融余额与融资+融券近似一致
- 前日数据必须存在才能计算变化

## 27.7 主赛道

- enabled track 全部有结果
- RPS 有足够历史窗口
- MA 至少有 20 个交易日
- Return60 至少有 61 个有效收盘点
- coveragePct 明确

---

# 28. 配置文件建议

## 28.1 sources.yaml

```yaml
market:
  primary: eastmoney
  fallback:
    - sina
    - tencent

northbound:
  primary: hkex

margin:
  primary:
    - sse
    - szse
```

## 28.2 market-rules.yaml

```yaml
volume_state:
  expansion_threshold_pct: 5
  contraction_threshold_pct: -5

validation:
  min_valid_stock_count: 4000
```

## 28.3 tracks.yaml

维护赛道清单与板块映射。

## 28.4 track-scoring.yaml

维护：

```text
权重
区间
PASS/WATCH/AVOID 阈值
```

---

# 29. 2026-07-17 Legacy Excel 基线导入

## 29.1 首个历史快照

V1 上线首日先把现有：

```text
《A股收盘全景》2026-07-17 Excel
```

转换为：

```text
web/public/data/daily/2026/2026-07-17.json
```

文件级：

```json
{
  "tradeDate": "2026-07-17",
  "meta": {
    "sourceSystem": "TONGDAXIN_LEGACY",
    "legacy": true,
    "importedFromExcel": true,
    "officialDisclosureCompatibility": false
  }
}
```

旧板块与主力资金：

```text
method = TONGDAXIN_LEGACY
```

不得改写成东方财富口径。

## 29.2 2026-07-17 北向字段

2026-07-17 明显属于 2024-08-19 后日期。

如果旧 Excel 保存：

```text
北向合计/沪股通/深股通净流入
净买入TOP10
净卖出TOP10
同步流入/同步流出
```

这些数据**原样保留，但不能写入 SMI 现行官方字段**。

专用模式：

```text
POST_20240819_LEGACY_IMPORTED
```

示例：

```json
{
  "northbound": {
    "status": "FINAL",
    "mode": "POST_20240819_LEGACY_IMPORTED",
    "sourceSystem": "TONGDAXIN_LEGACY",
    "officialDisclosureCompatible": false,

    "officialV1": {
      "dailyTurnover": {
        "status": "UNAVAILABLE",
        "value": null
      },
      "activeSecurities": {
        "status": "UNAVAILABLE",
        "items": []
      },
      "legacyNetFlow": {
        "status": "UNAVAILABLE",
        "reason": "DISCLOSURE_RULE_CHANGED"
      }
    },

    "legacyImportedFields": {
      "status": "FINAL",
      "totalNetInflow": 0,
      "shanghaiNetInflow": 0,
      "shenzhenNetInflow": 0,
      "netBuyTop10": [],
      "netSellTop10": [],
      "sameDirectionIn": [],
      "sameDirectionOut": [],
      "excludeFromOfficialTimeSeries": true,
      "excludeFromTrackScoring": true
    }
  }
}
```

### 页面提示

北向模块顶部：

> **历史口径已变更**：本页北向字段来自 2026-07-17 原 Excel，仅用于还原历史报表；2024-08-19 后官方披露口径已调整，Legacy 值不作为 SMI 官方北向连续序列。

### 分析限制

Legacy 北向值不得：

```text
参与 2024-08-19 后官方北向趋势图
参与主赛道评分
参与主力×北向重合计算
与季度持仓做净流量含义比较
```

## 29.3 迁移工具

一次性工具：

```text
collector/legacy/import_excel.py
```

职责：

1. 读取 Excel 9 个模块。
2. 保留原始字段值。
3. 转换 SMI 结构但不改变原数据口径。
4. 给每个模块增加 Legacy metadata。
5. 对不能可靠解释的值加 `quality/notes`。
6. 禁止根据缺失字段自动猜值。

## 29.4 后续新数据

2026-07-17 是首个基线，并不意味着后续新快照继续使用通达信。

正式上线后的新交易日：

```text
板块/主力资金 → EASTMONEY
北向 → HKEX QUARTERLY_ONLY
两融 → SSE/SZSE
```

日期跨过 Legacy→V1 分界时前端必须显示口径提示。

# 30. 前端数据加载流程

```text
App 初始化
↓
GET manifest.json
↓
读取 URL date
↓
若 URL date 不存在：
  使用 latestDate
↓
GET daily/YYYY/YYYY-MM-DD.json
↓
Schema version check
↓
Render
```

日期切换：

```text
date changed
↓
更新 URL query
↓
fetch snapshot
↓
更新所有模块
```

不需要刷新整个页面。

---

# 31. 缓存策略

静态文件建议：

### daily 历史文件

```text
Cache-Control: public, max-age=31536000, immutable
```

仅对已经确定不会再修订的旧日期适用。

近期 T/T+1 文件不要立即 immutable。

### manifest/latest/status

使用短缓存：

```text
max-age=60~300
```

避免页面长时间读取旧 latest。

---

# 32. 开发里程碑

## M0：规范冻结

输出：

- `data-source-spec.md`
- `indicator-spec.md`
- `schema-spec.md`
- `tracks.yaml`
- `track-scoring.yaml`

验收：

> 所有字段含义、单位、来源、公式都有唯一答案。

---

## M1：数据框架与日历

完成：

- Adapter 接口层
- JSON Schema
- 状态机
- Calendar
- Validator
- 本地 CLI 运行

验收：

```text
指定日期可生成合法空骨架/部分数据快照
```

---

## M2：模块 1~7

依次完成：

1. 指数
2. 成交额
3. 情绪
4. 板块
5. 主力资金
6. 北向
7. 两融

验收：

> 任一模块失败不会导致其他模块丢失。

---

## M3：模块 8~9

完成：

- 赛道配置
- MA5/10/20
- Return20/60
- RPS60
- 连续资金流
- 涨停/连板梯队
- 权重评分
- PASS/WATCH/AVOID
- 规则总结

---

## M4：历史迁移与自动化

完成：

- Excel Legacy Import
- close-snapshot
- t1-reconcile
- manual-backfill
- concurrency
- idempotent commit

---

## M5：Web Dashboard

完成：

- Vue 3
- 日期选择
- 四分组
- 9 模块
- 状态徽标
- ECharts
- Responsive
- 历史回查

---

## M6：上线与可靠性

完成：

- Cloudflare Pages
- 数据异常模拟
- 上游接口失败模拟
- 节假日验证
- 周五→周一 T+1 测试
- 北向 2024 分界测试
- 历史 Legacy 口径提示
- 自动任务健康状态

---

# 33. V1 验收标准

SMI V1 可认为完成，至少满足：

1. 任意已归档交易日能通过 URL/日期选择器打开。
2. 九模块均使用统一 Schema。
3. 每个模块明确显示 FINAL/PENDING/STALE/UNAVAILABLE/ERROR。
4. 收盘任务自动生成当日文件。
5. 两融 T+1 能自动回补。
6. manual workflow 能指定交易日补跑。
7. 同日重复运行不会产生无意义 Git commit。
8. 2024-08-16 与 2024-08-19 北向 Schema 能正确切换。
9. 新板块/资金数据全部标记东方财富口径。
10. Legacy 数据不会与新口径无提示混合。
11. 主赛道名单可只改 config 即增删。
12. 主赛道评分权重可只改 config 调整。
13. 移动端无需横向缩放整个页面即可使用。
14. 某一第三方接口失败不导致已有 FINAL 历史数据被空值覆盖。
15. 页面能显示最后数据日期、最后更新时间和异常模块。

---

# 34. V1 关键决策汇总

| 项目 | 决策 |
|---|---|
| 数据采集 | GitHub Actions + Python |
| 前端 | Vue 3 + Vite + TypeScript |
| 图表 | ECharts |
| 托管 | Cloudflare Pages |
| 数据库 | V1 不使用 |
| 历史存储 | `web/public/data/daily/YYYY/YYYY-MM-DD.json`，每交易日一个 JSON |
| 板块 | 东方财富 |
| 主力资金 | 东方财富 |
| 通达信 | Legacy/可选 Adapter |
| 北向 | 2024-08-16 前可保留净流量；2024-08-19 后自动版仅季度持仓，日度成交/活跃/旧式净流量均 UNAVAILABLE |
| 两融 | SSE+SZSE，T+1 回补 |
| 交易日历 | 本地快照 + AKShare/Sina + 市场事实双校验 |
| 主赛道 | 配置化名单 |
| RPS60 | 60 交易日收益横截面百分位 |
| 主赛道阈值 | >=75 达标；55~75 观察；<55 规避 |
| 综合总结 | V1 规则引擎 |
| 自动化 | close + T+1 reconcile + manual |
| 幂等 | concurrency + canonical hash + git diff |

---

# 35. 已知工程坑清单

1. `tool_trade_date_hist_sina` 当前文档描述的返回范围并未覆盖到 2026，不能作为未来日历唯一来源。
2. 东方财富/乐咕接口并无商业 SLA，AKShare 版本升级可能修改接口行为。
3. 涨停/跌停/炸板历史范围有限，必须从上线日起每日沉淀。
4. 东方财富资金流与通达信资金流不可直接视为同一序列。
5. 北向净流量在 2024-08-19 后无法按旧口径继续公开获取。
6. HKEX Historical Daily 网页虽存在日度统计，但 V1 未验证到官方承诺的稳定免费机器接口，因此日度成交额/活跃证券自动字段明确 UNAVAILABLE。
7. 北向季度持仓不是当日净买入替代指标。
7. 深交所公开免费接口结构与上交所不完全一致，融资净买入/融券净卖出需保留 `DERIVED` 标记。
8. “两融成交额”中的融券卖出成交额在 V1 免费方案中属于估算，应显示 `ESTIMATED`。
9. GitHub cron 可能延迟，不能把运行时间当成市场事实。
10. T+1 目标日期必须通过“上一交易日”函数计算，不能直接 `today - 1 day`。
11. workflow 重跑必须幂等，否则每天可能生成多次无意义提交。
12. Cloudflare Pages 会随 main 分支数据更新触发构建，需关注免费构建次数。
13. 表格在手机端直接缩放会不可读，必须设计移动端卡片模式。
14. 主赛道复合赛道（如半导体/AI算力）必须显式定义代理板块或组合算法。
15. RPS Universe 必须固定，否则历史 RPS 不可比。
16. 评分权重变更必须增加 `trackConfigVersion`，旧历史分数不能静默重算后覆盖。
17. 规则总结依赖模块异常时必须降级文案，不能基于缺失数据做确定性结论。

---

# 36. 后续 V2 可选演进

V1 稳定后再考虑：

- Cloudflare D1
- R2 历史归档
- Worker API
- 用户自选股
- 个股详情页
- 多周期趋势分析
- 数据质量监控页面
- 邮件/Telegram/企业微信异常通知
- AI 总结润色
- 回测与条件筛选
- AutoDeal 数据联动

---

# 37. 参考资料与 V1.1 核验来源

**核验日期：2026-08-14。**

## 37.1 AKShare

当前在线文档版本标题显示：

```text
AKShare 1.18.88
```

指数：

```text
https://akshare.akfamily.xyz/data/index/index.html
```

当前文档明确：

```text
index_hist_cni(symbol="399005", ...)
```

其中 `symbol` 来自 `index_all_cni()` 的“指数代码”，因此国证1000/2000使用：

```text
399311
399303
```

股票/两融：

```text
https://akshare.akfamily.xyz/data/stock/stock.html
```

当前文档列出：

```text
stock_margin_sse
stock_margin_detail_sse
stock_margin_szse
stock_margin_detail_szse
```

交易日工具：

```text
https://akshare.akfamily.xyz/data/tool/tool.html
```

注意 `tool_trade_date_hist_sina()` 只作为历史种子/辅助源，不是未来年度唯一日历真源。

## 37.2 HKEX

季度持仓直接 GET：

```text
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh
https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz
```

Historical Daily：

```text
https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en
```

V1.1 对 Historical Daily 的结论：

> 网页存在，但未把动态加载内部接口认定为官方稳定免费 API，因此不作为生产自动化依赖。

## 37.3 东方财富板块代理

已核验页面：

```text
中特估 BK1139
https://quote.eastmoney.com/bk/90.BK1139.html

电力 BK0428
https://quote.eastmoney.com/unify/r/90.BK0428

医药生物 BK1216
https://quote.eastmoney.com/bk/90.BK1216.html

半导体 BK1036
https://quote.eastmoney.com/bk/90.BK1036.html

算力概念 BK1134
https://quote.eastmoney.com/bk/90.BK1134.html
```

这些代码在每次生产配置装载时仍需做“代码+名称”契约校验。

## 37.4 Vite

```text
https://vite.dev/guide/assets.html#the-public-directory
```

设计依赖：

> `public` 目录中的资源构建时原样复制至输出目录根。

## 37.5 Cloudflare Pages

```text
https://developers.cloudflare.com/pages/
https://developers.cloudflare.com/pages/platform/limits/
```

V1 使用：

```text
Root = web
Build = npm ci && npm run build
Output = dist
```

## 37.6 GitHub Actions

```text
https://docs.github.com/actions/using-workflows/events-that-trigger-workflows
https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
```

生产设计仍要求：

```text
schedule + workflow_dispatch + concurrency + idempotent diff
```

# 38. 结论

SMI V1.1 正式锁定为：

```text
GitHub Actions（主生产）
+ Windows Task Scheduler（开发/降级）
+ Python / AKShare / Official Sources
+ web/public/data Daily JSON
+ Vue 3 / Vite / TypeScript / ECharts
+ Cloudflare Pages
```

数据口径：

```text
板块/主力资金    → 东方财富
旧 Excel         → TONGDAXIN_LEGACY
北向 2024-08-19+ → HKEX 季度持仓自动化；日度成交/活跃/旧净流量 UNAVAILABLE
两融             → SSE + SZSE，T+1 校正
主赛道           → 配置化代理 + 成分并集聚合 + 版本化评分
综合总结         → 可追溯规则引擎
```

V1.1 的工程优先级：

> **宁可明确标记 UNAVAILABLE，也不把“网页上能看到但机器接口未验证”的字段假定为可自动化；宁可模块降级，也不产生看似完整但无法证明口径的数据。**

只有通过第 39 节 `RUNNER_VERIFIED` 验收清单的外部接口，才允许进入正式生产链路。

# 39. 接口可用性验证清单

## 39.1 验证状态定义

```text
DOC_VERIFIED
= 当前官方/AKShare文档中存在明确接口契约

RUNNER_VERIFIED
= 在目标 GitHub Actions Linux Runner 上真实调用成功，
  返回字段、日期、数量均通过验收

PRODUCTION_READY
= RUNNER_VERIFIED + 重试 + Schema + 降级路径全部通过
```

**任何 `DOC_VERIFIED` 接口都不能直接等价为生产可用。**

实施时建议保留：

```text
docs/interface-verification.md
```

记录：

```text
测试日期
AKShare版本
Python版本
Runner OS
函数
参数
HTTP/异常
返回行数
字段列表
目标日期
结论
```

## 39.2 模块级清单

| 模块 | 首选接口/页面 | 当前设计状态 | Runner 验收项 | 降级 | 最终失败状态 |
|---|---|---|---|---|---|
| 1 指数-沪深主要指数 | `stock_zh_index_daily_em()` | DOC_VERIFIED | 目标日唯一记录、日期匹配、close>0 | 已验收同代码日线 Adapter | ERROR |
| 1 国证1000 | `index_hist_cni("399311")` | DOC_VERIFIED | 目标日记录、代码/日期/收盘有效 | `sz399311` EM 日线经单独验收 | ERROR |
| 1 国证2000 | `index_hist_cni("399303")` | DOC_VERIFIED | 同上 | `sz399303` EM 日线经单独验收 | ERROR |
| 1 北证50 | `stock_zh_index_daily_em("bj899050")` | DOC_VERIFIED | 日期=目标日、close>0 | 已验收北交所/其他日线 Adapter | ERROR |
| 2 两市成交额 | `stock_zh_a_spot_em()` | DOC_VERIFIED | 沪深有效证券数达阈值、成交额>0、日期为当日收盘 | 已验收 SSE/SZSE 汇总 Adapter | ERROR |
| 3 上涨/下跌/平盘 | `stock_zh_a_spot_em()` / `stock_market_activity_legu()` | DOC_VERIFIED | 数量合理且与股票 universe 近似勾稽 | spot 派生 | ERROR |
| 3 涨停 | `stock_zt_pool_em()` | DOC_VERIFIED | 目标近期交易日可取、字段完整 | 无可靠历史补回则保留已有快照 | ERROR |
| 3 炸板 | `stock_zt_pool_zbgc_em()` | DOC_VERIFIED | 同上 | 同上 | ERROR |
| 3 跌停 | `stock_zt_pool_dtgc_em()` | DOC_VERIFIED | 同上 | 同上 | ERROR |
| 4 行业板块 | `stock_board_industry_name_em()` | DOC_VERIFIED | 行数>阈值、代码名称非空、涨跌幅可解析 | 保留前次，不冒充当日 | ERROR |
| 4 概念板块 | `stock_board_concept_name_em()` | DOC_VERIFIED | 同上 | 同上 | ERROR |
| 5 个股资金 | `stock_individual_fund_flow_rank("今日")` | DOC_VERIFIED | 主力净流入字段存在、数量正常 | 无口径等价源则 ERROR | ERROR |
| 5 行业/概念资金 | `stock_sector_fund_flow_rank()` | DOC_VERIFIED | TOP 排序与符号校验 | 无口径等价源则 ERROR | ERROR |
| 6 北向季度SH | `https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh` | HTTP GET 已核验 | 200、Shareholding Date、表格行数>0 | 重试；无则保留上季 | STALE/ERROR |
| 6 北向季度SZ | `https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz` | HTTP GET 已核验 | 同上 | 同上 | STALE/ERROR |
| 6 北向日度成交 | HKEX Historical Daily 动态页 | **V1 不启用** | 不做上线阻断测试 | 无 | UNAVAILABLE |
| 6 北向活跃股 | HKEX Historical Daily 动态页 | **V1 不启用** | 不做上线阻断测试 | 无 | UNAVAILABLE |
| 7 SSE 两融汇总 | `stock_margin_sse()` | DOC_VERIFIED | 目标日记录、金额>0、字段齐全 | 已验收 SSEOfficialAdapter | PENDING/STALE/ERROR |
| 7 SSE 两融明细 | `stock_margin_detail_sse()` | DOC_VERIFIED | 融资偿还额、融券偿还量存在 | 同上 | ERROR |
| 7 SZSE 两融汇总 | `stock_margin_szse()` | DOC_VERIFIED | 目标日记录、字段与单位核对 | 已验收 SZSEOfficialAdapter | PENDING/STALE/ERROR |
| 7 SZSE 两融明细 | `stock_margin_detail_szse()` | DOC_VERIFIED | 代码、融资买入、融券卖出等字段 | 同上 | ERROR |
| 8 板块成分 | `stock_board_*_cons_em()` | DOC_VERIFIED | 配置代码与 expected_name 一致、成分>0 | 不自动换近似板块 | ERROR |
| 8 板块历史 | `stock_board_*_hist_em()` | DOC_VERIFIED | 至少 61 个有效交易日 | 使用已归档快照逐步补齐 | ERROR |
| 9 总结规则 | 无外部接口 | LOCAL | 固定 fixture 结果可重复 | 降级模板 | ERROR |
| 交易日历 | `tool_trade_date_hist_sina()` + 本地年度日历 | 辅助 | 历史日期覆盖 + 市场二次验证 | SSE/SZSE 年度休市配置 | ERROR |

## 39.3 上线前固定测试

### A. 历史可回查接口

使用：

```text
SMOKE_HISTORY_DATE = 2026-07-17
```

适用于支持历史日期的：

```text
指数日线
国证日线
两融历史
板块历史
```

### B. 仅近期/当日接口

使用：

```text
SMOKE_LATEST_DATE = 最近一个已收盘交易日
```

适用于：

```text
stock_zh_a_spot_em
涨停/炸板/跌停池
今日资金流
板块实时列表
```

### C. HKEX 季度

不以“今天”作为持仓日期。

验收：

```text
GET 页面
→ 解析页面给出的 Shareholding Date
→ 验证该日期为最近已发布季度末
→ 表格行数 > 0
```

## 39.4 发布门槛

生产启用一个 Adapter 之前必须：

```text
DOC_VERIFIED
+ RUNNER_VERIFIED
+ unit conversion test
+ schema test
+ stale-date test
+ empty-response test
+ retry test
```

否则：

```text
enabled = false
```

---

# 40. V1.1 修订记录

相对 V1.0，本版锁定以下变化：

1. 北向 2024-08-19 后生产模式从“成交+持仓”收紧为 `QUARTERLY_ONLY`。
2. HKEX 季度持仓给出可直接 GET 的 SH/SZ 页面；Historical Daily 动态接口不进入 V1 自动链路。
3. AKShare 两融接口明确区分 `DOC_VERIFIED` 与 `RUNNER_VERIFIED`。
4. 国证指数明确使用纯 6 位 `symbol`；北证50主路径固定 `bj899050` 日线。
5. 静态数据唯一目录改为 `web/public/data/`，构建复制到 `web/dist/data/`。
6. 2026-07-17 Excel 作为首个 Legacy 基线，北向原值放入 `legacyImportedFields`。
7. 增加 Windows Task Scheduler 本地降级/开发方案与依赖安装基线。
8. 主赛道给出 BK1139、BK0428、BK1216、BK1036、BK1134 的 V1 代理定义。
9. 半导体/AI算力明确 50/50 链式收益，资金/成交按成分股并集去重聚合。
10. 模块9增加 10 条确定性规则及数据缺失/Legacy 降级。
11. 增加全模块接口可用性验证清单和生产发布门槛。
