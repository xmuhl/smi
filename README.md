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

### 前端（Node 20+）

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
