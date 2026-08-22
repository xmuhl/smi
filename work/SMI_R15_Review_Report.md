# SMI R15 复核报告（最终收敛轮）

- 项目：SMI — A股收盘全景 Web 看板
- 基线：R14 送审 HEAD `0e2cfbf`
- 复核日期：2026-08-22
- 复核性质：只读复核 + 独立运行验证（pytest / shell 自测 / typecheck / acceptance 跑批）

---

# 1. 总体结论

## 1.1 裁定

**PASS，本轮收敛。**

R14 遗留 6 项 NOT_CLOSED 全部 CLOSED：

| 编号 | R15 裁定 | 结论摘要 |
|---|---|---|
| R14-P1-01 | **CLOSED** | spawn registry 化：装饰期登记原始函数、子进程按字符串 key 解析直接调用、全路径句柄释放；真实装饰器语法 + 强制 spawn 4 条回归，且在 win32 真实 spawn 路径本机通过 |
| R13-P2-01 | **CLOSED** | 健康日清零 exit streak（FAIL→PASS→FAIL 不出池）；minHistoryDays 升级为真实评分池门禁（WARMING_UP 无成熟 score/decision、不进 coverage 与 D0，全预热日 fail-closed）；universe 完整性门禁（0.5×峰值）先行于"缺行=exit hit" |
| R13-P3-04 | **CLOSED** | optional 语义严格化：absent=warning / present=exact-match required；实现抽取为可离线自测脚本，三态+required mismatch 4 场景回归接入 CI |
| R14-P2-01 | **CLOSED** | v4 产品裁决落地：allowedStatuses + 状态-判定矩阵 + readinessMap；WARMING_UP/动态候选/诚实缺口契约全部编码；正例 3 + 负例 7 回归；08-20 生产日 9 模块全 PASS 证明 acceptance 恢复可信 PASS 语义 |
| R14-P3-01 | **CLOSED** | 前端类型补齐 TRACKS_DEGRADED/TRACKS_INSUFFICIENT/dataReadiness/historyDays/coverage 三元组/warmingUpBoards；WARMING_UP 预热徽标 + 判定弱化 + DEGRADED 降级说明；vue-tsc 通过 |
| R14-P3-02 | **CLOSED** | 指针存在性单调检查（FINAL⇒CLOSE_COMPLETE⇒CAPTURED）+ 2 条负向回归 |

## 1.2 本轮新增问题（送审方自查 + 评审发现，均已修复）

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| R15-N01 | P2 | **已修复** | `reconcile_turnover_chain` 对 Legacy Excel 范本日（07-17）无豁免：manual backfill（610c854）把 Excel 记录的跨日比较事实 null 化为 PREVIOUS_UNAVAILABLE 并覆写 summary 叙述，破坏 referenceAssertions 金标（2 条存量测试失败的根因）。修复：LEGACY_UNKNOWN 当日豁免门禁 + 数据外科恢复（revision 8）+ 回归测试 |
| R15-N02 | P3 | **已修复** | `collect_tracks` 死变量 `all_scores_present` 清理 |
| R15-N03 | P3 | **已修复** | template-standard notes 滞后旧枚举文案更正 |

**新增问题修复后全量验证通过，无遗留 NOT_CLOSED。**

---

# 2. 独立复验情况

本轮在调用方本机（win32 / Python 3.13.5）直接运行验证，非仅静态审阅：

| 验证项 | 命令 | 结果 |
|---|---|---|
| 全量 Python 测试 | `pytest -q collector/tests tools/acceptance/test_accept.py` | **278 passed, 1 skipped** |
| spawn 专项（真实 Windows spawn） | `pytest collector/tests/test_netguard_spawn.py -v` | 4 passed |
| 归档同步自测 | `bash tools/deploy/test_verify_archive_sync.sh` | 4/4 PASS |
| 前端类型 | `npm run typecheck` | 通过 |
| 全量验收 | `acceptance --all` | PASS=2（07-17、08-20）；23 日失败全部在 historical-profile 披露边界内 |
| 基线对照 | R14 基线 worktree 复跑 2 条失败测试 | 确认 R15-N01 为存量问题、非本轮引入 |

## 2.1 关键对抗性复验结论

1. **spawn 真实路径**：win32 平台 `_pick_context()` 自然返回 spawn context；`test_spawn_real_decorator_*` 三条在真实 spawn 子进程下执行（非 forced 模拟），证实生产 `@net_guard` 装饰入口在 Windows 可用。
2. **迟滞语义最小反例**：D1 入池 → D2 失败(streak=1) → D3 恢复(streak 清零) → D4 失败(streak=1) → 保留池籍；新回归测试固化该行为。
3. **v4 矩阵对生产的适配**：08-20 真实快照 PARTIAL/TRACKS_SUFFICIENT 下 9 模块全 PASS，同时负例证明 SUFFICIENT 低 coverage / DEGRADED 高 coverage 等非法组合仍 FAIL——acceptance 恢复"健康数据必 PASS、非法契约必 FAIL"的区分度。
4. **null 指针链**：final=08-18 + closeComplete=null 现在产生 gap（旧实现错误返回 []）。
5. **optional membership**：本地存在 + 线上 mismatch → 退出码 1（离线自测场景 3）。

---

# 3. 已知边界（不登记新问题）

沿用 R14 边界框架，当前全部披露且未恶化：

1. `coverage_hard_floor_pct=65` 临时标定（R14 边界 #3）；
2. sentiment 22 日 / fundFlow 21 日历史源缺口（historical-profile.json 披露；fundFlow 为 push2his 主机级封禁，解封可恢复）；
3. margin 08-17/18/19、turnover 08-18、northbound 08-17、summary 08-19 为上游采集失败的存量数据状态（R14 边界 #2 延续；08-18 margin 曾 FINAL 成功证明代码路径正常）；
4. tracks 08-14/17/18 失败为 tracks 配置生效区间（2026-08-20 起）之前的历史日，coversTradeDate 防倒灌设计按预期工作。

---

# 4. 最终裁定

```text
R14-P1-01  CLOSED
R13-P2-01  CLOSED
R13-P3-04  CLOSED
R14-P2-01  CLOSED
R14-P3-01  CLOSED
R14-P3-02  CLOSED
R15-N01    已修复（本轮新增，P2）
R15-N02    已修复（本轮新增，P3）
R15-N03    已修复（本轮新增，P3）

当前未闭环总计：0
```

**R15：PASS，代码评审侧收敛。**

后续无需再为当前架构发起评审轮，除非出现：
1. 新交易日 acceptance 出现非已披露边界的 FAIL；
2. 备案/新域迁移触及数据链路（另属域名专项）；
3. SMI 功能引入新模块或改变现有数据契约。

剩余事项转为**人工验收**（见 `SMI_R15_Review_Request.md` §人工验收清单）。
