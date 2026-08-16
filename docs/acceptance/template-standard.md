# 《范本验收标准》 template-standard (v2)

> 参照范本：**2026-07-17**（Excel `A股收盘全景_20260717.xlsx` 与当日网站数据快照 `web/public/data/daily/2026/2026-07-17.json`）。
> 机器可读单一真源：同目录 `template-standard.json`；验收器严格消费该 JSON，本 MD 仅为人类可读说明，与 JSON 保持一致。

- version: **2**
- referenceDate: 2026-07-17
- referenceXlsx: A股收盘全景_20260717.xlsx
- referenceSnapshot: web/public/data/daily/2026/2026-07-17.json
- priority: **referenceXlsx > canonicalSnapshot > rawLegacySnapshot**（参考级字段以 XLSX 为权威；快照中 XLSX 未覆盖字段次之；raw Legacy 仅作溯源）
- rejectedPlaceholders: 暂无、待补、占位、TBD、N/A、nan、null、（无）、None、无数据、未知

通用约束：除备注明确允许外，各模块 `requiredStatus` 均为 `FINAL`；数值一律取自范本 XLSX，不得编造。所有模块的 `dataDate/asOf/publishedAt <= tradeDate`（防 look-ahead）。

---

## 1-宽基指数收盘数据 — `marketIndex`

- **ruleId**：`marketIndex_V2`（ruleVersion=2）　**requiredStatus**：FINAL
- **XLSX 列**：指数名称 / 收盘点位 / 当日涨跌幅

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| dataDate | 字符串 |
| status | 枚举，取值[FINAL] |
| source | 字符串 |

**items 列表**：minItems=6，uniqueBy=`code`
- 必需代码：000001、399001、399006、000688、000300、899050（requiredCodes 保持 6 核心）
- referenceNamesMin：**9**（参考日须能同时匹配全部 9 个范本指数名称，fail-on-missing，缺任一即 FAIL）

| 字段 | 校验 |
| --- | --- |
| code | 字符串 |
| name | 字符串 |
| close | 正有限数值 |
| changePct | 有限数值 |

**渲染规则 displayRules**：

- 必须渲染 items 列表，每条展示指数名称(name)、收盘点位(close，2 位小数)、当日涨跌幅(changePct，带 +/− 与红绿配色)；过滤 name 为空或 null 的项。
- 至少展示 6 个核心宽基指数（000001/399001/399006/000688/000300/899050）；范本日须能同时展示 9 项（上证指数、深证成指、创业板指、科创50、沪深300、北证50、国证1000、国证2000、科创综合），所有 9 个 referenceNamesMin 名称必须全部渲染，缺失任一即 FAIL。
- 面板标题为『宽基指数』，并显示模块状态徽章(StatusBadge)。
- items 内 code 不得重复，dataDate 必须等于所选交易日 tradeDate，close 必须 > 0。

**口径注释 notes**：

referenceAssertions 按指数名称固化 close/changePct 精确值，共 9 项（上证指数/深证成指/创业板指/科创50/沪深300/北证50/国证1000/国证2000/科创综合）；items.referenceNamesMin=9，即参考日须能同时匹配全部 9 个范本指数名称（fail-on-missing，缺任一即 FAIL）。close>0、changePct 有限；code 唯一。最小必须出现 000001/399001/399006/000688/000300/899050 六项核心代码（requiredCodes），close/changePct 均为有限数值；不允许重复 code；dataDate==tradeDate。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "上证指数": {
    "close": 3764.15,
    "changePct": -3.05
  },
  "深证成指": {
    "close": 13706.88,
    "changePct": -5.4
  },
  "创业板指": {
    "close": 3428.63,
    "changePct": -7.15
  },
  "科创50": {
    "close": 1715.4,
    "changePct": -7.12
  },
  "沪深300": {
    "close": 4529.1,
    "changePct": -3.6
  },
  "北证50": {
    "close": 1076.38,
    "changePct": -2.31
  },
  "国证1000": {
    "close": 4862.19,
    "changePct": -4.29
  },
  "国证2000": {
    "close": 9271.69,
    "changePct": -6.16
  },
  "科创综合": {
    "close": 1938.77,
    "changePct": -8.13
  }
}
```

---

## 2-两市成交量 — `turnover`

- **ruleId**：`turnover_V2`（ruleVersion=2）　**requiredStatus**：FINAL
- **XLSX 列**：统计项 / 数值 / 备注

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| turnoverToday | 正有限数值 |
| turnoverPrevious | 正有限数值，(可选) |
| turnoverDelta | 有限数值，(可选) |
| turnoverChangePct | 有限数值，(可选) |
| volumeState | 枚举，取值[EXPANSION/CONTRACTION/FLAT/UNKNOWN] |
| method | 字符串 |
| previousMethod | 可空，(可选) |
| comparisonStatus | 枚举，取值[COMPARABLE/PREVIOUS_UNAVAILABLE/PREVIOUS_METHOD_MISMATCH] |
| crossMethodReferencePrevious | 有限数值，(可选) |
| crossMethodReferenceDelta | 有限数值，(可选) |
| crossMethodReferenceChangePct | 有限数值，(可选) |
| crossMethodReference | 对象(object)，(可选)，PREVIOUS_METHOD_MISMATCH 时 required |
| ↳ previous | 有限数值，required |
| ↳ delta | 有限数值，required |
| ↳ changePct | 有限数值，required |
| ↳ nonComparable | 布尔，required，必须==true |
| ↳ currentMethod | 字符串，required |
| ↳ previousMethod | 字符串，required |

**渲染规则 displayRules**：

- 必须渲染四个格子：当日合计(turnoverToday)、前一交易日(turnoverPrevious)、增减金额(turnoverDelta)+变化幅度(turnoverChangePct)、量能定性(volumeState：EXPANSION→放量/CONTRACTION→缩量/FLAT→平量)。
- comparisonStatus=PREVIOUS_METHOD_MISMATCH 时，必须渲染结构化块 crossMethodReference{previous,delta,changePct,nonComparable=true,currentMethod,previousMethod}，显著标注『跨口径参考（非同一口径，不可与正常环比比较）』，不得写入正常 turnoverPrevious/Delta/ChangePct；crossMethodReference 缺失即 FAIL。
- 单位统一为 亿元。

**口径注释 notes**：

comparisonStatus 状态机：COMPARABLE=method==previousMethod 且 turnoverPrevious>0、delta/pct 有限且满足算术恒等；PREVIOUS_UNAVAILABLE=previousMethod 为 null 且三个环比字段全为 null、volumeState=UNKNOWN；PREVIOUS_METHOD_MISMATCH=previousMethod 非 null 且 !=method，此时必须携带结构化块 crossMethodReference{previous,delta,changePct,nonComparable=true,currentMethod,previousMethod}，nonComparable 必须严格等于 true，三项数值成组出现并满足内部算术关系，禁止写入正常 turnoverPrevious/Delta/ChangePct。禁止按具体日期特判；通用方法边界处理。Legacy 参考日 07-17 仅限 method=LEGACY_UNKNOWN 时，turnoverToday/Previous/Delta/ChangePct/volumeState 由 referenceAssertions 精确断言（26549.58/24035.65/+2513.93/+10.46/EXPANSION），不再允许『字段缺失即 PASS』。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "turnoverToday": 26549.58,
  "turnoverPrevious": 24035.65,
  "turnoverDelta": 2513.93,
  "turnoverChangePct": 10.46,
  "volumeState": "EXPANSION"
}
```

