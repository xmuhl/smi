# SMI R12 P0.2 复审：P0.1 九项 NOT_CLOSED 的收口交付

- 轮次：R12 P0.2（对 R12 P0.1 HOLD 的第二修订轮）
- 送审输入 commit：594512a（分支 feat/p0-acceptance-baseline；基线报告独立提交 59cac97）
- 前置复核链：R12 P0 → HOLD(9项) → R12 P0.1 → HOLD(9项：P0-005 已 CLOSED + 新增 P01-010)
- 基线 provenance：evaluatedCommit=594512a、dirty=false（两提交法，P0-009 语义）

## 一、逐项收口（对照 P0.1 报告的 9 项 NOT_CLOSED）

| 编号 | 收口内容 | 证据位置 |
|---|---|---|
| P0-001 断言假阳性 | ① _ref_match_items_by_name fail-on-missing（缺期望项即 FAIL，禁止 continue）；② declared/consumed 覆盖率自检（_count_assertion_leaves 展开计数，declared!=consumed → FAIL 并写明数值）；③ northbound reference 消费 netBuyTop10/netSellTop10 全表、margin 消费 8 值（嵌套 {"value":...} 自动解包）、summary 分支新增（segmentCount/riskWarningMustContain/MustContain/MustNotContain 通用执行、*Reason 为文档键）；④ 07-17 数据补第 9 项指数"科创综合"（000680，1938.77/-8.13%），marketIndex 9 项断言全部精确执行 | accept.py::_run_reference_assertions / _ref_* 系列；07-17.json marketIndex |
| P0-002 单一真源 | ① dispatch 表改为 ruleId -> {supportedVersions, handler} 真实路由：ruleId 未知或 ruleVersion 不受支持 → 启动自检失败退出码 3（实测触发过：margin ruleVersion 升 2 时自检拦截，随后显式扩支持版本）；② 所有复杂 handler 开头统一 _validate_field_values(mod, spec.fields)；③ 状态豁免声明在标准：margin 四余额字段带 skipStates:["PENDING"]；④ northbound/tracks 的 sourceSystem/officialDisclosureCompatible/effectiveFrom/effectiveTo 均由通用引擎消费 | accept.py::startup_self_check / _COMPLEX_HANDLERS / check_*；standard margin fields |
| P0-003 北向 PIT | OFFICIAL_REPLACEMENT 分支强制 quarterlyHolding.asOf 与 publishedAt 必须存在、可解析（ISO date/datetime 截断比较）、asOf<=tradeDate 且 publishedAt<=tradeDate；INV-NORTHBOUND-PIT 对缺失同样返回 false（不再只拦未来值） | accept.py::check_northbound / run_cross_module_invariants |
| P0-004 跨口径契约 | MISMATCH 分支强制 crossMethodReference 结构化块：previous/delta/changePct 三个有限数值成组、nonComparable===true、currentMethod/previousMethod 非空、内部算术恒等（|delta-(today-prev)|<=0.01、|pct-delta/prev*100|<=0.01）；标准 fields 同步声明 | accept.py::check_turnover；standard turnover fields |
| P0-005 | （上轮已 CLOSED，未动） | — |
| P0-006 tracks 时序/区间/派生 | ① item.date 必须存在且 == tradeDate；② effectiveFrom<=tradeDate<=effectiveTo（仅参考日 legacy 豁免）；③ redStockRatio 解析 0~100；④ 文本字段执行标准 rejectedPlaceholders；⑤ sourceSystem required；⑥ 非 legacy FINAL 时用 collector.calculators.tracks.score_tracks 对 items 重算 score/decision 并与快照值比对（score 容差 0.1、decision 必须相等；重算 INSUFFICIENT 而快照 FINAL → FAIL）；参考日(legacy)由 reference assertions 覆盖 | accept.py::check_tracks；standard tracks fields/items |
| P0-007 summary 事实锚点 | ① marketEnvironment↔turnover：COMPARABLE 时禁"暂无/不可比/无可比较"且按 volumeState 要求含 放量/缩量/平量；② trackConclusion↔tracks：4 赛道名前缀全含 + 判定词至少 2 个；③ margin 段↔margin（FINAL 须含融资/两融，PENDING 须含待披露/参考/T+1）；④ northbound 段↔northbound（legacy 须含净流入/净流出，OFFICIAL 须含停发/季度/披露）；⑤ 07-17 数据修正：marketEnvironment 改为与 COMPARABLE 一致文案（24035.65/26549.58/+2513.93/+10.46/放量），northbound 段补净流出数值（156.32/沪-68.54/深-87.78） | accept.py::check_summary；07-17.json summary |
| P0-008 9 条 invariant | 9 个 id 全部产出 results key（含 INV-ENUM-SOURCE-METHOD，按标准枚举校验 source/method）；启动自检强制 标准 ids == 代码 ids；DATE 递归扫描 tracks.items.date / margin.latestPublishedReference.dataDate / northbound.quarterlyHolding.asOf+publishedAt | accept.py::run_cross_module_invariants；baseline invariants 9/9（07-17 全 true） |
| P0-009 溯源 | provenance 新增 evaluatedCommit + dirty；reportCommitSemantics 说明两提交法；本轮已按两提交执行：输入树 594512a → 干净树跑基线（evaluatedCommit=594512a、dirty=false）→ 报告单独提交 59cac97 | baseline-report.json.provenance |
| P01-010 证据口径 | 统一表述：20 tests = 18 negative mutation + 2 positive regression；本轮送审的模块失败集合/计数直接取自 baseline-report.json 自动生成（见下） | 本文件 §二 |

