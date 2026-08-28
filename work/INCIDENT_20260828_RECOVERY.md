# 2026-08-28 数据断更事故：根因分析与完整解决方案

> 状态：方案已实施待验证 · 发现时间 2026-08-28 19:39 CST · 恢复目标 当日 21:30 前上线

## 一、事故现象

- 线上 `latest.json` 停留在 `tradeDate=2026-08-27`（rev5），08-28（周五交易日）全天无数据。
- GitHub Actions 自 08-27T22:15Z 后**零运行**——当日全部计划窗口未触发：
  close-snapshot（16:23/18:23/19:23 CST）、archive-raw（16:35）、t1-reconcile（18:17）、
  freshness-watchdog（17:10/18:10/19:10）全部缺失。
- 作为 cron 丢弃兜底而生的 freshness-watchdog 自身也是 cron 触发，同批被丢弃，兜底失效。

## 二、根因（三层）

### 层 1：GitHub 平台调度静默劣化（触发层）
- 8/26~27 GitHub 官方两起 Actions 事故（job 启动失败/延迟/4% 未触发，状态页已 resolved）。
- **scheduled 触发不在状态页跟踪范围**：08-27 部分 cron 被丢弃且补发延迟 7~10 小时；
  08-28 升级为当日全丢、零补发。无任何官方事件记录，"未触发"不产生失败运行 → 零告警。

### 层 2：延迟补发在凌晨执行 → 两类次生损害（执行层）
昨夜（08-28 CST 凌晨）被补发的运行产生了新问题：

| 运行 | 实际执行时间 | 后果 |
|---|---|---|
| archive-raw ×1 | 03:12 CST | `--date auto` 解析到 08-28（未收盘）；THS「即时」资金流/涨停池/行业汇总盘前返回的是 **08-27 收盘值**，被写成 `tradeDate=2026-08-28`（capturedAt 03:14）→ **7 行错日脏数据入库并推送**（450fd9a） |
| close-snapshot ×3 | 03:08/04:36/05:03 CST | BEFORE_CLOSE 守卫正确拦截（exit 2），但该码与 VALIDATION_FAILED 共用 → 步骤判失败 + data_health 误报"当日快照未发布" → **3 个假红灯** |
| t1-reconcile ×2 | 03:50/06:15 CST | 两融采集返回空 DataFrame（runner 海外 IP 被交易所重置，08-25 同模式）→ margin 08-27=ERROR，**真实数据缺口** |

### 层 3：看门狗单平台依赖（兜底层）
- freshness-watchdog 的修复假设是"cron 丢弃是部分性的，看门狗自身仍会被触发"。
- 本次平台级全丢证明：**兜底与主链路同平台同触发机制 = 无兜底**。

## 三、经验对照（08-25 → 08-27 → 08-28）

| 事故 | 直接根因 | 当时修复 | 本次验证的残余盲区 |
|---|---|---|---|
| 08-25 | runner 海外 IP 被数据源重置（margin 静默 ERROR 两天） | 本机兜底回补 + P0-b 数据健康门禁 | 门禁有效（今晨两次红灯属实），但 runner 侧无解，只能本机兜底 |
| 08-27 | GitHub cron 部分丢弃（5+ 窗口） | freshness-watchdog（盘后巡检+dispatch 自愈） | 假设看门狗自身不被丢——08-28 证伪 |
| 08-27 深夜~08-28 | 调度补发延迟 7~10h | （当时未发生/未识别） | **新故障模式**：盘前执行产生错日脏数据 + 假红灯；archive_raw 无盘前守卫 |
| 08-28 | GitHub cron 当日全丢（含看门狗） | 本方案：跨平台兜底 + 盘前守卫 | — |

核心教训：
1. **dispatch 走 API 免疫 cron 丢弃**（08-27 已证）——一切恢复路径以 API dispatch 为准。
2. **凡 `--date auto` 的 job 必须有盘前守卫**——调度延迟不可预测，任何 cron 都可能在凌晨补发。
3. **良性跳过与真失败必须用不同退出码**——共用退出码会把守卫的正确拦截变成告警噪音，
   淹没真信号（昨夜 5 个红灯里只有 2 个是真缺口）。