---

## 3-市场情绪指标 — `sentiment`

- **ruleId**：`sentiment_V2`（ruleVersion=1）　**requiredStatus**：FINAL
- **XLSX 列**：全市场上涨家数 / 全市场下跌家数 / 平盘家数 / 非ST涨停数量 / ST涨停数量 / 非ST跌停数量 / ST跌停数量 / 炸板数量 / 涨停封板率 / 市场最高连板高度

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| riseCount | 有限数值 |
| fallCount | 有限数值 |
| flatCount | 有限数值 |
| nonStLimitUpCount | 非负整数 |
| stLimitUpCount | 非负整数 |
| nonStLimitDownCount | 非负整数 |
| stLimitDownCount | 非负整数 |
| brokenLimitCount | 非负整数 |
| limitSealRatePct | 有限数值，范围 0~100 |
| maxLimitUpStreak | 字符串 |
| correctionReason | 枚举，取值[LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX/NONE/PROVENANCE_RAW_ONLY]，(可选) |

**榜单 lists**：

- `rawLegacy`：minItems=0
  - `stLimitUpCount`：非负整数
  - `stLimitDownCount`：非负整数

**渲染规则 displayRules**：

- 必须渲染：上涨家数(riseCount)/下跌家数(fallCount)/平盘家数(flatCount)、非ST涨停(nonStLimitUpCount)/ST涨停(stLimitUpCount)、非ST跌停(nonStLimitDownCount)/ST跌停(stLimitDownCount)、炸板(brokenLimitCount)。
- 涨停封板率(limitSealRatePct)与市场最高连板高度(maxLimitUpStreak)必须以提示行或数值格渲染，不得因快照未展开而静默缺失。
- canonical 展示值必须使用 XLSX 校正后的 ST 计数（ST涨停10/ST跌停32），原始重复的 Legacy 值仅保留于 rawLegacy 溯源。

**口径注释 notes**：