## 二、新基线（accept.py P0.2 + 修正后 07-17，evaluatedCommit=594512a）

- **2026-07-17：PASS（9/9 模块 + 9/9 不变量）**——参考日全部 referenceAssertions（311→含新增 9 项指数/北向全表/margin 8 值/summary 断言）精确执行且覆盖率自检通过；
- 2026-08-14：FAIL，失败模块={sentiment(缺 limitSealRatePct/maxLimitUpStreak), northbound(mode 枚举+sourceSystem+PIT 字段，P1 数据工作), tracks(UNAVAILABLE，P2)}；
- 2026-07-20：FAIL，={turnover(缺 crossMethodReference 块，P1 回补), sentiment, sectorPerformance, fundFlow, northbound, tracks, summary}；summary 失败原因=riskWarning 中文字符占比 0.32 + marketEnvironment 含"暂无"（P1 回补将重生成文案）；
- 2026-07-21~08-13：FAIL，={sentiment, sectorPerformance, fundFlow, northbound, tracks, summary}；
- 模块失败日期数：marketIndex 0 / turnover 1 / sentiment 20 / sectorPerformance 19 / fundFlow 19 / northbound 20 / margin 0 / tracks 20 / summary 19；
- 测试：tools/acceptance/test_accept.py 20/20（0.26s）；collector/tests/test_core.py 86 项全绿（P0.2 修复了 lineage 负向用例对 legacy 9 指数的依赖）；test_sectors_history.py 6 项（P1A 范围，见 §三）。

## 三、并行进展（供上下文，不在本轮评审范围）

P1 分支 feat/p1-collector-revamp 已含两处采集器修复：margin 未披露 fail-closed（SZSE "Length mismatch" 分类为 NOT_YET_PUBLISHED，D0→PENDING/t1→STALE，含 3 个新测试）、sectorPerformance 历史分支（THS 板块历史指数 → 任意历史日行业/概念 TOP5/BOTTOM5，method=THS_HISTORICAL_INDEX）。后续 P1 将继续 sentiment/资金流历史源研究与北向口径数据落地，然后全量回补 20 个历史日。

## 四、请复核

1. 上轮 9 项（P0-001/002/003/004/006/007/008/009/P01-010）是否可判 CLOSED；
2. 若有新变体请按新编号登记；
3. 若收敛请明确写"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
