# SMI R25 修复说明（R24-P3-01/02 · 纯验收与文档层）

## R24-P3-01：资格层-排名交叉校验

- decisionContract 新增声明：entryRankMax=5 + qualificationMatrix
  （QUALIFIED_TODAY ⟺ rank<=entryRankMax；RETAINED_OBSERVATION ⟹
  rank>entryRankMax 且未满出池确认）；
- acceptance（cfg>=3.5 正式项）交叉校验：rank6+QUALIFIED /
  rank3+RETAINED 反例即 FAIL；反例 A/B 回归测试入列。

## R24-P3-02：退役语义清理

- select_scoring_pool docstring："入池需连续确认"段落改写为 R24
  直入语义（原 2/3 确认退役，防抖=出池确认），消除同函数自相矛盾；
- tracks.yaml：两处"全市场口径/全市场排名"改为"监测口径（行业板块
  全景 + 已配置概念赛道联合排名）"；
- template-standard displayRules：空表规则改两分支
  （UNAVAILABLE→上游不可用；完整无合格→无符合条件主赛道），
  删除"暂无赛道数据"统一占位。

## 验证

- 纯验收/文档层：采集行为与快照数据零变化（3.5 数据有效，无需重生成）；
- 测试 312 绿（collector 248+1skip + acceptance 64）；acceptance --all
  PASS=3（07-17、08-20、08-21）不变；CI（8bf7d03）。

## 请复核

1. R24-P3-01/P3-02 裁定 CLOSED/NOT_CLOSED；
2. 若无新 NOT_CLOSED，请写明"本轮 0 NOT_CLOSED，ChatGPT 侧已收敛"。