4. **「即时」类接口盘前返回昨日值**——数据源语义陷阱，靠 capturedAt 与 tradeDate 一致性无法
   自愈，只能靠时间守卫前置拦截。
5. **兜底必须跨调度平面**——同平台的第二 cron 不是兜底。

## 四、完整解决方案

### A. 数据修复（恢复当日发布）
1. ✅ 本机 t1_reconcile 回补 margin 08-27 → FINAL（rev5）。
2. ✅ 清除 7 行错日脏归档（tradeDate=2026-08-28 且 capturedAt<16:00 的行）。
3. ⏳ push 数据+代码修复提交（98a77f9 + 09c6368）。
4. ⏳ dispatch archive-raw（盘后采集真实 08-28 归档：universe/涨停池/flow/close）。
5. ⏳ archive-raw 完成后 dispatch close-snapshot（发布 08-28 daily + 构建部署 Pages）。
   - 顺序硬约束：archive 必须先于 close-snapshot（08-27 事故已证反序会导致 tracks 缺涨停池
     → coverage fail-closed UNAVAILABLE）。
   - 部署自检（SITE_LATEST_EXACT_MATCH）由 workflow 内置。

### B. 代码加固（防同模式复发）
1. `close_snapshot.py`：BEFORE_CLOSE exit 2 → **exit 3**；workflow 在步骤 shell 内把
   exit 3 转为 exit 0（步骤成功）→ 假红灯消除；VALIDATION_FAILED（exit 2）原样透传，
   步骤失败 + data_health 双保险维持 job 级红灯（含 dispatch 重采已发布日场景——
   子代理评审 P1 修正：不使用 continue-on-error，避免 exit 2 在旧 daily 存在时静默变绿）。
2. `archive_raw.py`：新增盘前守卫（同阈 16:00 CST）→ 盘前补发直接 BEFORE_CLOSE 跳过，
   杜绝错日脏数据入库。
3. 回归测试 `test_schedule_guards.py`×3（盘前跳过×2 + 盘后放行×1），全量 255 passed。

### 子代理验证结论（agent_14a0628b）
- **VERDICT: 有条件可行，无 P0 阻断**。数据清除 1:1 精确无误删；GitHub Actions
  语义推演（continue-on-error/success() 隐式条件/四场景逐步骤）通过；恢复顺序硬约束
  （archive→close、push 先于 dispatch）证实；延迟补发三场景（close freshness skip /
  t1 ALREADY_FINAL / archive ALREADY_EXISTS）均自愈安全。
- P1（已落实）：continue-on-error 弱化 exit 2 的 dispatch 重采场景红灯 → 改为 shell 内
  exit 3→0 转换并移除 continue-on-error。
- P2（留档知悉）：archive 延迟补发可能因 payload 微差（字段排序）产生 rc=2 假红灯（噪音）；
  close-snapshot commit 步骤无 rebase 重试（既有，风险≈0）；status.json DEGRADED 与
  HS300_SEED_UNAVAILABLE 为既有诚实缺口，不构成恢复失败判据。

### C. 跨平台兜底（防调度全丢）
1. **本机 ZCode 定时自动化**（另一调度平面，与 GitHub 独立）：工作日 20:30 CST 巡检
   线上 latest.json——滞后即按本 runbook：排障 → dispatch 恢复 → 验证 → 部署 → MCP 核对。
2. （留档待人工裁决）Cloudflare Workers Cron Trigger 方案：见 §六。

### D. 验证与上线核对
1. archive-raw 运行绿 + jsonl md5 自检过 + 归档含真实 08-28 行（capturedAt ≥ 16:00）。
2. close-snapshot 运行绿 + SITE_LATEST_EXACT_MATCH。
3. 线上核对（MCP webReader 逐项）：latest.tradeDate=2026-08-28；9 模块状态；
   margin 08-27=FINAL；tracks 非 UNAVAILABLE；当日 daily JSON 可访问。
