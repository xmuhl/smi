# SMI 代码评审迭代收敛报告（R15→R20 最终）

- 日期：2026-08-22
- 最终裁定：**R20 收敛 —— 0 NOT_CLOSED，ChatGPT 侧已收敛**（work/SMI_R20_Review_Report.md）
- 提交链：0e2cfbf(R14基线) → ebac337(R15) → a3a706c(R16) → ab76aeb(R17) → f2b1813(R18) → dbc0fae(R19) → 8757313(R20)

## 迭代轨迹

| 轮 | 送审 | 裁定 | 关键事件 |
|---|---|---|---|
| R15 | R14 六项修复 + 自查 N01~N03 | HOLD（4/6 CLOSED） | 新增 R15-P2-01（包缺 N01 文件）/ R15-P3-01（CI 缺 acceptance）；R13-P2-01 universe 门禁两漏洞、R14-P2-01 v4 矩阵六漏洞 |
| R16 | 上述 4 项修复 | HOLD（4 项全 CLOSED） | 新增 R16-P2-01：configVersion 自证循环（快照自报版本决定验收强度） |
| R17 | 权威版本时间表 | HOLD（R16-P2-01 CLOSED） | 新增 R17-P2-01：cutoff 后非数值版本 fail-open（解析失败静默 pass） |
| R18 | numericOnly fail-closed | HOLD（仍 NOT_CLOSED） | "严格 x.y"解析不严格：3.2.1/3.2./4/尾空白/前导零可绕 |
| R19 | 唯一严格解析器 ^x.y$ | HOLD（仍 NOT_CLOSED） | 正则 $ 放过尾部换行（3.2\n）；\d 是 Unicode 数字类（全角 3２.2） |
| R20 | fullmatch + [0-9] + 段长≤9 | **收敛** | R17-P2-01 CLOSED；0 新增 |

## 最终契约要点（本轮迭代沉淀）

1. **universe 完整性门禁**：绝对下限 45（已验证 90 板块快照之半）+ 因果前向可信峰值（只有完整日抬高基线，未来峰值不回溯改写历史证据资格）；
2. **tracks_V2 v4 穷举状态机**：status⇄decision⇄coverage 全配对 + strict 字段契约（≥3.2：dataReadiness/阈值透传/warmingUpBoards 必填且与 decisionContract 一致；formal 仅计 READY/DEGRADED；WARMING_UP 四字段全检）；
3. **权威版本时间表**：≤2026-08-20 精确白名单（legacy/1.0/2.0/3.0/3.1/3.2）；≥2026-08-21 唯一严格解析器（ASCII fullmatch [0-9]，段长≤9）+ minConfigVersion=3.2，版本降级旁路全形态闭合；
4. **Legacy 范本日保护**：reconcile 按方法口径豁免 LEGACY_UNKNOWN 当日，07-17 Excel 金标恢复（revision 8）；
5. **CI 门禁**：collector 测试 + acceptance 契约测试 + archive 同步自测三段全绿。

## 最终验证（2026-08-22）

- pytest **299 passed + 1 skipped**；
- acceptance --all：PASS=2（07-17 范本日、08-20 生产日，9 模块全 PASS），其余 23 日在 historical-profile 已披露边界内；
- shell 自测 4/4；vue-tsc 通过。

## 人工验收清单（转人工，自动化不可替代）

- [ ] **HA-A** push 后观察下一个交易日 close-snapshot / archive-raw workflow 全绿，线上 latest.json 与本地 tradeDate+SHA-256 全等
- [ ] **HA-B** 本机手动跑一次任一 @net_guard 采集入口做生产烟测（spawn 路径留证）
- [ ] **HA-C** 前端目检：预热徽标「预热」/TRACKS_DEGRADED 降级提示/历史日 tracks 提示渲染正常
- [ ] **HA-D** 部署后抽查线上 07-17 页面 turnover 放量字段与 Excel 范本一致
- [ ] **HA-E** 跟踪 fundFlow push2his 主机封禁；coverage floor=65 满 20~30 交易日后回放重标
