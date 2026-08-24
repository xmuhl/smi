# SMI 线上数据全量审计报告（2026-07-20 ~ 2026-08-21）

- **审计时间**：2026-08-23（周日）
- **审计对象**：生产站 smi-6s2.pages.dev（双域同源）/data/daily/YYYY/YYYY-MM-DD.json，自 2026-07-20 起全部 **25 个交易日**逐一抓取核验
- **审计方式**：逐日抓取线上 JSON，对 9 大模块提取 status / reason / errors / 榜单条数；与验收器（accept.py）逐日明细交叉核对
- **触发背景**：人工验收发现 08-18 主力资金流向不可用

---

## 一、总矩阵

图例：**F**=FINAL　**P**=PARTIAL（部分可用）　**~**=PENDING（披露在途）　**U**=UNAVAILABLE（不可用）

| 交易日 | 指数 | 成交额 | 情绪 | 板块表现 | 主力资金 | 北向 | 两融 | 主赛道 | 摘要 |
|---|---|---|---|---|---|---|---|---|---|
| 07-20 | F | F | U | F | U | F | F | U | F |
| 07-21 | F | F | U | F | U | F | F | U | F |
| 07-22 | F | F | U | F | U | F | F | U | F |
| 07-23 | F | F | U | F | U | F | F | U | F |
| 07-24 | F | F | U | F | U | F | F | U | F |
| 07-27 | F | F | P | F | U | F | F | U | F |
| 07-28 | F | F | P | F | U | F | F | U | F |
| 07-29 | F | F | P | F | U | F | F | U | F |
| 07-30 | F | F | P | F | U | F | F | U | F |
| 07-31 | F | F | P | F | U | F | F | U | F |
| 08-03 | F | F | P | F | U | F | F | U | F |
| 08-04 | F | F | P | F | U | F | F | U | F |
| 08-05 | F | F | P | F | U | F | F | U | F |
| 08-06 | F | F | P | F | U | F | F | U | F |
| 08-07 | F | F | P | F | U | F | F | U | F |
| 08-10 | F | F | P | F | U | F | F | U | F |
| 08-11 | F | F | P | F | U | F | F | U | F |
| 08-12 | F | F | P | F | U | F | F | U | F |
| 08-13 | F | F | P | F | U | F | F | U | F |
| 08-14 | F | F | F | F | F | F | F | U | F |
| 08-17 | F | F | F | F | F | F | F✚ | U | F |
| 08-18 | F | F | P | F | U | F | F✚ | U | F |
| 08-19 | F | F | F | F | F⚠ | F | F | U | F |
| 08-20 | F | F | F | F | F | F | F | P | F |
| 08-21 | F | F | F | F | F | F | ~③ | P | F |

> ✚ = 本次审计中已自动回补修复；⚠ = FINAL 但榜单不足 10 条（见 F1）；③ = T+1 正常在途，周一晚 cron 自动补。

**结论：指数 / 成交额 / 板块表现 / 北向 / 摘要 五个模块 25 天全部 FINAL，无一缺失。**

---

## 二、不可用清单与根因分析

### 族 A：主赛道 tracks —— UNAVAILABLE ×23 天（07-20 ~ 08-19）｜不可回补

- **现象**：整日空池，reason=TRACK_CRITICAL_INPUT_MISSING，errors 含 HS300_SEED_UNAVAILABLE、RED_RATIO_SOURCE_UNAVAILABLE
- **根因**：tracks 数据底座（industry-universe-snapshot 行业板块全景归档）**2026-08-20 才接入**，此前日期的板块快照物理上不存在且上游 THS 不提供历史回溯 → 完整性门禁不过 → 按 R24 收敛语义 fail-closed 输出诚实空池（人工验收「无数据日清空」决议，设计内行为）
- **判定**：❌ 永久缺口（除非未来引入可回溯的历史板块数据源后立项重建）

### 族 B：主力资金 fundFlow —— UNAVAILABLE ×18 天（07-20 ~ 08-13 共 17 天 + 08-18）｜不可回补

- **现象**：reason=FUNDFLOW_HISTORICAL_FETCH_FAILED，错误为东财 push2his/push2 ConnectionError(RemoteDisconnected) 或 502 Bad Gateway
- **根因链**：
  1. fundFlow 历史回补路径（_collect_fund_flow_historical）**唯一依赖东财 push2his 接口**；
  2. 东财 push2/push2his 已被封禁（2026-08-23 实测：代理与直连均封），历史日重采必然失败；
  3. THS 主力资金接口仅提供**当日**快照，无法取历史日期；
  4. 因此「当时没采到的日子，现在永远补不回来」。
- **为什么前后交易日完好**：08-14 / 08-17 / 08-19 / 08-20 / 08-21 是**当日实时采集**入库（THS_MAIN_FORCE 成功），无需回补；缺的只是事故日与系统上线前的日子。
- **08-18 特别说明**：该日原采集事故导致缺失，其后所有回补尝试均撞上 push2his 封禁——是族 B 中唯一「本可以当天拿到却丢了」的日子，也是本次人工验收报告的问题日。
- **判定**：❌ 免费源范围内不可回补（若未来引入付费源或东财解封，可按日重放）。

### 族 C：情绪 sentiment —— UNAVAILABLE ×5 天（07-20 ~ 07-24）｜不可回补