canonical 字段 riseCount/fallCount/flatCount 为 finite 且三者之和 >= 4000（市场宽度完整性）；涨跌停类字段为 nonNegativeInt；limitSealRatePct 为 0~100 的 finite；maxLimitUpStreak 为字符串（如『2连板』）。参考日 07-17 必须 stLimitUpCount=10、stLimitDownCount=32、limitSealRatePct=43.75、maxLimitUpStreak=『2连板』，correctionReason=LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX。rawLegacy 仅作溯源审计，不得替代 canonical 展示值。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "riseCount": 482,
  "fallCount": 5001,
  "flatCount": 40,
  "nonStLimitUpCount": 25,
  "stLimitUpCount": 10,
  "nonStLimitDownCount": 180,
  "stLimitDownCount": 32,
  "brokenLimitCount": 45,
  "limitSealRatePct": 43.75,
  "maxLimitUpStreak": "2连板",
  "correctionReason": "LEGACY_DUPLICATED_FIELD_CORRECTED_FROM_XLSX"
}
```

---

## 4-板块行情表现 — `sectorPerformance`

- **ruleId**：`sectorPerformance_V2`（ruleVersion=1）　**requiredStatus**：FINAL
- **XLSX 列**：一、通达信行业板块-涨幅前5 / 跌幅前5 / 二、通达信概念板块-涨幅前5 / 跌幅前5

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| method | 字符串 |

**榜单 lists**：

- `industryTop5`：minItems=5, uniqueBy=name, sign=mixed, 按 changePct desc
  - `name`：字符串
  - `changePct`：有限数值
- `industryBottom5`：minItems=5, uniqueBy=name, sign=negative, 按 changePct asc
  - `name`：字符串
  - `changePct`：有限数值
- `conceptTop5`：minItems=5, uniqueBy=name, sign=mixed, 按 changePct desc
  - `name`：字符串
  - `changePct`：有限数值
- `conceptBottom5`：minItems=5, uniqueBy=name, sign=negative, 按 changePct asc
  - `name`：字符串
  - `changePct`：有限数值

**渲染规则 displayRules**：

- 必须提供行业/概念两个 Tab，默认行业；每个 Tab 渲染涨幅榜 TOP5 与跌幅榜 TOP5 双栏表格。
- 每行展示板块名称(name)与当日涨跌幅(changePct，带红绿配色)。
- method=TONGDAXIN_LEGACY 时页脚展示『数据口径：通达信 Legacy（历史导入）』。

**口径注释 notes**：

industryTop5/industryBottom5/conceptTop5/conceptBottom5 各需 minItems=5；item name 非空、changePct 有限。Top 列表按 changePct 降序、Bottom 列表按升序；每个列表内 name 互不重复。method 标注口径。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "industryTop5": [
    {
      "name": "电力",
      "changePct": 1.85
    },
    {
      "name": "银行",
      "changePct": 0.92
    },
    {
      "name": "石油石化",
      "changePct": 0.45
    },
    {
      "name": "煤炭",
      "changePct": -0.86
    },
    {
      "name": "交通运输",
      "changePct": -1.52
    }
  ],
  "industryBottom5": [
    {
      "name": "医药生物",
      "changePct": -8.23
    },
    {
      "name": "电子",
      "changePct": -7.68
    },
    {
      "name": "通信",
      "changePct": -7.15
    },
    {
      "name": "计算机",
      "changePct": -6.72
    },
    {
      "name": "机械设备",
      "changePct": -6.18
    }
  ],
  "conceptTop5": [
    {
      "name": "火电",
      "changePct": 3.26
    },
    {
      "name": "水电",
      "changePct": 2.18
    },
    {
      "name": "中字头银行",
      "changePct": 1.65
    },
    {
      "name": "黄金概念",
      "changePct": 1.08
    },
    {
      "name": "油气开采",
      "changePct": 0.72
    }
  ],
  "conceptBottom5": [
    {
      "name": "CRO",
      "changePct": -11.35
    },
    {
      "name": "CPO/光模块",
      "changePct": -10.68
    },
    {
      "name": "存储芯片",
      "changePct": -9.82
    },
    {
      "name": "半导体设备",
      "changePct": -9.15
    },
    {
      "name": "创新药",
      "changePct": -8.76
    }
  ]
}
```

---

## 5-主力资金流向 — `fundFlow`

- **ruleId**：`fundFlow_V2`（ruleVersion=1）　**requiredStatus**：FINAL
- **XLSX 列**：一、行业板块-主力净流入TOP10 / 净流出TOP10 / 二、概念板块-主力净流入TOP10 / 净流出TOP10 / 三、个股-主力净流入TOP10 / 净流出TOP10

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| method | 字符串 |
| unit | 字符串 |

**榜单 lists**：

- `industryInflowTop10`：minItems=10, uniqueBy=name, sign=positive, 按 netInflowYi desc
  - `name`：字符串
  - `netInflowYi`：有限数值
- `industryOutflowTop10`：minItems=10, uniqueBy=name, sign=negative, 按 netInflowYi asc
  - `name`：字符串
  - `netInflowYi`：有限数值
- `conceptInflowTop10`：minItems=10, uniqueBy=name, sign=positive, 按 netInflowYi desc
  - `name`：字符串
  - `netInflowYi`：有限数值
- `conceptOutflowTop10`：minItems=10, uniqueBy=name, sign=negative, 按 netInflowYi asc
  - `name`：字符串
  - `netInflowYi`：有限数值
- `stockInflowTop10`：minItems=10, uniqueBy=name, sign=positive, 按 netInflowYi desc
  - `name`：字符串
  - `netInflowYi`：有限数值
- `stockOutflowTop10`：minItems=10, uniqueBy=name, sign=negative, 按 netInflowYi asc
  - `name`：字符串
  - `netInflowYi`：有限数值

**渲染规则 displayRules**：

- 必须提供行业/概念/个股三个 Tab，默认行业；每个 Tab 渲染净流入 TOP10(inList) 与净流出 TOP10(outList) 双栏表格。
- 每行展示名称(name)与净流入额(netInflowYi，单位亿元，带 +/- 与红绿配色)。
- 页脚展示单位『亿元』与口径（通达信 Legacy / 东方财富）。

**口径注释 notes**：

