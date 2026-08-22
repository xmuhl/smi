# SMI R28 修复说明（R24-P3-02 系统性收口 · tracks 域全仓清查）

R27 裁定：C1 区间注释已修，但 test_tracks_dynamic.py 仍余两处旧口径。
本轮放弃逐处修补，改为 **tracks 域全仓系统性 grep 清查**（关键词：
全市场/poolSize/入池确认/净流入为正/退化为纯种子），一次清除 6 处：

1. test_tracks_dynamic.py：种子排名注释"全市场口径"→"监测口径"；
   grandfather 对照"准入（>poolSize=8）"→"准入（>entryRankMax=5）"；
   分区头"入池确认/双阈值/冷启动"→"R24 起当日前5直入；出池确认/观察保留"；
2. collector/archive.py：kind 注释"全市场行业板块每日快照…全市场口径底座"
   →"行业板块全景每日快照…监测口径（行业 universe）底座"；
3. collector/jobs/archive_raw.py：阶段 5 注释同步；
4. collector/calculators/tracks.py：评分 docstring 资金维度"近 5 日成交额
   全市场前 5"→"监测口径前 5"（评分条件数值不变，仅口径命名）。

保留说明：
- tracks.py:710"原 poolSize=8 防抖口径取消"为显式历史变更注记（标注
  "取消"），非现行语义陈述；
- 非 tracks 域的"全市场"（turnover 新浪全市场 spot/情绪全市场涨跌家数/
  sectorPerformance 全市场榜）为各模块真实语义，不在本问题范围。

验证：全仓 grep（tracks 域 6 文件）无现行语义的退役表述；测试 312 绿；
纯注释层零行为变化；acceptance PASS=3 不变。
