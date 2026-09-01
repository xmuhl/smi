# VPS 迁移进度与剩余任务清单（2026-09-01）

> 状态：**勘察完成，待决定性验证（SSH-over-443）→ 环境实施 → 双跑 → 切换 → 上线验收**
> 方案：`PLAN_DOMESTIC_MIGRATION.md`（方案 A：VPS 采集 + GitHub 构建部署）
> 关联：`PENDING_HUMAN_DECISIONS.md` §1/§3/§4；09-01 事故记录见 `CLAUDE.md` 当前状态
> 本文档由 2026-09-01 勘察会话产出，作为迁移实施的进度真源，随任务推进更新勾选

## 一、背景与目标

2026-09-01 GitHub 托管侧第 3 次调度大面积延迟/丢弃（08-27/08-28 同源），叠加 runner
海外 IP 被交易所拒导致 margin 两日缺口。用户裁决启动国内 VPS 迁移，摆脱「调度丢弃 +
runner IP 封锁」双重结构性风险。

目标实例（已勘察确认）：阿里云华北2（北京）`i-2zeabtvhmpf263ll3emq`
（iZ2zeabtvhmpf263ll3emqZ），公网 47.95.232.146。

## 二、今日已完成（2026-09-01）

1. **09-01 断更事故处置（全部完成）**
   - margin 缺口本机回补：08-28/08-31 → FINAL（提交 `9ad003e`），环比链 -60.09/+56.00，
     两日 acceptance PASS、margin failDates=0
   - dispatch close-snapshot（deploy=true）run#47 success 重采部署（`d07cc80`），
     09-01 margin latestPublishedReference 刷至 08-31，线上核验通过
   - watchdog 设计修订：today 巡检 16:00 CST 前良性跳过，不派发不误报
     （`9719a46`，3 例离线回归测试；全量 pytest 259 passed + 1 skipped）
   - CLAUDE.md 事故记录 + watchdog 行为同步（`ba7490a`）
2. **治理包核验**：SMI `.governance/` 与权威源包 ai-governance.zip（15 条目，
   2026-08-31 引导链强化版）逐哈希一致 0 mismatch，确认最新
3. **VPS 控制台侧勘察**（只读；chrome-devtools 驱动控制台 + 云助手发送 3 轮只读命令）

## 三、VPS 勘察结果（已核实事实）

| 项 | 结果 | 对方案影响 |
|---|---|---|
| 实例状态 | 运行中、健康正常，CPU ~2.8% | ✓ |
| 规格/资源 | 2C / 2GiB（`free -h` 可用 1.0Gi）/ 40G 盘（已用 21%） | 满足 §三；内存偏紧，实施时配 2G swap |
| OS | Ubuntu 22.04.5 LTS | ✓ |
| Python | 3.10.12 + pip 22.0.2 | ⚠️ 需 ≥3.11（apt universe 优先，后备 deadsnakes/Miniconda 镜像） |
| git | 2.34.1 | ✓ |
| 时区 | Asia/Shanghai (CST, +0800) | ✓ cron 无需 UTC 换算 |
| 云助手 | 正常（版本 2.2.4.1097），发送命令可用 | ✓ 免 SSH 运维通道成立 |
| cron 服务 | active | ✓ |
| 网络 | VPC vpc-2zes9qrh1jrka82pbhlqh / 交换机 vsw-2zembpr5qikyc3tzkykl4 / 私网 172.21.193.90 | 记录在案 |
| 公网带宽 | 47.95.232.146，固定 3 Mbps | JSON 提交（数百 KB/日）无压力 |
| 安全组 | sg-2ze2uscueqbt6bb8eycg（唯一挂载）：入方向 80/443/22 全网放行；出方向默认全通 | 采集纯出方向，**无需改动**；22 全网开放+密码认证有爆破面（建议部署期收紧） |
| 本机→VPS | sshd 22 应答正常（publickey,password；本机未持凭证） | 部署通道可用（待凭证或继续走云助手） |
| 监控 | 云监控插件未装（内存/盘/网无指标） | 建议安装（观测内存水位） |
| 续费 | 手动续费，2027-04-03 到期 | 低优待办 |

