# SMI R15 送审请求（Review Request）

- 送审内容：R14 裁定 6 项 NOT_CLOSED 的修复 + 本轮自查新增 3 项修复
- 基线 HEAD：`0e2cfbf`（R14 送审时 HEAD）
- 送审包：`work/SMI_R15_source_20260821.zip`（最小清单 §19 + 本轮完整 diff）
- 日期：2026-08-22

## 1. 送审范围

按 R14 §19 最小复送清单：

1. `collector/modules/tracks.py` — R13-P2-01 三阻断点修复（streak 清零 / WARMING_UP 真门禁 / universe 完整性门禁）
2. `collector/netguard.py` — R14-P1-01 spawn registry 化 + 全路径句柄释放
3. `.github/workflows/archive-raw.yml` — R13-P3-04 自检抽取为脚本调用
4. `docs/acceptance/template-standard.json` — R14-P2-01 v4 契约（allowedStatuses + decisionContract）
5. `tools/acceptance/accept.py` — v4 状态-判定矩阵 + WARMING_UP 契约 + R14-P3-02 null 指针链
6. `web/src/types/smi.ts`、`web/src/modules/TrackMonitorPanel.vue` — R14-P3-01 前端契约跟进
7. 新增/修改测试：`test_netguard_spawn.py`（新）、`test_tracks_dynamic.py`、`test_acceptance_identity.py`、`test_accept.py`、`test_core.py`、`tools/deploy/test_verify_archive_sync.sh`（新）
8. 新增：`tools/deploy/verify_archive_sync.sh`、`config/tracks.yaml`(3.2)、`docs/acceptance/historical-profile.json`、`.github/workflows/ci.yml`
9. 数据修复：`web/public/data/daily/2026/2026-07-17.json`（R15-N01 恢复，revision 8）+ `collector/jobs/reconcile_turnover_chain.py`（Legacy 豁免门禁）
10. 说明文档：`SMI_R15_Fix_Notes.md`、`SMI_R15_Review_Report.md`（本目录）

## 2. R14 §19 必含负向回归对照

| R14 要求 | 落点 | 结果 |
|---|---|---|
| exit：FAIL→PASS→FAIL 不得出池 | `test_tracks_dynamic.py::test_r13_p2_01_exit_streak_resets_on_healthy_day` | PASS |
| forced spawn + 真实 decorator syntax | `test_netguard_spawn.py`（4 条；win32 本机即真实 spawn） | PASS |
| optional membership absent/match/mismatch 三态 | `tools/deploy/test_verify_archive_sync.sh`（+required mismatch） | PASS |
| final!=null + closeComplete=null 必须 identity FAIL | `test_acceptance_identity.py` 2 条 | PASS |
| tracks PARTIAL/SUFFICIENT 与 PARTIAL/DEGRADED 正例 | `test_accept.py::test_tracks_v4_partial_sufficient_positive` / `..._degraded_positive`（另 UNAVAILABLE 正例） | PASS |
| frontend typecheck 覆盖 TRACKS_DEGRADED/WARMING_UP | `npm run typecheck`（smi.ts 枚举 + Panel 消费） | PASS |

## 3. 验证证据

见 `SMI_R15_Fix_Notes.md` §三：
- pytest 278 passed + 1 skipped；
- shell 自测 4/4；
- vue-tsc 通过；
- acceptance：07-17 与 08-20 双关键日 9 模块全 PASS；--all 其余失败均在 historical-profile 披露边界内。

## 4. 人工验收清单（代码评审收敛后转人工）

以下为自动化无法替代的人工/环境验收项：

- [ ] **HA-A 生产日观察**：下一交易日 close-snapshot + archive-raw workflow 全绿，线上 latest.json 与新 daily 一致（tradeDate + SHA-256 全等）
- [ ] **HA-B Windows 采集实测**：本机手动跑一次任一 `@net_guard` 采集入口（如 turnover），确认 spawn 路径正常出数（测试已覆盖，生产烟测留证）
- [ ] **HA-C 前端目检**：08-20 及以后日期，TrackMonitorPanel 预热徽标/降级提示渲染正常；历史日（<08-20）tracks 历史不可用提示不受影响
- [ ] **HA-D 数据修复确认**：07-17 范本日恢复后，人工抽查线上 07-17 页面 turnover 放量字段与 Excel 范本一致（部署后生效）
- [ ] **HA-E 已知边界跟踪**：fundFlow push2his 主机封禁状态复查；coverage floor=65 标定回放（满 20~30 交易日后）
