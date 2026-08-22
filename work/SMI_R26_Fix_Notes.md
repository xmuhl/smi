# SMI R26 修复说明（R24-P3-02 二次收口 · 纯注释层）

R25 裁定：R24-P3-01 ✅；R24-P3-02 ❌ 残余三处文档真理源漂移。本轮
彻底清理（main HEAD=95a9ed6，纯注释/文档，零行为与数据变化）：

1. tracks.yaml 头部候选口径：
   旧："近 N 日成交额排名靠前 + 当日主力净流入为正 → 前 poolSize 名为候选"
   新："近 N 日成交额监测口径排名 <= entryRankMax(5) 直接入池（当日前5，
   每日范本真理源，无确认门槛；净流入不作准入条件——排名决定监测资格，
   资金流决定评分/评级）"
2. tracks.yaml RETAINED_OBSERVATION 区间：
   旧："rank∈(5,exitRankMax]"（遗漏 >12 出池宽限形态）
   新："rank>entryRankMax 且未满出池确认——含 (5,exitRankMax] 观察区与
   >exitRankMax 出池宽限两种形态"（与 qualificationMatrix 一致）
3. tracks.py 三处 docstring：
   - _universe_ranking / select_candidate_boards / collect_tracks：
     "全市场口径" → "监测口径（行业板块全景+注入概念腿）"
   - select_candidate_boards："调用方退化为纯种子" →
     "R22 起调用方不再回退种子，无数据日诚实空池"
   - 预热池注释去"不要求当日净流入为正"措辞（准入已整体不筛净流入）
4. tracks.yaml 预热注释同步。

## 验证

- grep 复核：全仓库（config/tracks.yaml + collector/modules/tracks.py）
  不再存在"全市场（除'不自称全市场'声明句）/退化为纯种子/净流入为正
  →候选"退役语义；
- 测试 312 绿；acceptance --all PASS=3 不变；纯注释层零行为变化。

## 请复核

R24-P3-02 裁定：CLOSED / NOT_CLOSED；若无新问题，请写明
"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