industry/concept/stock 六类 TOP10 各必须 minItems=10，不放松门禁。item 含 name+netInflowYi（finite）。流入列表所有 netInflowYi > 0，流出列表所有 netInflowYi < 0。流入按金额降序排列；流出按金额绝对值降序（即数值升序）。每个列表 name 唯一。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "industryInflowTop10": [
    {
      "name": "电力",
      "netInflowYi": 58.62
    },
    {
      "name": "银行",
      "netInflowYi": 52.34
    },
    {
      "name": "石油石化",
      "netInflowYi": 28.75
    },
    {
      "name": "煤炭",
      "netInflowYi": 15.68
    },
    {
      "name": "交通运输",
      "netInflowYi": 12.43
    },
    {
      "name": "公用事业",
      "netInflowYi": 10.25
    },
    {
      "name": "建筑装饰",
      "netInflowYi": 8.67
    },
    {
      "name": "房地产",
      "netInflowYi": 6.32
    },
    {
      "name": "钢铁",
      "netInflowYi": 4.58
    },
    {
      "name": "农林牧渔",
      "netInflowYi": 3.21
    }
  ],
  "industryOutflowTop10": [
    {
      "name": "医药生物",
      "netInflowYi": -386.52
    },
    {
      "name": "电子",
      "netInflowYi": -325.78
    },
    {
      "name": "通信",
      "netInflowYi": -218.65
    },
    {
      "name": "计算机",
      "netInflowYi": -186.34
    },
    {
      "name": "电力设备",
      "netInflowYi": -125.46
    },
    {
      "name": "传媒",
      "netInflowYi": -98.72
    },
    {
      "name": "机械设备",
      "netInflowYi": -86.53
    },
    {
      "name": "汽车",
      "netInflowYi": -65.28
    },
    {
      "name": "国防军工",
      "netInflowYi": -52.17
    },
    {
      "name": "有色金属",
      "netInflowYi": -45.69
    }
  ],
  "conceptInflowTop10": [
    {
      "name": "火电",
      "netInflowYi": 42.68
    },
    {
      "name": "中字头",
      "netInflowYi": 38.52
    },
    {
      "name": "高股息",
      "netInflowYi": 35.76
    },
    {
      "name": "银行",
      "netInflowYi": 32.18
    },
    {
      "name": "水电",
      "netInflowYi": 25.43
    },
    {
      "name": "油气开采",
      "netInflowYi": 18.65
    },
    {
      "name": "央企改革",
      "netInflowYi": 15.32
    },
    {
      "name": "黄金概念",
      "netInflowYi": 12.45
    },
    {
      "name": "一带一路",
      "netInflowYi": 8.76
    },
    {
      "name": "地产链",
      "netInflowYi": 5.32
    }
  ],
  "conceptOutflowTop10": [
    {
      "name": "CRO",
      "netInflowYi": -268.43
    },
    {
      "name": "CPO/光模块",
      "netInflowYi": -225.76
    },
    {
      "name": "存储芯片",
      "netInflowYi": -186.32
    },
    {
      "name": "AI算力",
      "netInflowYi": -168.54
    },
    {
      "name": "半导体设备",
      "netInflowYi": -128.65
    },
    {
      "name": "创新药",
      "netInflowYi": -98.72
    },
    {
      "name": "AI应用",
      "netInflowYi": -76.28
    },
    {
      "name": "机器人",
      "netInflowYi": -65.43
    },
    {
      "name": "ChatGPT",
      "netInflowYi": -52.17
    },
    {
      "name": "算力租赁",
      "netInflowYi": -45.86
    }
  ],
  "stockInflowTop10": [
    {
      "name": "长江电力",
      "netInflowYi": 18.65
    },
    {
      "name": "工商银行",
      "netInflowYi": 15.32
    },
    {
      "name": "中国石油",
      "netInflowYi": 12.78
    },
    {
      "name": "农业银行",
      "netInflowYi": 10.56
    },
    {
      "name": "中国神华",
      "netInflowYi": 9.87
    },
    {
      "name": "建设银行",
      "netInflowYi": 8.43
    },
    {
      "name": "中国银行",
      "netInflowYi": 7.65
    },
    {
      "name": "华银电力",
      "netInflowYi": 6.82
    },
    {
      "name": "桂冠电力",
      "netInflowYi": 5.96
    },
    {
      "name": "中国平安",
      "netInflowYi": 5.23
    }
  ],
  "stockOutflowTop10": [
    {
      "name": "药明康德",
      "netInflowYi": -58.62
    },
    {
      "name": "中际旭创",
      "netInflowYi": -52.34
    },
    {
      "name": "寒武纪",
      "netInflowYi": -45.78
    },
    {
      "name": "海光信息",
      "netInflowYi": -38.65
    },
    {
      "name": "浪潮信息",
      "netInflowYi": -35.26
    },
    {
      "name": "恒瑞医药",
      "netInflowYi": -32.18
    },
    {
      "name": "紫光股份",
      "netInflowYi": -28.75
    },
    {
      "name": "新易盛",
      "netInflowYi": -25.43
    },
    {
      "name": "天孚通信",
      "netInflowYi": -22.68
    },
    {
      "name": "中芯国际",
      "netInflowYi": -18.92
    }
  ]
}
```

---

## 6-北向资金数据 — `northbound`

- **ruleId**：`northbound_V2`（ruleVersion=2）　**requiredStatus**：FINAL
- **XLSX 列**：一、北向资金整体流向（合计/沪股通/深股通净流入） / 二、北向净买入TOP10 / 净卖出TOP10 / 三、主力&北向资金重合个股（同步流入/同步流出）

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| mode | 枚举，取值[POST_20240819_LEGACY_IMPORTED/POST_20240819_OFFICIAL_REPLACEMENT] |
| sourceSystem | 字符串 |
| officialDisclosureCompatible | 枚举，取值[true/false]，(可选) |
| quarterlyHolding | 对象(object)，(可选)，OFFICIAL_REPLACEMENT 时 required |
| ↳ status | 枚举，required，取值[FINAL] |
| ↳ asOf | 日期字符串(dateString)，required |
| ↳ publishedAt | 日期字符串(dateString)，required |
| ↳ items | 数组，required，minItems=1 |
| ↳ items[].code | 字符串，required |
| ↳ items[].hkexStockCode | 字符串，required |
| ↳ items[].name | 字符串，required |
| ↳ items[].shareholding | 非负有限数值，required |
| ↳ items[].pctOfIssued | 非负整数，required |
| ↳ items[].market | 枚举，required，取值[沪股通/深股通] |

**榜单 lists**：

- `legacyImportedFields`：minItems=0
  - `totalNetInflow`：有限数值
  - `shanghaiNetInflow`：有限数值
  - `shenzhenNetInflow`：有限数值

**渲染规则 displayRules**：

- Legacy 分支（POST_20240819_LEGACY_IMPORTED）：顶部必须显示『历史口径已变更』通知，说明北向字段来自原 Excel Legacy 导入、不作为官方连续序列；必须渲染合计/沪股通/深股通净流入(legacyImportedFields)及净买入/净卖出 TOP10。
- Official 分支（POST_20240819_OFFICIAL_REPLACEMENT）：必须展示 quarterlyHolding.field（dict、status=FINAL、items 非空且逐项含 code/hkexStockCode/name/shareholding/pctOfIssued/market）；asOf 与 publishedAt 为 required dateString，须存在且 asOf<=selectedDate、publishedAt<=selectedDate（防 look-ahead，缺任一即 FAIL）；可选 dailyOfficialActivity 块，仅承载官方成交总额/笔数与十大活跃证券，不得推导净流入。
- 页面须显著注明『官方已停止日度净流入披露，以下为官方替代口径（point-in-time），不与 Legacy 净流入连续比较』。

**口径注释 notes**：

mode 严格枚举：POST_20240819_LEGACY_IMPORTED（07-17 参考日使用）或 POST_20240819_OFFICIAL_REPLACEMENT。OFFICIAL_REPLACEMENT 分支：模块 status=FINAL、quarterlyHolding 为 dict 且 status=FINAL、items 非空且逐项 schema 合法；asOf 与 publishedAt 均为 required（kind=dateString，用 date/datetime 解析后比较，不用裸字符串），二者必须存在且满足 asOf<=tradeDate 且 publishedAt<=tradeDate（防 look-ahead）；缺任一字段即 FAIL。可选 dailyOfficialActivity 块仅含官方成交总额/笔数与前十大成交活跃证券，不得推导净流入。Legacy 分支：legacyImportedFields.totalNetInflow/shanghaiNetInflow/shenzhenNetInflow 精确断言 -156.32/-68.54/-87.78。若未来采用非官方估算，只能放独立 estimated 分支，isOfficial=false、标明模型/误差/来源，不作为官方口径验收门禁的替代。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "totalNetInflow": -156.32,
  "shanghaiNetInflow": -68.54,
  "shenzhenNetInflow": -87.78,
  "netBuyTop10": [
    {
      "name": "长江电力",
      "netInflowYi": 12.65
    },
    {
      "name": "工商银行",
      "netInflowYi": 10.34
    },
    {
      "name": "中国石油",
      "netInflowYi": 8.76
    },
    {
      "name": "农业银行",
      "netInflowYi": 7.23
    },
    {
      "name": "中国神华",
      "netInflowYi": 6.58
    },
    {
      "name": "建设银行",
      "netInflowYi": 5.92
    },
    {
      "name": "中国银行",
      "netInflowYi": 5.16
    },
    {
      "name": "贵州茅台",
      "netInflowYi": 4.68
    },
    {
      "name": "招商银行",
      "netInflowYi": 4.23
    },
    {
      "name": "中国平安",
      "netInflowYi": 3.85
    }
  ],
  "netSellTop10": [
    {
      "name": "药明康德",
      "netInflowYi": -22.68
    },
    {
      "name": "中际旭创",
      "netInflowYi": -18.54
    },
    {
      "name": "宁德时代",
      "netInflowYi": -15.32
    },
    {
      "name": "比亚迪",
      "netInflowYi": -12.76
    },
    {
      "name": "海光信息",
      "netInflowYi": -10.85
    },
    {
      "name": "寒武纪",
      "netInflowYi": -9.63
    },
    {
      "name": "恒瑞医药",
      "netInflowYi": -8.92
    },
    {
      "name": "浪潮信息",
      "netInflowYi": -7.65
    },
    {
      "name": "迈瑞医疗",
      "netInflowYi": -6.87
    },
    {
      "name": "紫光股份",
      "netInflowYi": -5.96
    }
  ]
}
```