### 云助手三轮命令关键证据

1. **§三核对清单**：os/python/cpu/mem/disk/tz/agent/cron 见上表；
   `curl -sI https://github.com` **空输出**（触发深入诊断）
2. **网络诊断（23:04）**：
   - DNS：github.com → 20.205.243.166 ✓
   - `https://github.com` → curl(28) 超时，0 字节 ✗
   - `https://api.github.com` → **200** ✓
   - `https://codeload.github.com` → **301** ✓
3. **连通复测（23:07）**：
   - `https://github.com` 再次 curl(28) 超时 ✗（**复现，非偶发**）
   - TCP 443 → ssh.github.com（20.205.243.160）**OPEN** ✓
   - TCP 443 → github.com OPEN，但 TLS 层挂起（TCP 通 + ClientHello 后无响应，SNI 干扰特征）
   - `git ls-remote https://github.com/xmuhl/smi.git HEAD` 20 秒零输出（挂起被 timeout 杀死）✗

### 关键结论

- **github.com HTTPS（含 git-over-HTTPS push）从该 VPS 不可用**——方案 A 唯一硬门槛
  （§三 ★）未直接通过。
- **api.github.com / codeload.github.com 可达**；**ssh.github.com:443 TCP 可达**
  （SSH 协议层未验证）。
- **方案 A 保留路径**：git 远端改用 `ssh://git@ssh.github.com:443/xmuhl/smi.git`
  （GitHub 官方备用端点，deploy key 认证，SSH 协议无 SNI 可被嗅探）。
- 若 SSH 协议层验证也失败，降级顺序：
  ① 改造提交脚本走 GitHub Contents API（api.github.com 可达，需新增改造工作量）；
  ② 方案 C（VPS 全接管：构建 + wrangler 部署本地化，GitHub 仅 API 镜像）；
  ③ Gitee 中继（新增第三方依赖，最后考虑）。

## 四、剩余任务（按序执行）

| # | 任务 | 依赖 | 验收标准 | 状态 |
|---|---|---|---|---|
| 1 | **决定性验证**：云助手跑 `ssh -p 443 -o BatchMode=yes -o StrictHostKeyChecking=no git@ssh.github.com`（预期快速返回 Permission denied(publickey) = 协议层可达） | 无 | SSH 握手 ≤10s 到达认证阶段 | ☐ |
| 2 | 凭证：VPS 生成 ed25519 deploy key → GitHub 仓库添加 Deploy Key（只授予该仓写权限）[或 fine-grained PAT Contents:RW，90 天轮换提醒] | 1 | `git ls-remote ssh://git@ssh.github.com:443/xmuhl/smi.git HEAD` 返回 HEAD | ☐ |
| 3 | Python 3.11：`apt install python3.11 python3.11-venv`（jammy universe）；不可则 deadsnakes PPA / Miniconda（tuna 镜像） | 无 | python3.11 --version ≥ 3.11 | ☐ |
| 4 | VPS 环境：clone 至 `/opt/smi`（remote 改 ssh-443）、venv、`pip install -r collector/requirements.txt` | 2,3 | venv 内 `import akshare` 成功；离线 pytest 全绿 | ☐ |
| 5 | 三 job 手动试运行：close_snapshot `--date <已发布日>`（预期 freshness SKIP）、t1_reconcile `--auto`（预期 ALREADY_FINAL）、archive_raw（盘后实跑） | 4 | 退出码与语义输出符合预期；不产生非预期写 | ☐ |
| 6 | cron + 提交脚本：三组 cron（`flock -n` 防重叠）、push 重试 3 次/60s、失败飞书；VPS 配 `FEISHU_WEBHOOK_URL` 环境变量（**顺带解决 PENDING §1 第三次提醒**） | 5 | crontab -l 生效；人为触发一条告警，飞书真实收到 | ☐ |
| 7 | **双跑观察 1 周**：GitHub cron 不动，VPS cron 上线，双侧 freshness 守卫互斥 | 6 | 一周日志无差异；每日发布只有一侧实际 WRITTEN，另一侧 SKIP | ☐ |
| 8 | GitHub 侧 PR（与 7 并行）：新增 `deploy-pages.yml`（push paths `web/public/data/**` → node22/npm ci/typecheck/build/wrangler deploy/EXACT_MATCH 自检）；注释 close-snapshot/archive-raw/t1-reconcile 的 schedule 段（保留 workflow_dispatch 后门） | 无 | PR CI 绿 | ☐ |
| 9 | 切换：合并 8（GitHub schedule 退役，VPS 为主）。回滚预案 = 恢复 schedule 段（≤5 分钟） | 7,8 | 切换后 3 个交易日 VPS 独立供数 | ☐ |
| 10 | **上线验收**（清单见 §五） | 9 | 全部通过 | ☐ |
| 11 | 收尾：CLAUDE.md「自动更新链路」章节改写 + PENDING §3/§4 勾销 + PLAN 状态更新 | 10 | 文档三处一致 | ☐ |

