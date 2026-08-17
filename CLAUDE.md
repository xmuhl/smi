# SMI — Stock Market Intelligence

## 项目概述

A股收盘全景 Web 看板。Python 采集 + Vue3 前端 + Cloudflare Pages 托管。
每日自动采集 9 大模块收盘数据，生成 JSON 快照，构建部署到 Pages。

## 环境铁律（踩坑必读）

- **采集前必须清代理**：`$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'`（否则 v2rayN 代理导致挂起）
- **THS 板块历史必须串行**：akshare 内部 py_mini_racer.dll 并发崩溃，`_THS_HIST_CONCURRENCY=1`
- **组合 pytest 可能挂起**（含网络测试），按文件单独跑（如 `python -m pytest collector/tests/test_core.py -q`）
- **git 两提交法**：先提交代码/数据（输入树），再单独提交验收报告（report-only commit）

## 架构

```
Python(AKShare) 采集 → web/public/data/daily/YYYY/YYYY-MM-DD.json (9 大模块)
→ Vue3 前端 → Cloudflare Pages (smi-6s2.pages.dev / smi.gorestart.cn 双域)
```

9 大模块：marketIndex / turnover / sentiment / sectorPerformance / fundFlow / northbound / margin / tracks / summary

## 生产域

| 域名 | 用途 | 状态 |
|------|------|------|
| `smi-6s2.pages.dev` | Cloudflare Pages 默认域 | ✅ 生产 |
| `smi.gorestart.cn` | 自定义域名（阿里云 CNAME） | ✅ 生产 |

## 自动更新链路（GitHub Actions）

| 工作流 | 触发 | 功能 |
|--------|------|------|
| `close-snapshot.yml` | Cron 工作日 16:23 CST | 采集 → commit → build → Pages 部署 |
| `t1-reconcile.yml` | 手动/自动 | 补昨日两融数据（T+1 回补） |
| `archive-raw.yml` | 手动 | 逐日归档原始数据 |
| `ci.yml` | Push to main | 类型检查 + 测试 + 构建验证 |

## 关键命令速查

```powershell
# 清代理 + 全量验收
$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:NO_PROXY='*'; $env:PYTHONPATH='.'
python tools/acceptance/accept.py --all --report work/acceptance/report.json

# 单日验收
python tools/acceptance/accept.py --date YYYY-MM-DD

# 回补单日
python -m collector.jobs.backfill_loop --start YYYY-MM-DD --end YYYY-MM-DD --force

# 两融回补
python -m collector.jobs.t1_reconcile --date YYYY-MM-DD

# 单独跑测试
python -m pytest collector/tests/test_core.py -q
python -m pytest tools/acceptance/test_accept.py -q
```

## 验收

- 验收器：`tools/acceptance/accept.py`（读标准 `docs/acceptance/template-standard.json`）
- 历史覆盖 Profile：`docs/acceptance/historical-profile.json`（产品裁决已知边界）
- 最新 clean 报告：`work/acceptance/p1_r9_final_c7.json`（dirty=false，绑定 c7de51b）
- 页面探针：`tools/acceptance/page_check.js`（`window.__smiPageCheck()`）

## 已知边界（产品裁决 v1）

| 模块 | 历史缺口 | 状态 |
|------|----------|------|
| sentiment | riseCount/fallCount/flatCount 等无免费历史源 | PARTIAL/UNAVAILABLE |
| fundFlow | stockInflowTop10/OutflowTop10 无历史源；push2his 封禁 | UNAVAILABLE/PARTIAL |
| tracks | 量化输入底座不足（mainNetInflow/excessReturn20d 等） | UNAVAILABLE |
| 07-20~07-24 | 涨停池保留窗口外不可恢复 | UNRECOVERABLE |

## 深入文档

| 文档 | 说明 |
|------|------|
| `docs/SMI-V1-Design-V1.1.md` | 完整设计文档（架构、数据源、验收标准） |
| `docs/acceptance/template-standard.md` | 验收标准（人类可读版） |
| `docs/acceptance/template-standard.json` | 验收标准（机器可读，单一真源） |
| `docs/acceptance/historical-profile.md` | 历史覆盖合同（产品裁决 v1） |
| `docs/acceptance/historical-profile.json` | 历史覆盖合同（机器可读） |
| `work/SMI_HANDOVER.md` | 任务交接手册（含完整命令速查） |
| `work/acceptance/*.json` | 验收报告存档 |
