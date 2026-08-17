# SMI 历史数据覆盖能力 Profile（产品裁决 v1）

> 决策日期：2026-08-17
> 决策类型：PRODUCT_ACCEPTED_KNOWN_BOUNDARIES（历史覆盖范围产品裁决）
> 参考日：2026-07-17（保持完整验收标准 template-standard.json version=2）
> 机器可读版：`docs/acceptance/historical-profile.json`

## 核心承诺

**历史日（07-20 起）不承诺与 07-17 参考日完整基准等效。**
参考日维持原有完整验收；历史日按本 profile 的能力范围验收，
缺失字段不因"诚实缺口"判 FAIL，而是接受 PARTIAL/UNAVAILABLE 已知边界。
此项声明取代此前"历史全量回补达到 07-17 完整效果"的口径。

## 各模块历史能力

| 模块 | 最早支持日 | 缺失字段 | 历史状态映射 | UI 提示 |
|---|---|---|---|---|
| sentiment | 2026-07-20 | riseCount/fallCount/flatCount | 缺失→PARTIAL | 『市场宽度（涨跌家数）无历史源』 |
| fundFlow | 2026-07-20 | stockInflow/OutflowTop10 | 四榜单缺→UNAVAILABLE；补→FINAL；stock 缺→PARTIAL | 『资金流历史榜单部分缺失』 |
| tracks | 2026-07-20 | mainNetInflow/excessReturn20d/redStockRatio 等 | 缺失→UNAVAILABLE | 『赛道量化指标历史不可用』 |

## 不可恢复区间（产品裁决）

- **2026-07-20 ~ 2026-07-24**（影响 sentiment/tracks）：东财涨停池保留窗口仅覆盖 ~07-27 起，
  limit-up-pool archive 无数据，**不可恢复**。

## 附加说明

- fundFlow push2his 主机 2026-08-15 起主机级封禁为**临时运营缺口**，解封可恢复行业/概念四榜单；
  个股两榜单为**结构性能力缺口**（无可用历史批量源），两者必须区分。
- 前端 UI 对历史日缺失字段按上表明确展示提示，禁止显示为"加载失败"。
- 本 profile 为 versioned（v1），后续产品决策变更时升级版本，不静默修改。