## 五、上线验收清单（任务 10，逐项留证）

- [ ] **数据完整性**：连续 3 个交易日（含至少一次 margin T+1 回补）九模块状态合规，
  无新增 failDates；tracks 监测表当日前 5 正常产出
- [ ] **验收器**：`accept.py --all` 报告不劣于现基线（07-17/08-20/08-21 PASS=3 保持）
- [ ] **线上指针**：manifest/status 三指针与 daily 一致；最新文件 `updatedAt ≥ 当日任务启动`；
  pages.dev 与 gorestart.cn 双域内容一致
- [ ] **调度可靠性**：VPS cron 连续一周 0 丢失（对照 GitHub 托管期 3 次事故）；
  如发生延迟补发，盘前守卫（16:00 BEFORE_CLOSE / archive 同阈）正确良性跳过
- [ ] **告警链路实测**：人为制造一次数据缺口（或测试 webhook），验证「红灯 + 飞书」
  双通道真实可达（VPS 直连飞书，正是迁移收益项）
- [ ] **双跑一致性抽查**：双跑期同日 JSON 业务语义哈希一致（剔除 VOLATILE_FIELDS：
  generatedAt/updatedAt/revision/generationReason）
- [ ] **运维底座**：logrotate 按日切割保留 30 天生效；磁盘水位 <60%；2G swap 在位；
  deploy key 权限最小化（单仓读写、无其它 scope）确认
- [ ] **回滚演练**：确认恢复 GitHub schedule 段可在 ≤5 分钟内生效（把操作步骤写进 PR 描述）

## 六、风险与未决项

- **R1 git 通道（最高）**：ssh.github.com:443 仅 TCP 层验证；SSH 协议层可达性（任务 1）
  与长稳性（是否间歇性干扰，双跑周内观察 push 成功率）待验证。后备 API 提交方案
  （api.github.com 可达）尚未设计。
- **R2 内存**：可用 1.0Gi，采集峰值 <1.5G 偏紧 → 实施时配 2G swap（阿里云 SWAP 配置
  扩展程序或手动 dd+mkswap）。
- **R3 带宽**：3 Mbps 固定——日常提交无压力；首次全量 clone 含历史归档体积待实测
  （一次性冷启动）。
- **R4 安全**：22 全网开放 + 密码认证为既有状态；建议部署完成后收紧安全组来源并改
  密钥登录（需人工决策，不在自动实施范围）。
- **R5 单点切换**：切换后 VPS cron 为唯一调度面（watchdog 保留为第二平面发现停滞）；
  VPS 宿主级宕机即断更——是否加 VPS 存活外测（如本机对 47.95.232.146 的探活）待人工决策。
- **R6 低优**：云监控插件未装（观测盲区）；实例手动续费（2027-04 到期，远期风险）。

## 七、今日变更物清单

- smi 仓提交：`9ad003e`（margin 回补）、`9719a46`（watchdog 修订+测试）、
  `d07cc80`（bot 重采）、`ba7490a`（CLAUDE.md 同步）、本文档
- 线上状态：08-28/08-31 margin FINAL；09-01 latestRef=08-31；部署 run#47 验证通过
- 阿里云控制台：仅只读勘察 + 云助手发送 3 条只读诊断命令，**无任何实例配置/状态变更**
- 治理源仓：无变更（SMI 治理包 15 条目已是最新，本轮未动）