---

## 7-两融数据 — `margin`

- **ruleId**：`margin_V2`（ruleVersion=1）　**requiredStatus**：FINAL
- **XLSX 列**：融资余额（亿元） / 融券余额（亿元） / 两融总余额（亿元） / 较前一交易日余额变动（亿元） / 融资净买入（亿元） / 融券净卖出（亿元） / 两融成交额（亿元） / 两融成交占两市总成交比重

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| status | 枚举，取值[FINAL/PENDING] |
| financingBalance | 非负有限数值 |
| securitiesLendingBalance | 非负有限数值 |
| marginBalance | 非负有限数值 |
| marginBalanceChange | 有限数值 |

**渲染规则 displayRules**：

- FINAL：必须渲染 融资余额(financingBalance)/融券余额(securitiesLendingBalance)/两融总余额(marginBalance)及变动(marginBalanceChange)，并满足总量恒等与环比恒等。
- PENDING：顶部显示『两融数据 T+1 披露，今日暂缺，待次日回补』；存在 latestPublishedReference 时渲染最近已披露参考，不得伪装成当日 FINAL。
- 页脚渲染两融成交额、成交占比及质量标注（LEGACY/派生/估算）。

**口径注释 notes**：

FINAL 分支：三项余额 finite>=0 且 |marginBalance - (financingBalance + securitiesLendingBalance)| <= 0.05；marginBalanceChange 须与前一交易日 FINAL margin 的 marginBalance 差额恒等（|change - (today - prev)| <= 0.01）。PENDING 分支：仅限 tradeDate==latestCapturedDate 且 latestPublishedReference 为 dict 且其 dataDate<tradeDate、三项余额 finite>=0、总量恒等、dataDate 确为已落盘 FINAL margin 日期（须验到存在该日文件且 margin FINAL）。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "financingBalance": 27927.01,
  "securitiesLendingBalance": 212,
  "marginBalance": 28139.01,
  "marginBalanceChange": -442.55,
  "financingNetBuyAmount": -450,
  "legacySecuritiesLendingNetSellAmount": 7.45,
  "marginTradeAmount": 3902.79,
  "marginTradeSharePct": 14.7
}
```

---

## 8-主赛道每日监测表 — `tracks`

- **ruleId**：`tracks_V2`（ruleVersion=2）　**requiredStatus**：FINAL
- **XLSX 列**：监测日期 / 板块名称 / 板块定位 / 近5日成交额排名 / 今日主力净流入(亿) / 连续净流入天数 / 5/10/20日多头排列 / 60日RPS数值 / 近10日跑赢沪深300 / 板块涨停家数 / 连板梯队完整度 / 红盘个股占比 / 核心催化逻辑 / 业绩兑现情况 / 综合达标率 / 最终判定

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| configVersion | 字符串 |
| effectiveFrom | 字符串，required；coversTradeDate：effectiveFrom<=tradeDate |
| effectiveTo | 字符串，required；coversTradeDate：tradeDate<=effectiveTo |
| sourceSystem | 字符串，required |

**items 列表**：minItems=4，uniqueBy=`trackId`

| 字段 | 校验 |
| --- | --- |
| date | 字符串，equalsTradeDate：必须==tradeDate |
| trackId | 字符串 |
| trackName | 字符串 |
| positioning | 字符串 |
| turnoverRank | 正有限数值 |
| mainNetInflow | 有限数值 |
| continuousInflowDays | 非负整数 |
| maAlignment | 枚举，取值[是/否] |
| rps60 | 有限数值，范围 0~100 |
| excessReturn20d | 枚举，取值[是/否] |
| limitUpCount | 非负整数 |
| ladderCompleteness | 字符串，>= 1 字符 |
| redStockRatio | 百分比字符串(如 85%)，按百分比数值解析，min 0 / max 100 |
| coreCatalyst | 字符串，>= 2 字符，需含中文，noPlaceholders=true（不得为空/占位词） |
| earningsRealization | 字符串，>= 2 字符，需含中文，noPlaceholders=true（不得为空/占位词） |
| score | 有限数值，范围 0~100 |
| decision | 枚举，取值[核心防御主线/次主线/主跌浪/退潮主线/观察/达标/规避/数据不足] |

**渲染规则 displayRules**：

- 必须渲染赛道表格，16 列最终目标：监测日期/板块名称/板块定位/近5日成交额排名/今日主力净流入/连续净流入天数/5-10-20日多头排列/60日RPS/近10日跑赢沪深300/板块涨停家数/连板梯队完整度/红盘个股占比/核心催化逻辑/业绩兑现情况/综合达标率/最终判定。
- 至少 4 条赛道；空列表时显示『暂无赛道数据』。
- sourceSystem=TONGDAXIN_LEGACY 时页脚展示『数据口径：通达信 Legacy（历史导入）』；主力净流入按正负红绿配色。
- score（综合达标率）按 0~100 百分比渲染；decision（最终判定）用 decisionText 归一化文案。

**口径注释 notes**：

16 列硬目标不放松。items minItems=4。每列 typed 规则见 items.fields：date==tradeDate（equalsTradeDate）；turnoverRank finitePositive、mainNetInflow finite、continuousInflowDays nonNegativeInt、maAlignment 枚举[是,否]、rps60 0~100、excessReturn20d 枚举[是,否]、limitUpCount nonNegativeInt、ladderCompleteness 非空字符串（如『2连板』/『无连板』）、redStockRatio 为百分比数值（min 0/max 100，按百分比数值解析）、coreCatalyst/earningsRealization 非空中文且 noPlaceholders=true（不在 rejectedPlaceholders）、score 0~100 finite、decision 非空枚举（核心防御主线/次主线/主跌浪/退潮主线/观察/达标/规避/数据不足）。模块级 configVersion/effectiveFrom/effectiveTo/sourceSystem 必填，effectiveFrom<=tradeDate<=effectiveTo（coversTradeDate），避免配置倒灌历史日期。score/decision 由 score_tracks（规则版本化重算器）按输入指标+规则版本重算一致，非 legacy 直接透传；对 legacy 来源同样需用规则版本重算校验一致性。历史行情可派生（近5日排名/均线/RPS/超额/红盘占比）、资金流时间序列（净流入/连续天数）、涨停池/成分（涨停数/梯队）、配置定性列（定位/催化/业绩，versioned config）、派生输出（score/decision），均须记录来源与窗口成熟条件，未成熟不得给完整 PASS。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "高股息_中特估": {
    "监测日期": "2026-07-17",
    "板块名称": "高股息/中特估",
    "板块定位": "核心防御主线",
    "近5日成交额排名": 2,
    "今日主力净流入(亿)": 125.68,
    "连续净流入天数": 3,
    "5/10/20日多头排列": "是",
    "60日RPS数值": 82,
    "近10日跑赢沪深300": "是",
    "板块涨停家数": 8,
    "连板梯队完整度": "2连板",
    "红盘个股占比": "85%",
    "核心催化逻辑": "高股息防御属性、资金抱团避险",
    "业绩兑现情况": "业绩稳定、分红率高",
    "综合达标率": 90,
    "最终判定": "核心防御主线"
  },
  "电力_火电_水电": {
    "监测日期": "2026-07-17",
    "板块名称": "电力(火电/水电)",
    "板块定位": "次主线",
    "近5日成交额排名": 3,
    "今日主力净流入(亿)": 58.62,
    "连续净流入天数": 2,
    "5/10/20日多头排列": "是",
    "60日RPS数值": 78,
    "近10日跑赢沪深300": "是",
    "板块涨停家数": 6,
    "连板梯队完整度": "2连板",
    "红盘个股占比": "90%",
    "核心催化逻辑": "夏季用电高峰、电改政策催化",
    "业绩兑现情况": "业绩确定性强、电价上浮",
    "综合达标率": 80,
    "最终判定": "次主线/轮动主线"
  },
  "医药生物_创新药_CRO": {
    "监测日期": "2026-07-17",
    "板块名称": "医药生物(创新药/CRO)",
    "板块定位": "退潮主线",
    "近5日成交额排名": 4,
    "今日主力净流入(亿)": -386.52,
    "连续净流入天数": 0,
    "5/10/20日多头排列": "否",
    "60日RPS数值": 35,
    "近10日跑赢沪深300": "否",
    "板块涨停家数": 0,
    "连板梯队完整度": "无连板",
    "红盘个股占比": "5%",
    "核心催化逻辑": "无明显催化、业绩不及预期",
    "业绩兑现情况": "CXO海外订单不及预期",
    "综合达标率": 10,
    "最终判定": "一日游脉冲/回避"
  },
  "半导体_CPO_AI算力": {
    "监测日期": "2026-07-17",
    "板块名称": "半导体/CPO/AI算力",
    "板块定位": "主跌浪",
    "近5日成交额排名": 1,
    "今日主力净流入(亿)": -730.77,
    "连续净流入天数": 0,
    "5/10/20日多头排列": "否",
    "60日RPS数值": 28,
    "近10日跑赢沪深300": "否",
    "板块涨停家数": 0,
    "连板梯队完整度": "无连板",
    "红盘个股占比": "3%",
    "核心催化逻辑": "无明显催化、获利盘兑现",
    "业绩兑现情况": "业绩兑现不及预期、估值过高",
    "综合达标率": 5,
    "最终判定": "主跌浪/坚决回避"
  }
}
```

