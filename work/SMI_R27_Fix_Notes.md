# SMI R27 修复说明（R24-P3-02 三次收口 · 最后一处注释）

R26 裁定：其余旧语义已清理，仅余 select_scoring_pool() 输出段注释
"RETAINED_OBSERVATION = rank∈(entryRankMax, exitRankMax]"遗漏
>exitRankMax 出池宽限日。本轮修正（main HEAD=ce60d38，纯注释层）：

1. select_scoring_pool 输出注释：改为"rank > entryRankMax 且未满出池
   确认——含 (entryRankMax, exitRankMax] 观察区与 > exitRankMax
   出池宽限两种形态，见 C1 决议"（与 qualificationMatrix 一致）；
2. 顺带清理 test_tracks_dynamic.py 两处同款"rank∈(5,12]"文档串。

全仓 grep（collector/ + config/）不再存在 "(5,12]"/"∈ (entryRankMax"
区间遗漏表述；测试 312 绿；纯注释层零行为变化。
