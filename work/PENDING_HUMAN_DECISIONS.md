# 待人工裁决事项（PENDING HUMAN DECISIONS）

> 生成：2026-08-28 断更事故恢复过程（详见 work/INCIDENT_20260828_RECOVERY.md）。
> 以下事项不阻塞数据恢复，但需要人工决策或操作。处理后请勾销对应条目。

## 1. FEISHU_WEBHOOK_URL secret 未配置（第三次提醒 · 08-28 已备好一键方案）

- **仅需人工做的一步**（约 2 分钟，需登录飞书）：
  1. 打开接收告警的飞书群（可新建，如「SMI 数据告警」）→ 设置 → 群机器人 → 添加机器人 → **自定义机器人**；
  2. 安全设置选 **自定义关键词**，填 `SMI`（告警文本固定以 `[SMI]` 开头）；
     ⚠️ 不能选「加签」——data_health.py 发的是无签名纯文本，选加签会被全部拒收；
     ⚠️ 不能选「IP 白名单」——GitHub runner 出口 IP 动态，无法枚举；
  3. 复制生成的 webhook 地址（`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）发给助手。
- **其余全自动**（助手执行，无需人工）：
  `tools/alert/set_feishu_secret.py` 一键写入 GitHub secret（sealed box 加密，无明文落盘；
  token 权限已于 08-28 验证 HTTP 200）→ 直发一条 `[SMI] test` 消息验证收达 → 勾销本条。
- **影响**：未配置期间所有数据级告警降级为 workflow annotation + GitHub 邮件；
  GitHub cron「静默丢弃」类事故（无失败运行产生）依旧零通知——这正是 08-28 断更到
  19:39 才被发现的原因之一。

## 2. 跨平台看门狗的调度平面选择

本会话无法自建定时任务（工具集仅 CronList/Delete/Update，无 CronCreate），已将完整
runbook + 可直接粘贴的定时任务提示词落盘 `ops/AUTOCHECK_RUNBOOK.md`。三选一（可叠加）：

- **A. ZCode 定时自动化**：在 ZCode 中新建定时任务（工作日 20:30 CST），提示词直接
  粘贴 ops/AUTOCHECK_RUNBOOK.md 中的模板。零基础设施成本，依赖本机开机。
- **B. Windows 计划任务**：schtasks 注册工作日 20:30 触发 zcode CLI 执行同一提示词。
  同样依赖本机开机，但注册一次后与会话无关。
- **C. Cloudflare Workers Cron Trigger**：唯一能覆盖「本机关机」时段的方案。在 CF
  部署 Worker 定时校验 smi.gorestart.cn 新鲜度并调 GitHub dispatch API。需要把
  GitHub PAT（fine-grained，仅 Actions:write）存入 CF Worker secret——**安全边界
  变化，需人工批准**（token 最小化权限 + 泄露轮换策略）。
- **建议**：先 A/B（5 分钟），C 作为后续加固。

## 3. GitHub scheduled workflows 可靠性（平台风险，无代码侧根治）

- 8/26~27 官方两起 Actions 事故 + scheduled 触发不进状态页跟踪；08-27 部分丢弃 +
  延迟 7~10h 补发、08-28 当日全丢，均无官方事件记录。
- 代码侧已尽：盘前守卫（防延迟补发脏数据/假红）+ dispatch 免疫（恢复路径）+
  跨平台兜底（§2）。**根治只能靠 §2 的调度双平面**，或迁移采集主机。
- 留观：若 GitHub 调度劣化常态化（连续多周），考虑把主采集迁至国内 VPS cron +
  GitHub 仅作镜像（架构决策，需人工立项）。

## 4. runner 海外 IP 结构性劣势（第三次出现）

- 两融（SSE/SZSE）与东财 push2 系对 GitHub runner（Azure 海外 IP）频繁重置连接；
  本机同源畅通。已两次靠本机 t1_reconcile 兜底（08-25、08-28）。
- 选项：维持现状（本机兜底为常态 runbook）/ 迁国内 runner / 付费代理。属基础设施
  决策，暂维持现状。
