# P1 研究：主力资金流历史数据免费可回补源验证

- 窗口：2026-07-20 ~ 2026-08-13 行业/概念/个股主力净流入 TOP10 历史回补（范本要求六类榜单：行业/概念/个股 x 净流入TOP10 / 净流出TOP10）
- 现状：当日可用（东财被封时降级 THS）；历史无源。已知：东财 push2 主站被封、THS 无历史资金流。
- 探测方式：requests（项目 .venv），timeout=25，Session.trust_env=False 直连（绕过代理/env），最多 3 个网络探测。临时脚本 smi/tmp/probe_fundflow.py（未提交）。

---

## 一、三个探测的实测证据

### 探测1：东财历史行业资金流日线 API【可用】
- 请求：GET https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=20&klt=101&secid=90.BK0475&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55
- **HTTP 200，elapsed≈3.44s**
- 响应首300字符：
  {"rc":0,"rt":22,"svr":...,"data":{"code":"BK0475","market":90,"name":"银行Ⅱ","klines":["2026-07-20,367011584.0,200677120.0,-567688960.0,-309733376.0","2026-07-21,-2870245376.0,...",...]}}
- 结论：
  - 接口存活且返回**真实历史每日资金流时间序列**（klt=101 日线，lmt=20 返回 20 根日K；日期从 2026-07-20 开始，覆盖回补窗口起点）。
  - **关键：主机 push2his.eastmoney.com 与已被封的 push2.eastmoney.com 主站不同，当前未被封。**
  - 字段顺序（fields2=f51,f52,f53,f54,f55）：f51=日期，f52=主力净流入（元），f53=小单净流入，f54=中单净流入，f55=大单净流入。探测值自洽（07-20 主力净流入约 +3.67 亿，方括号数据相互勾稽）。
  - 注意：任务备注称 BK0475=电力，实测返回 name=“银行Ⅱ”。即该 secid 在东财板块体系对应**银行**板块——**备注板块名有误，但接口与 secid 用法本身有效**。回补时应按板块代码清单核对名称，不得盲信备注。
  - 局限：该接口是按单板块（单 secid）拉自身历史序列，**不直接返回“某历史日期的排行”**。构建 TOP10 需枚举 secid 后按日排序（见实现方案），本轮 3 探测内未做端到端排行验证。

### 探测2：东财数据中心“资金流历史”接口【失败】
- 请求：GET https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_FUND_FLOW_INDUSTRY&columns=ALL&filter=(TRADE_DATE='2026-08-13')&pageNumber=1&pageSize=10
- **HTTP 200（业务层失败），elapsed≈2.17s**
- 响应：{"version":null,"result":null,"success":false,"message":"报表配置不存在,RPT_FUND_FLOW_INDUSTRY","code":9501}
- 结论：该报表名配置不存在（接口本身在，但 reportName 无效/已改）。**候选源不可用，排除。**

### 探测3：同花顺问财历史查询【失败，符合预期】
- 请求：POST https://www.iwencai.com/customized/chart/get-robot-data
- body：{"question":"2026年8月13日行业板块主力净流入排行","perpage":10,"page":1}
- **HTTP 401，elapsed≈1.72s**（快速失败）
- 响应：{"code":0,"msg":null,"data":{"captcha_url":"http://www.iwencai.com/ac_verification/captcha/?host=..."}}
- 结论：问财套验证码/登录墙，无凭证直接 401。**不可作免费自动化历史源，排除。**

---

## 二、结论：是否有可用免费历史资金流源

**有，存在一个可用免费源。**

可用源：`push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`（东财历史资金流日线接口，主机与已封 push2 主站不同，当前连通）。

- 能给 07-20~08-13 行业/概念/个股主力净流入**按日历史基础值**：可以（单板块单接口按日拉取，klt=101 日线，lmt 调大（如 40+）可覆盖整窗）。
- 能给“某历史日的行业/概念/个股主力净流入 **TOP10 排行**”：可以，但属**构建式**——需“枚举 secid → 拉各自序列 → 按目标日主力净流入排序取 TOP10”。未探测到 push2his 上直接返回“历史某日排行榜”的现成接口（受 3 探测上限约束，未验证排行接口）。

诚实边界：
- 单板块历史序列已实测可用；“历史日排行”最终形态需“枚举+排序”实现后做一次端到端验收（本轮 3 探测内无法做到）。
- 免费源受东财风控影响（当前 push2his 未被封；但历史曾封主站 push2，若 push2his 后续也被封则免费路线失效，需回退）。
- 探测2/3 确认不可行：datacenter 报表名失效、问财 401 验证码墙。

---

## 三、推荐实现方案与 method 命名

### 方案 A（推荐，免费，基础可行性已实测）
- 数据源：push2his.eastmoney.com fflow daykline（klt=101 日线）。
- 步骤：
  1. 维护三份 secid 清单：行业板块（90.BKxxxx，如 90.BK0475）、概念板块（90.BKxxxx）、个股（含市场前缀，如 1./0. 等）。
  2. 对每 secid 调 /api/qt/stock/fflow/daykline/get（lmt>=40&klt=101&fields2=f51,f52,f53,f54,f55），取 klines 序列。
  3. 按目标历史日（07-20~08-13）切出当日 f52（主力净流入）。
  4. 在行业/概念/个股三个域内分别：降序取主力净流入 TOP10（净流入榜）、升序取 TOP10（净流出榜）→ 六类榜单。
  5. 落库为“日期 x 板块/个股 x 主力净流入”历史明细，页面按日渲染；当日逻辑仍可保留 THS 降级兜底。
- 命名建议（沿用现有 fetch/backfill 风格，前缀 fa/ff 基金流）：
  - `fundflow_backfill_history(dstart, dend, source="eastmoney_push2his")` —— 全量回补入口。
  - `_em_ff_daykline(session, secid, lmt)` —— push2his daykline 单板块拉取。
  - `_rank_by_date(series_map, date, topn)` —— 按日排序取 TOP10。
  - 缓存键：`ff:{industry|concept|stock}:{secid}:{date}:main_net`。
- 验收：任取一历史日，抽查若干板块/个股当日值与东财网页或第三方人工交叉核验一次。

### 方案 B（保底/诚实降级，若方案 A 之后被风控）
- 不做 07-20~08-13 历史：历史日 fundFlow 保持 UNAVAILABLE + 标注原因。
- 展示口径：历史日卡片显示“历史资金流无免费源”标注，不造假数据；仅当日资金流榜单展示。
- 非免费源需用户批准后引入（付费数据服务/授权资金流历史接口，或人工从东财页面导出），本轮未探测。

---

## 附注
- 探测脚本：smi/tmp/probe_fundflow.py（临时，不提交）。
- 本轮网络探测恰好 3 次（P1 push2his、P2 datacenter、P3 iwencai）；早前两次 TypeError 为本地参数写法问题（trust_env 应设在 Session 上），未触网，不计入探测配额。
