# 采集链路迁移国内 VPS 方案（阿里云可用性评估 + 实施设计）

> 2026-08-28 起草 · 状态：**实施中**——VPS 勘察完成（2026-09-01）：github.com HTTPS
> 阻断（TLS 挂起），方案 A git 通道改走 ssh.github.com:443（协议层待验证），
> 进度与剩余任务真源见 `VPS_MIGRATION_PROGRESS_20260901.md` ·
> 关联 PENDING_HUMAN_DECISIONS.md §3/§4

## 一、动机（两次事故的共同根因）

| 事故 | 根因 | 迁移后 |
|---|---|---|
| 08-25 / 08-28 margin ERROR | GitHub runner（Azure 海外 IP）被交易所 SSE/SZSE 与东财 push2 重置连接 | **根治**：国内 VPS 直连全部畅通（08-23 实测：本机同源全通，仅 runner 被封） |
| 08-27 / 08-28 断更 | GitHub scheduled cron 部分丢弃/全天丢弃（含兜底 watchdog 自身） | **根治**：VPS crond 与 GitHub 调度平面彻底解耦 |

附带收益：飞书 webhook 国内直连更稳；数据健康门禁/告警本地化。

## 二、推荐架构（方案 A：VPS 采集 + GitHub 构建/部署）

分工原则：VPS 做国内网络有优势的事（采集），GitHub 做海外有优势的事（build + Cloudflare Pages 部署）。

```
阿里云 VPS                             GitHub                          Cloudflare
cron(工作日 CST):                      deploy-pages.yml(新):            Pages
 16:23/18:23/19:23 close_snapshot ──push──> checkout→node22→npm ci     (托管不变)
 16:35          archive_raw       数据提交   →typecheck→build
 10:17/18:17/20:17 t1_reconcile             →wrangler pages deploy
 收尾 data_health(飞书直连)                  →SITE_LATEST_EXACT_MATCH 自检
```

- 采集代码**零改动**：三个 job 入口（`collector.jobs.close_snapshot/archive_raw/t1_reconcile`）
  直接复用；08-28 已上线的盘前守卫（close exit 3 / archive BEFORE_CLOSE）天然防
  cron 延迟补发与重复触发，多窗口=自愈重试（已发布日 freshness 守卫秒级跳过）。
- 数据底座不变：git 仓库仍是单一真源（daily JSON + jsonl 归档 + 验收工具），
  验收器/CI/历史审计链路全部保留。

## 三、VPS 可用性核对清单（人工在服务器上执行）

```bash
cat /etc/os-release                       # 可装 Python 3.11 即可（Ubuntu 22.04/Debian 12 均 OK）
python3 --version                         # ≥3.11 最佳（与 workflow 一致）
nproc; free -h; df -h /                   # 1c2g 起步够（采集峰值内存 <1.5G）；磁盘 5G 足够
curl -sI --max-time 10 https://github.com | head -1   # ★ 关键项：需 200/301
timedatectl | grep Time                   # 建议 Asia/Shanghai（否则 cron 按 UTC 换算）
```

唯一硬门槛：**VPS→github.com push 连通性**。阿里云国内节点一般可用；小体积 JSON
提交（数百 KB/日）压力小，配 3 次重试 + 失败飞书告警消化。若实测长期不可达，
升级到方案 C（见 §六）。

## 四、实施工作项

### ① VPS 侧

| 项 | 内容 |
|---|---|
| 环境 | Python 3.11 venv；`pip install -r collector/requirements.txt`；clone 仓库至 `/opt/smi` |
| 认证 | fine-grained PAT（仅 Contents:RW）+ git credential store；**勿用账号主密码** |
| cron | `23 16,18,19 * * 1-5` close_snapshot；`35 16 * * 1-5` archive_raw；`17 10,18,20 * * 1-5` t1_reconcile（均 `flock -n` 防重叠） |
| 提交脚本 | `git add web/public/data → commit("data: ...") → pull --rebase → push`，push 重试 3 次（间隔 60s）；失败→飞书告警，数据留本地等下窗口自动补推 |
| 告警 | 各任务收尾跑 `tools/alert/data_health.py`；`FEISHU_WEBHOOK_URL` 配 VPS 环境变量（国内直连） |
| 代码更新 | 人工 `git pull`（或加每周 cron）；变更走 CI 验证后再拉取 |
| 日志 | logrotate 按日切割，保留 30 天 |

### ② GitHub 侧

1. **新增 `deploy-pages.yml`**：触发 `push`（paths: `web/public/data/**`）+ workflow_dispatch；
   步骤复用 close-snapshot 现有构建/部署/自检段（node22→npm ci→typecheck→build→
   wrangler deploy→SITE_LATEST_EXACT_MATCH）；concurrency 沿用 `smi-data-write`
   或独立 `smi-deploy`（部署与数据写解耦后可独立）。
2. **禁用 3 个采集 workflow 的 schedule 段**（注释保留 workflow_dispatch 应急后门）。
3. **freshness-watchdog 保留**：角色从「唯一兜底」反转为「第二平面」——任一侧调度
   故障都能被另一侧发现，跨平台双平面自此成立。

### ③ 迁移节奏（可回滚）

1. **双跑观察 1 周**：GitHub cron 不动，VPS cron 上线——双侧 freshness 守卫互斥跳过
   （谁先发布对方跳过），比对一周日志无差异；
2. **切换**：注释 GitHub schedule，VPS 为主；
3. **回滚**：恢复 schedule 段即可（≤5 分钟）。

## 五、方案 B/C 对比（为何不推荐/留档）

| 方案 | 内容 | 结论 |
|---|---|---|
| B. self-hosted runner | VPS 注册为 GH runner，workflow 零改动 | **不推荐**：调度仍在 GitHub（cron 丢弃问题原样保留），只治 IP 不治调度；常驻 agent + 安全面扩大 |
| C. VPS 全接管 | 采集+构建+wrangler 部署全在 VPS，GitHub 仅代码镜像 | 留作演进：根治所有 GitHub 依赖，但需装 Node22、迁移 CLOUDFLARE_API_TOKEN、重写自检链。仅当 VPS→GitHub 长期不可达时启用 |

## 六、实施 checklist（人工确认后执行）

- [ ] VPS 核对清单（§三）全部通过（尤其 github.com 可达）
- [ ] 生成 fine-grained PAT（Contents:RW，90 天轮换提醒）
- [ ] VPS 环境 + clone + 三个 cron + 提交脚本 + flock + logrotate
- [ ] PR：新增 deploy-pages.yml + 注释三个 schedule 段
- [ ] 双跑 1 周比对日志（重点关注 close_snapshot WRITTEN/SKIP 与 margin 状态）
- [ ] 切换：注释 GitHub schedule → 观察 3 个交易日
- [ ] 更新 CLAUDE.md「自动更新链路」章节 + PENDING_HUMAN_DECISIONS 勾销 §3/§4