---

## 9-综合总结 — `summary`

- **ruleId**：`summary_V2`（ruleVersion=2）　**requiredStatus**：FINAL
- **XLSX 列**：一、指数与量能总结 / 二、市场情绪总结 / 三、资金流向总结 / 四、赛道监测结论 / 五、操作建议 / 风险提示

**模块级字段**：

| 字段 | 校验 |
| --- | --- |
| indexAndTurnover | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| sentiment | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| fundFlow | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| trackConclusion | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| marketEnvironment | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| northbound | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| margin | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |
| riskWarning | 字符串，>= 10 字符，需含中文，中文占比>= 0.5 |

**渲染规则 displayRules**：

- 必须渲染各总结块并带小标题：指数与量能(indexAndTurnover)、市场情绪(sentiment)、资金流向(fundFlow)、赛道监测(trackConclusion)、风险提示(riskWarning，含风险样式)。
- margin/marketEnvironment/northbound 三个块仅在字段存在时渲染（v-if），标题分别为 两融/市场环境/北向资金。
- 风险提示块使用黄色左边框样式突出，且必须包含『不构成投资建议』。

**口径注释 notes**：

8 段 required（indexAndTurnover/sentiment/fundFlow/trackConclusion/marketEnvironment/northbound/margin/riskWarning），每段 string、minChars>=10、中文字符占比>=0.5、不含 rejectedPlaceholders；riskWarning 必须含『不构成投资建议』。summaryFacts 声明结构化事实锚点（见下方 summaryFacts），验收器须将其与底层模块逐字段比对：marketEnvironment 锚 turnover（COMPARABLE 时禁用『暂无/无可比较/暂无可比较/不可比』等词，量能词按 volumeState 映射 EXPANSION→放量/CONTRACTION→缩量/FLAT→平量/UNKNOWN→量能不明）；trackConclusion 锚 tracks（FINAL 且 items 非空时 4 赛道名前缀全部提及且与数量/判定一致）；margin 段锚 margin（FINAL 反映余额与净变动方向，PENDING 显式『待次日回补』）；northbound 段锚 northbound（LEGACY 标注口径变更、OFFICIAL 体现 point-in-time）。依赖模块非 FINAL/替代口径时，summary 必须显式包含『不可用/口径替代』说明，不得生成貌似完整的结论。

