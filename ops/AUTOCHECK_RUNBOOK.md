# SMI 网站数据自动检查 Runbook（定时任务提示词模板）

> 用途：跨平台调度兜底。GitHub cron 整体丢弃（2026-08-27 部分丢 / 08-28 全天丢，
> 两起事故均发生）时，本机侧调度是唯一能发现断更的通道。
> 状态：**待人工接入调度**——本会话工具集无 CronCreate，无法自动创建定时任务。

## 建议调度

| 时点（CST） | 检查内容 | 说明 |
|---|---|---|
| 工作日 20:30 | 当日快照新鲜度 + 昨日两融 FINAL | 最后采集窗口 19:23 + 部署耗时后；覆盖全部日更链路 |
| （可选）工作日 10:50 | 次晨 margin T+1 回补核验 | t1-reconcile 10:17 窗口 + catchup 10:40 之后的复核 |

## 定时任务提示词（可直接粘贴给 ZCode 定时自动化 / Windows 计划任务包装器）

```text
SMI 网站当日数据例行检查（工作日 20:30 CST）。严格按以下步骤执行，全程自主，
遇到需要人工裁决的事项写入 C:\Users\huangl\Desktop\SMI\smi\work\PENDING_HUMAN_DECISIONS.md
并继续其余工作。

1. 检查线上新鲜度：curl -s https://smi-6s2.pages.dev/data/latest.json，确认 tradeDate
   是否为今日（CST 交易日）。若是今日且 overallStatus 非 ERROR → 检查通过，简要报告后
   结束（同时抽查 margin 模块：昨日两融应为 FINAL；若 ERROR 参照步骤 3 的本机回补）。
2. 若 tradeDate 滞后（非今日），按 runbook 排障：
   a. 查 GitHub Actions 是否有当日运行（API：curl -s --proxy http://127.0.0.1:10808
      -H "Authorization: Bearer <token>"
      "https://api.github.com/repos/xmuhl/smi/actions/runs?per_page=15"，token 用
      printf "protocol=https\nhost=github.com\n\n" | git credential fill 在
      C:/Users/huangl/Desktop/SMI/smi 下获取）。零运行/缺窗口 = GitHub cron 丢弃
      （08-27/08-28 已发生过）。
   b. 若有失败运行，下载日志看失败步骤，区分：spot 源被封（等下一窗口或 dispatch 重试）、
      门禁拦截（数据源问题）、runner IP 被重置（margin 类 → 本机兜底：cd
      C:/Users/huangl/Desktop/SMI/smi && 清空代理 env（export HTTP_PROXY= HTTPS_PROXY=
      NO_PROXY='*'）后 PYTHONPATH=. .venv/Scripts/python.exe -m
      collector.jobs.t1_reconcile --date <缺口日>，然后 git push）。
   c. 检查归档是否有盘前脏数据（tradeDate=今日 但 capturedAt<16:00 的行，2026-08-28
      事故模式）：python 解析 C:/Users/huangl/Desktop/SMI/smi/web/public/data/archive/*.jsonl。
      若有脏行：删除这些行、先 git fetch origin && git pull --rebase、提交推送。
3. 恢复发布（顺序硬约束，不可反序）：先 dispatch archive-raw（POST
   .../actions/workflows/archive-raw.yml/dispatches -d '{"ref":"main","inputs":{"date":"auto"}}'，
   204=成功），等该 run conclusion=success（轮询 API）；再 dispatch close-snapshot（同理
   close-snapshot.yml）。close-snapshot 会采集+commit+部署+自检（SITE_LATEST_EXACT_MATCH）。
4. 验证：run 绿后 curl 线上 latest.json 确认 tradeDate=今日；用 MCP webReader 工具核对
   https://smi-6s2.pages.dev 首页内容与 /data/daily/<年>/<今日>.json 可访问、9 模块状态、
   tracks 非 UNAVAILABLE。
5. 报告：结论写清「发现什么问题→做了什么→线上现状」，并更新
   C:\Users\huangl\Desktop\SMI\smi\work\ 下的当日检查记录文件（CHECKLOG_YYYYMMDD.md，追加即可）。
   若本次无任何问题，一句话报告即可。
6. 边界：不得绕过任何 fail-closed 门禁强行发布；盘前（16:00 CST 前）不得 dispatch 采集
   当日；连续两次恢复失败 → 停止重试，写 PENDING_HUMAN_DECISIONS.md 并在报告中醒目标注
   等待人工。

背景文档：C:\Users\huangl\Desktop\SMI\smi\CLAUDE.md（环境铁律：采集前清代理、THS 禁重试
并发）、work/INCIDENT_20260828_RECOVERY.md（历史事故与恢复 runbook）。
```

## 为什么必须跨平台

08-27 上线的 freshness-watchdog 与主链路同为 GitHub cron 触发。08-28 GitHub 当日全丢
（scheduled 触发不进状态页、零告警），看门狗同批阵亡——**同平台第二 cron 不是兜底**。
本机调度（ZCode 定时 / Windows 计划任务 / Cloudflare Worker Cron 三选一及以上）才能
构成真正的双平面。Cloudflare Worker 方案见 PENDING_HUMAN_DECISIONS.md §2。
