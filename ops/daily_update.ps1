# SMI 每日收盘自动更新：采集 -> 验证 -> 构建 -> 部署 Cloudflare Pages
# 方案 A（GitHub 单一权威）部署后：日常由 GitHub Actions 完成，
# 本脚本仅作为应急工具（GitHub 链路故障时手工启用），
# 所以加了显式 OPERATOR_CONFIRM 守卫 -- 不允许无意识自动跑。
$ErrorActionPreference = "Continue"
$root = "C:\Users\huangl\Desktop\SMI\smi"
$logDir = "C:\Users\huangl\Desktop\SMI\work\logs"

if ($env:OPERATOR_CONFIRM -ne "SMI-EMERGENCY-OK") {
  Write-Host "=== 应应急模式 ==="
  Write-Host "本脚本当前部署为 GitHub Actions 单一权威，应急时才使用。"
  Write-Host "需要执行前设置环境变量 OPERATOR_CONFIRM=SMI-EMERGENCY-OK"
  Write-Host "并保证从 GitHub main 拉取最新数据后手工启动"
  exit 0
}

Write-Host "=== EMERGENCY FALLBACK MODE ==="
# 2026-08-16 实测铁律：本机采集必须清系统代理直连（akshare 请求继承 HTTP_PROXY 会走 v2rayN 挂起）
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:NO_PROXY = "*"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$log = Join-Path $logDir ("daily_" + $stamp + ".log")
function Log($msg) { Write-Output ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg) | Tee-Object -FilePath $log -Append }

Set-Location $root
$py = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $py)) {
  Log "ERROR: venv python not found at $py"
  exit 1
}

# 1) 收盘快照（自动解析最新交易日；非交易日/未收盘自动安全退出）
Log "STEP 1/4: close_snapshot --date auto"
& $py -m collector.jobs.close_snapshot --date auto 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
Log "close_snapshot exit=$code"
if ($code -ne 0) {
  Log "SKIP: close_snapshot failed (exit=$code), no deploy"
  exit $code
}

# 2) 前端构建
Log "STEP 2/4: npm run build"
Set-Location (Join-Path $root "web")
npm run build 2>&1 | Tee-Object -FilePath $log -Append
$buildCode = $LASTEXITCODE
Log "build exit=$buildCode"
if ($buildCode -ne 0) {
  Log "SKIP: build failed, no deploy"
  exit $buildCode
}

# 3) 部署到 Cloudflare Pages
Log "STEP 3/4: wrangler pages deploy"
npx wrangler pages deploy dist --project-name smi --branch main --commit-dirty=true 2>&1 | Tee-Object -FilePath $log -Append
$deployCode = $LASTEXITCODE
Log "deploy exit=$deployCode"

# 4) 清理旧日志（保留 30 天）
Log "STEP 4/4: cleanup old logs"
Get-ChildItem $logDir -Filter "daily_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
Log "DONE exit=$deployCode"
exit $deployCode