- **现象**：reason=HISTORICAL_LIMIT_POOL_UNAVAILABLE，整模块无数据
- **根因**：涨跌家数无免费历史源（结构性）；唯一历史替代=东财涨停池归档，而涨停池仅保留最近有限天数，这 5 天已超窗口 → 连涨停池派生字段也不可得
- **判定**：❌ 永久缺口（CLAUDE.md 已知边界表 07-20~07-24 UNRECOVERABLE 同源）

### 族 D：情绪 sentiment —— PARTIAL ×15 天（07-27 ~ 08-13 + 08-18）｜维持展示，属披露边界

- **可用**：非ST涨停/ST涨停/非ST跌停/ST跌停/炸板数/封板率等涨停池派生字段
- **缺失**：riseCount / fallCount / flatCount 涨跌家数——无免费历史源（结构性）
- **判定**：⚠️ 维持 PARTIAL 展示（fail-closed 设计），涨跌家数不可补齐

### 族 E：两融 margin —— 已全部修复 ✅（本次审计动作）

| 日期 | 修复前 | 根因 | 修复动作 | 修复后 |
|---|---|---|---|---|
| 08-17 | PENDING | T+1 数据从未回补 | t1_reconcile --date 2026-08-17 | FINAL balance=26840.96 亿 change=+185.95 |
| 08-18 | FINAL 但 marginBalanceChange=null | change 依赖 08-17 前值，生成时其仍为 PENDING | 前值补齐后联动重算（采集期同公式） | change=+54.63 亿 |
| 08-21 | PENDING | T+1 正常节奏：周五数据周一晚披露 | 无需动作（cron 周一 10:17/18:17 自动处理） | 在途 |

### 特记 F1：fundFlow 08-19 —— FINAL 但两张榜单不足 10 条｜不可回补

- industryInflowTop10 仅 8 条、conceptInflowTop10 仅 5 条（标准 minItems=10）
- **根因**：当日实时采集时 THS 源有效板块数不足（其余板块净额解析无效被诚实剔除），非丢失；历史日无法再走 THS 当日快照 → 数量无法增加
- **判定**：❌ 维持现状（数据真实，只是当日有效板块少；验收 FAIL 属标准刚性）

### 说明：北向 northbound 全部 FINAL

POST_20240819_OFFICIAL_REPLACEMENT 模式：HKEX 于 2024-08-19 起停止披露旧式日度净流入，现展示最近一期季度持仓 + 日度成交额，属官方口径替代而非数据缺失。

---

## 三、本次审计执行的修复记录

| # | 动作 | 结果 |
|---|---|---|
| 0（前轮） | 08-18 turnover 回补 + 08-19 成交额链条重算（1272e5f） | turnover/summary failDates 清零 |
| 1 | 08-17 两融 T+1 回补 | margin FINAL，acceptance margin failDates 2→0 |
| 2 | 08-18 marginBalanceChange 联动重算 | null→54.63，summary 同步重算 |
| 3 | 提交 f371c26 + 强制部署（显式日期防 auto 回采） | 生产站验证生效 |

---

## 四、最终不可回补清单（汇总）

| 模块 | 日期集 | 天数 | 类别 |
|---|---|---|---|
| tracks 主赛道 | 07-20 ~ 08-19 | 23 | 底座未接入，永久缺口 |
| fundFlow 主力资金 | 07-20 ~ 08-13 | 17 | 源封禁，免费范围内不可回补 |
| sentiment 情绪(全模块) | 07-20 ~ 07-24 | 5 | 涨停池窗口外，永久缺口 |
| fundFlow 08-18 | 单日 | 1 | 事故日+源封禁叠加 |
| sentiment 涨跌家数 | 07-27 ~ 08-13, 08-18 | 15 | 无免费历史源，维持 PARTIAL |
| fundFlow 08-19 榜单条数 | 单日 | 1 | 当日有效板块不足，真实数据 |

---

## 五、后续观察建议

1. **周一 08-24 晚**：确认 t1-reconcile cron 自动补齐 08-21 两融；
2. fundFlow 若发现新的免费历史源（或东财解封），可按本清单逐日重放回补；
3. 方案 A（完整概念 universe）落地后，tracks 历史仍无法回溯——缺口性质不变。

---

## 回补附录（2026-08-24）

**sentiment 涨跌家数经 gildata（恒生聚源）『市场涨跌停家数』API 回补**，覆盖原审计清单中全部 20 个缺口日（07-20~07-24、07-27~07-31、08-03~08-07、08-10~08-13、08-18），取数口径为沪深北市场，原始 CSV 留档 `tmp/gildata_breadth_<date>.csv`。

结果：
- **12 日升 FINAL**：07-27~07-30、08-03、08-05~08-07、08-10、08-11、08-13、08-18（涨停池派生字段齐全，补齐涨跌家数后必填字段全齐）
- **3 日维持 PARTIAL**：07-31、08-04、08-12（涨停池派生字段 nonStLimitDownCount/stLimitDownCount 仍缺，诚实缺口不伪造）
- **5 日 UNAVAILABLE→PARTIAL**：07-20~07-24（涨停池窗口外，派生字段仍不可恢复，reason 维持 HISTORICAL_LIMIT_POOL_UNAVAILABLE；涨跌家数已补）

口径声明：gildata 沪深北口径与既有东财/新浪 spot 口径存在约 1% 差异（FINAL 日实测比对确认），数据已标注 `source+=GILDATA`、`spotSource=GILDATA` 及 warnings 说明。suspendedCount 维持 null。

fundFlow 与 tracks 模块本次未动，缺口性质不变。
