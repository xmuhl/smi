# SMI R17 修复对照说明（Fix Notes）

- 基线：R16 送审 HEAD `a3a706c`
- 本轮范围：R16 唯一新增项 R16-P2-01（权威版本时间表）
- 日期：2026-08-22

## R16-P2-01 旧版本兼容没有权威时间边界 → 已修复

**裁定：采纳。** configVersion 是被验收事实，同时又被用作决定验收强度的可信依据，构成自证循环——未来新快照错误自报 3.0 可伪装"历史兼容"绕过 3.2 严格契约。

**修复**（按 R16 §5.6 建议）：

1. **标准**（`docs/acceptance/template-standard.json` tracks spec 新增 `tracksVersionSchedule`）：
   - `through: 2026-08-20`：`allowedConfigVersions: ["legacy","1.0","2.0","3.0","3.1","3.2"]`——历史快照实际版本全集（legacy=07-17 范本日；2.0×20日 07-20..08-19；1.0×08-14/17；3.0×08-18..20），历史日按当期契约验收不回溯强改；
   - `from: 2026-08-21`：`minConfigVersion: "3.2"`——3.2 代码（ebac337，2026-08-22）之后的首个可产数据交易日为 cutoff；此后自报 <3.2 一律 FAIL。
2. **验收器**（`tools/acceptance/accept.py` 矩阵块 1b）：按 trade_date 匹配时间表规则；窗口内不在 allowedConfigVersions 白名单 → FAIL；cutoff 后低于 minConfigVersion → FAIL（"版本降级旁路"）；非数值版本（legacy）由白名单裁决。
3. **测试**（`tools/acceptance/test_accept.py`）：
   - `test_tracks_v4_version_schedule_blocks_future_downgrade`：2026-08-24 自报 3.0 → FAIL（R16 §5.6 要求的负向）；
   - `test_tracks_v4_version_schedule_unknown_legacy_version_in_window`：cutoff 前 2026-08-19 自报 "9.9" 不在白名单 → FAIL（时间表是白名单不是自由放行）；
   - `test_tracks_v4_legacy_30_shape_still_passes` 日期修正为真实 **2026-08-20**（原测试误用 08-21——该日在 cutoff 后，自报 3.0 现在必须 FAIL；R16 §5.6 要求的正向）。

08-20 生产日（3.0）经 through 规则合法 PASS 的行为不变。

## 验证证据（2026-08-22）

| 验证项 | 结果 |
|---|---|
| `pytest -q collector/tests tools/acceptance/test_accept.py` | **293 passed, 1 skipped**（R16 后 291 → 净增 2：时间表负向+白名单负向；legacy 正例改期） |
| acceptance --all（25 日） | PASS=2（07-17、08-20）不变；其余在已披露边界内 |
| shell 自测 | 4/4 PASS |

## 已知边界（不变）

沿用 R15/R16 裁定：coverage floor=65 临时标定；sentiment/fundFlow 历史源缺口；margin/turnover/northbound/summary 存量上游失败；manifest 指针停在 07-17 与 D0 语义一致。