4. 页面探针 `window.__smiPageCheck()`（如可执行）。

## 五、执行时间线（CST）

| 时间 | 动作 | 结果 |
|---|---|---|
| 19:39 | 发现断更；查 Actions 零运行 | 确认调度全丢 |
| 19:44 | dispatch archive-raw（首次） | 19:47 rc=2——撞脏数据 conflict（据此定位层 2） |
| 19:43-19:48 | 本机 t1_reconcile 回补 08-27 | margin FINAL |
| 19:50-20:0x | 定位 450fd9a 脏提交；清 7 行；加双守卫；测试 255 绿 | 98a77f9 + 09c6368 |
| 20:0x | 子代理方案验证 | 见验证结论 |
| 之后 | push → 重 dispatch archive-raw → dispatch close-snapshot → 上线核对 | — |

## 六、待人工裁决事项（不阻塞本次恢复）

1. **FEISHU_WEBHOOK_URL secret 仍未配置**（GitHub → Settings → Secrets → Actions）。
   未配置期间告警降级为 annotation + GitHub 邮件。已两轮事故提醒，建议尽快配置。
2. **Cloudflare Workers Cron 跨平台看门狗**：在 CF 部署一个 Cron Trigger Worker，
   定时校验 smi.gorestart.cn 新鲜度并调 GitHub dispatch API。需要把 GitHub token 存入
   CF Worker secret——安全边界变化，需人工决策是否采纳（本机 ZCode 自动化已能覆盖
   开机时段；Worker 可覆盖本机关机时段）。
3. **runner 海外 IP 结构性劣势**（两融/东财源）：迁国内 runner / 付费代理 / 常态化本机
   兜底三选一，属基础设施决策，留档。

## 七、恢复结果（终态，2026-08-28 21:1x CST）

| 项 | 结果 |
|---|---|
| 线上 latest.json | tradeDate=**2026-08-28** rev2（20:50:40），PARTIAL_PENDING（margin T+1 正常时序 + tracks 常态降级带） |
| 模块状态 | 7 FINAL + tracks PARTIAL（coverage 75.3>65 地板，前5=半导体/通信设备/元件/通用设备/消费电子，rank 升序）+ margin PENDING（周五两融下周一披露，t1-reconcile 届时回补） |
| 08-27 margin | FINAL 已随构建上线（daily/2026/2026-08-27.json） |
| 归档 08-28 | flow×5 + universe×1 + limit-up×1 真实 post-close 记录（capturedAt 20:15/20:16，70a033c）；board-close 日线 THS 盘后延迟生成 → 次日回补（既有模式） |
| 运行链 | archive-raw ✅ → close-snapshot ✅（SITE_LATEST_EXACT_MATCH）→ 重建 close-snapshot ✅（rev2） |
| MCP webReader 核对 | 双域一致 ✅ 9 面板内容 ✅ 板块涨幅与归档交叉一致 ✅ 两融数字与本机回补一致 ✅（webReader 自身渲染缓存滞后一轮，生产 no-cache 策略下用户即时见 rev2） |
| 提交链 | 98a77f9(数据修复) → d9e6e58(盘前守卫) → 70a033c(归档) → 7a27e6c(测试离线化) → 889065f(08-28 快照) → 4277795(summary 自引用修复) → 30c014a(事故报告) |

### 过程中额外发现并修复（非事故直接根因）

1. **summary riskWarning 自引用**（既有 bug，每晚速览条误显示「待披露：margin、summary」）：
   new_snapshot 播种 PENDING 占位，generate_summary 运行时 summary 自身未被覆写，
   _rule_risk 把它写进自己的待披露清单。已过滤（4277795），rev2 实测修正为
   「待披露：margin。」。
2. **测试联网写生产归档**：test_archive_raw_after_close_proceeds 初版真实调用
   「即时」类采集器，把 08-28 数据写进生产归档目录（20:03 本机写入）。已全量打桩
   离线化（7a27e6c），本地以 dispatch 运行产物（70a033c）为准还原。
