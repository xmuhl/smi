# SMI - Stock Market Intelligence

A股收盘全景 Web 看板：每日自动采集 A 股收盘数据，支持历史回查。

## 技术架构

- 数据采集：Python + AKShare + 官方公开数据源
- 数据存储：`web/public/data/` 每日一个 JSON 快照
- 前端：Vue 3 + Vite + TypeScript + ECharts
- 托管：Cloudflare Pages（免费）

## 数据源口径（V1 固定）

| 数据类别 | 口径 |
|---|---|
| 宽基指数 | 东方财富 + 国证指数 |
| 板块行情 | 东方财富行业/概念板块 |
| 主力资金 | 东方财富资金流 |
| 北向资金 | HKEX 季度持仓（QUARTERLY_ONLY），日度字段 UNAVAILABLE |
| 两融 | SSE + SZSE 官方数据（T+1 披露） |
| 历史 Excel | TONGDAXIN_LEGACY 标记 |

## 快速开始

### 数据采集（Python 3.11+）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r collector\requirements.txt

# 生成最新交易日快照
python -m collector.jobs.close_snapshot --date auto

# 补跑指定日期
python -m collector.jobs.manual_backfill --date 2026-07-17
```

### 前端（Node 22+，wrangler 4.x 硬要求）

```powershell
cd web
npm ci
npm run dev        # 本地开发 http://localhost:5173
npm run build      # 构建产物 dist/
```

## 目录结构

```
smi/
├── collector/            # Python 数据采集
│   ├── adapters/         # 数据源适配器
│   ├── modules/          # 9 大模块采集
│   ├── calculators/      # 指标计算
│   ├── validators/       # 数据校验
│   ├── jobs/             # 任务入口
│   └── legacy/           # Excel 导入
├── web/                  # Vue 前端
│   ├── src/
│   └── public/data/      # 每日 JSON 快照（构建时复制到 dist）
├── config/               # 配置（赛道、评分、阈值）
├── docs/                 # 设计文档
└── .github/workflows/    # GitHub Actions
```

详细设计见 `docs/SMI-V1-Design-V1.1.md`。

## 当前状态（2026-08-20，R12）

- ✅ **网站已上线**：https://smi-6s2.pages.dev / https://smi.gorestart.cn
- ✅ **交易日数据连续**：2026-07-17 ~ 2026-08-20（08-18 已回补）
- ✅ **自动更新链路修复**（R12）：部署 Node 22（曾致 Actions 部署从未成功、站点停留 08-17）+ 采集超时护栏 + 部署后站点自检
- ✅ **主赛道动态化**（R12）：每日按全市场板块数据（近 5 日成交额排名 + 当日净流入）自动选出动态候选，与种子赛道合并评分；四级判定（核心主赛道/次主线/短线支线/一日游脉冲）
- ✅ **CI 全绿**（8-17 以来首次，根因：测试进程 sys.modules 泄漏）

### GitHub Actions 自动更新

| 工作流 | 时间（CST） | 作用 |
|---|---|---|
| close-snapshot | 工作日 16:23 | 采集 → 部署 → 站点自检 |
| archive-raw | 工作日 16:35 | 归档 + 候选历史回补 → 部署 → md5 自检 |
| t1-reconcile | 工作日 10:17 / 18:17 | 两融 T+1 回补 → 部署 |

**前置条件**：GitHub Secrets 需配置：
- `CLOUDFLARE_API_TOKEN` — Cloudflare API 令牌（Pages 部署权限）
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare 账户 ID

### 页面验收

在生产浏览器控制台执行 `window.__smiPageCheck()` 可验证 9 大面板渲染状态。
探针代码：`tools/acceptance/page_check.js`