**结构化事实锚点 summaryFacts**：

- **marketEnvironment（锚 turnover）**：comparisonStatus=COMPARABLE 时禁用词清单 `[暂无/无可比较/暂无可比较/不可比/无上一交易日]`；量能词映射 `volumeState→词`：`EXPANSION→放量`、`CONTRACTION→缩量`、`FLAT→平量`、`UNKNOWN→量能不明`。
- **trackConclusion（锚 tracks）**：当 tracks 为 FINAL 且 items 非空时，必须覆盖全部 4 条赛道；4 个赛道名前缀（高股息/中特估、电力/火电/水电、医药生物/创新药/CRO、半导体/CPO/AI算力）全部须被提及，且与 items 数量/最终判定(decision)一致。
- **margin（锚 margin）**：FINAL 反映融资/融券/总余额与净变动方向；PENDING 显式『待次日回补/今日暂缺』。
- **northbound（锚 northbound）**：LEGACY 须体现净流入/流出方向并标注口径已变更；OFFICIAL 体现 point-in-time。

**参考断言 referenceAssertions（2026-07-17，须精确匹配）**：

```json
{
  "segmentCount": 8,
  "riskWarningMustContain": "不构成投资建议",
  "marketEnvironmentMustNotContain": ["暂无", "不可比", "无可比较"],
  "marketEnvironmentMustContain": "放量",
  "marketEnvironmentMustContainReason": "volumeState=EXPANSION（07-17 turnover 精确断言量能为 EXPANSION）"
}
```

---

## 跨模块不变量 crossModuleInvariants

