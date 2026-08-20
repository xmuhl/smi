# SMI R13 送审请求（源码 + 方案复核）

## 项目

SMI — A股收盘全景 Web 看板。Python(AKShare) 采集 → JSON 快照 → Vue3 前端 → Cloudflare Pages 双域托管
（smi-6s2.pages.dev / smi.gorestart.cn）。9 大模块：marketIndex / turnover / sentiment /
sectorPerformance / fundFlow / northbound / margin / tracks / summary。

## 本轮送审范围

- main HEAD = d8d9597（feat/p1-collector-revamp 已合入 main）
- R12 变更（f56e28d）：①部署链路修复（wrangler 4.122.0 需 Node≥22，GitHub Actions 全部升级 Node 22）；
  ②主赛道 tracks 动态化（config/tracks.yaml v3.0：近 5 日成交额全市场排名 ≤8 且当日净流入>0 的行业板块
  动态候选 + 4 条种子赛道合并去重；数据底座 industry-universe-snapshot 归档；评分四维度 25/35/25/15）；
  ③CI 根因修复（pytest sys.modules["akshare"] 泄漏导致后续测试真实联网 16 分钟/个）。
- 自动更新链路：close-snapshot（工作日 16:23 CST）/ archive-raw（16:35）/ t1-reconcile（10:17/18:17）/
  manual-backfill / ci，全部数据写入共用 concurrency group smi-data-write。

## 当前线上实测状态（2026-08-20）

| 日期 | 模块异常 |
|---|---|
| 08-20 | margin=PENDING（T+1 正常）、tracks=UNAVAILABLE（coveragePct=71.4 < 阈值 80，errors=[HS300_SEED_UNAVAILABLE]，decision=TRACKS_INSUFFICIENT） |
| 08-19 | margin=ERROR、tracks=UNAVAILABLE |
| 08-18 | turnover=ERROR、sentiment=PARTIAL、fundFlow=UNAVAILABLE、tracks=UNAVAILABLE |

tracks 持续 UNAVAILABLE 是线上「部分板块获取失败」的直接原因：R12 动态化后 coverage 常态 ~71-82%，
对阈值 80 余量极小，叠加 excessReturn20d 无 HS300 归档源（HS300_SEED_UNAVAILABLE，诚实缺口），
fail-closed 触发 TRACKS_INSUFFICIENT。

## 已知边界（产品裁决 v1，docs/acceptance/historical-profile.json）

- sentiment：riseCount/fallCount/flatCount 无免费历史源 → 历史 PARTIAL/UNAVAILABLE
- fundFlow：stockInflowTop10/OutflowTop10 无历史源；东财 push2his 主机级封禁 → 历史 UNAVAILABLE
- tracks：excessReturn20d 无 HS300 归档源；动态候选 close 历史自入选次日起累积；涨停池分子（东财）与
  universe 分母（THS 家数）命名体系混合，未对齐时情绪维 fail-closed
- 07-20~07-24：涨停池保留窗口外不可恢复

## 请复核要点

1. R12 tracks 动态化方案（选池规则、双底座口径、四维度评分、fail-closed 策略）是否合理、有无逻辑漏洞；
2. tracks coverage 阈值 80 对常态 82.4% 仅 2.4pp 余量的 fail-fast 设计是否过激，有何改进建议；
3. 部署/CI 链路修复（Node 22、concurrency group、自检口径）是否完备；
4. 代码级复核（collector/ 采集器、netguard 护栏、tools/acceptance 验收器、web/ 前端）。

## 两个咨询问题（用户关注）

Q1：线上网页部分板块显示「获取失败」，除上述 tracks UNAVAILABLE 与 margin T+1 时序外，
是否还有我们未识别的系统性原因？

Q2：当前站点（Cloudflare Pages，pages.dev 与自定义域 smi.gorestart.cn 均解析至 Cloudflare anycast
IP 172.66.45.12/172.66.46.244）在大陆部分网络（尤其福州地区三大运营商）无法访问。
请评估：GitHub Pages 是否为可行替代？中国大陆地区有哪些可用（最好免费/低成本）的静态网页托管方案？
域名 gorestart.cn 尚未 ICP 备案这一约束请一并考虑。

## 附件

- SMI_R13_source_20260820.zip：完整源码树（排除 .git/.venv/node_modules/tmp/dist），
  含 collector/ tools/ config/ docs/ review/ ops/ web/ .github/workflows/，
  以及最近 3 个交易日（08-18~08-20）数据样本与 archive jsonl 底座样本。
