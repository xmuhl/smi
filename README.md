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

## 当前状态（2026-08-23，R28 收敛基线）

- ✅ **网站已上线**：https://smi.gorestart.cn / https://smi-6s2.pages.dev（双域，开/关代理均可访问）
- ✅ **交易日数据连续**：2026-07-17 ~ 2026-08-21
- ✅ **主赛道范本严格口径**（R22-R28 迭代收敛，ChatGPT 评审 0 NOT_CLOSED）：
  - 当日监测口径前 5 直接入选（半导体/通信设备/元件/高股息中特估[概念口径联合排名]/化学制药），无确认延迟
  - 两层资格展示（当日入选 / 观察保留徽标）；排名口径元数据（行业/概念注入/复合主腿）显式标注
  - 无数据日诚实空表（区分"上游不可用"与"无符合条件主赛道"）；历史无快照日（07-20~08-19）不再显示占位板块
- ✅ **CI 全绿**：测试 312 项 + acceptance PASS=3（07-17/08-20/08-21）
- 📅 待观察：周一 2026-08-24 首个 3.5 语义自动滚动日

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