共 **9** 条。每条必须实际产出对应的 invariant result（set(standard.crossModuleInvariants.ids)==set(运行结果 keys)，缺失即 FAIL），并有独立 mutation 覆盖；`enforce` 描述生效范围。

- **INV-DATE-LOOKAHEAD**：所有模块的 dataDate/asOf/publishedAt/latestPublishedReference.dataDate 均不得晚于所选交易日 tradeDate，禁止 look-ahead。
  - **enforce**：递归检查——所有模块顶层 dataDate/asOf/publishedAt/latestPublishedReference.dataDate 及 nested 时序字段（如 tracks.items.date、northbound.quarterlyHolding.asOf/publishedAt）必须 <= tradeDate；任一字段晚于 tradeDate 即 FAIL；缺失的不在比较范围时按该字段结构 required 规则处理。
- **INV-UNIT-亿元**：turnover/fundFlow/northbound/margin 金额单位统一为亿元；fundFlow 的 netInflowYi 含义为主力净流入（亿元），正为流入负为流出。
  - **enforce**：金额字段必须有 unit=亿元 或等价亿元数值域声明；**unit 缺失即 FAIL**（不得仅当 unit 存在且错误时才失败）。
- **INV-LIST-SORT-SIGN**：榜单唯一性/排序/符号：items/lists 内 uniqueBy 字段不重复；Top 列表按数值降序、Bottom 列表按升序（或规定方向）；fundFlow 流入全>0、流出全<0，northbound netBuy>0、netSell<0。
  - **enforce**：对每个声明的榜单 lists/items 校验 uniqueBy 互不重复、Top 降序/Bottom 升序、符号约束；排序/符号/唯一性任一违反即 FAIL。
- **INV-MARGIN-IDENTITY**：marginBalance == financingBalance + securitiesLendingBalance（容差 0.05）；marginBalanceChange == 当日 marginBalance - 前一交易日 FINAL marginBalance（容差 0.01）。
  - **enforce**：任一恒等不成立即 FAIL；前一交易日缺失时不得记 note 放行，须按 PENDING 规则判定。
- **INV-TURNOVER-IDENTITY**：COMPARABLE 态下 turnoverDelta == turnoverToday - turnoverPrevious（容差 0.01）；turnoverChangePct == turnoverDelta / turnoverPrevious * 100（容差 0.01）。
  - **enforce**：comparisonStatus=COMPARABLE 时上述两恒等任一不成立即 FAIL。
- **INV-SENTIMENT-WIDTH**：riseCount + fallCount + flatCount >= 4000（市场宽度完整性），三类均须为有限数值。
  - **enforce**：riseCount+fallCount+flatCount>=4000 且三类皆为有限数值；不满足（含任一缺失/非有限）即 FAIL。
- **INV-ENUM-SOURCE-METHOD**：各模块 source/method/mode/comparisonStatus/volumeState/maAlignment/excessReturn20d/decision 必须满足标准枚举；source 与 method 标识口径来源。
  - **enforce**：各字段必须命中 `spec.allowedEnums` 允许枚举清单；任一不合法即 FAIL。允许枚举清单：
    - turnover.method=`[LEGACY_UNKNOWN]`；turnover.comparisonStatus=`[COMPARABLE/PREVIOUS_UNAVAILABLE/PREVIOUS_METHOD_MISMATCH]`；turnover.volumeState=`[EXPANSION/CONTRACTION/FLAT/UNKNOWN]`
    - marketIndex.source=`[TONGDAXIN_LEGACY/SINA/EASTMONEY]`
    - sectorPerformance.method=`[TONGDAXIN_LEGACY/EASTMONEY]`
    - fundFlow.method=`[TONGDAXIN_LEGACY/EASTMONEY]`
    - northbound.mode=`[POST_20240819_LEGACY_IMPORTED/POST_20240819_OFFICIAL_REPLACEMENT]`
    - tracks.sourceSystem=`[TONGDAXIN_LEGACY/SELF]`；tracks.maAlignment=`[是/否]`；tracks.excessReturn20d=`[是/否]`；tracks.decision=`[核心防御主线/次主线/主跌浪/退潮主线/观察/达标/规避/数据不足]`
- **INV-REF-EXACT**：参考日 2026-07-17 的各模块 referenceAssertions 必须逐项匹配精确值（容差按字段规定）；referenceAssertions 中任一字段在参考日不满足即该模块 FAIL，不得以 Legacy 字段缺失豁免。
  - **enforce**：逐项精确匹配且 **fail-on-missing**（缺 actual 即 FAIL，禁止 continue 跳过）；declaredAssertions 必须==consumedAssertions，未消费 assertion 直接 FAIL/exit。
- **INV-NORTHBOUND-PIT**：northbound 的 official replacement 必须 point-in-time：quarterlyHolding.asOf<=selectedDate 且 quarterlyHolding.publishedAt<=selectedDate；不得把运行时最新季度持仓倒灌历史选择日。
  - **enforce**：mode=OFFICIAL_REPLACEMENT 时 asOf 与 publishedAt 必须存在（required dateString）且 asOf<=selectedDate、publishedAt<=selectedDate；缺失或晚于 selectedDate 均返回失败，不得只拦未来值。
## 报告溯源 reportProvenance

验收报告必须包含：`repoCommit`、`standardSha256`、`acceptorSha256`、`manifestSha256`、`schemaVersion`、`perDateSnapshotSha256`、`pythonVersion`、`generatedAt`。

## 占位词 rejectedPlaceholders

`暂无`、`待补`、`占位`、`TBD`、`N/A`、`nan`、`null`、`（无）`、`None`、`无数据`、`未知` 一律视为占位/无效值，不得作为通过依据。