#!/bin/bash
# SMI VPS 采集任务包装器（VPS_MIGRATION_PROGRESS_20260901 任务 6）
# 用法: run_job.sh <close_snapshot|archive_raw|t1_reconcile> [job 额外参数...]
# 职责: 运行 job → 数据变化则 commit + push（重试 3 次间隔 60s，失败飞书
#       告警、数据留本地等下窗口自动补推）→ 数据健康告警收尾
# 重叠防护由 crontab 的 flock -n 承担（每 job 独立 lock 文件）
set -uo pipefail

JOB="${1:?usage: run_job.sh <close_snapshot|archive_raw|t1_reconcile> [args...]}"
shift || true

REPO=/opt/smi
LOG_DIR="$REPO/logs"
VENV="$REPO/.venv/bin"
export PYTHONPATH="$REPO"
export SMI_WORKFLOW="vps-$JOB"

# 密钥/钩子环境变量（FEISHU_WEBHOOK_URL 等），不存在则静默跳过
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
fi

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${JOB}_$(date +%F).log"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

cd "$REPO" || exit 1

# ---- 1. 采集（自动拉平远端，避免在旧基线上写数据）----
log "RUN_BEGIN $JOB args=$*"
git pull --rebase --autostash >> "$LOG" 2>&1 || log "PULL_FAIL (继续，推送阶段再拉平)"

# close_snapshot freshness 守卫（GitHub workflow YAML schedule 守卫的 VPS
# 等价物）：当日 daily 文件已存在（本侧 16:23 已发布，或双跑期 GitHub 侧
# 先发布）即跳过采集——18:23/19:23 自愈窗口零成本；仅在未发布时重试。
# t1/archive 的守卫在 job 内部（ALREADY_FINAL / ALREADY_ARCHIVED）。
if [ "$JOB" = "close_snapshot" ]; then
  TODAY="$(TZ=Asia/Shanghai date +%F)"
  if [ -f "web/public/data/daily/${TODAY%%-*}/${TODAY}.json" ]; then
    log "SKIP_ALREADY_PUBLISHED ${TODAY}"
    log "JOB_DONE $JOB (skip)"
    exit 0
  fi
fi

"$VENV/python" -m "collector.jobs.$JOB" "$@" >> "$LOG" 2>&1
rc=$?
log "RUN_END rc=$rc"

# ---- 2. 提交推送（rc=0 正常 / rc=3 BEFORE_CLOSE 良性跳过也可能有滞留补推）----
if [ "$rc" -eq 0 ] || [ "$rc" -eq 3 ]; then
  git add web/public/data
  if git diff --cached --quiet; then
    log "NO_DATA_CHANGE"
  else
    git commit -m "data: $JOB (vps)" >> "$LOG" 2>&1
    pushed=0
    for i in 1 2 3; do
      if git pull --rebase >> "$LOG" 2>&1 && git push >> "$LOG" 2>&1; then
        pushed=1; log "PUSH_OK attempt=$i"; break
      fi
      log "PUSH_FAIL attempt=$i"; [ "$i" -lt 3 ] && sleep 60
    done
    if [ "$pushed" -eq 0 ]; then
      log "PUSH_GAVE_UP 数据留本地，下一窗口 freshness 跳过后由本段自动补推"
      if [ -n "${FEISHU_WEBHOOK_URL:-}" ]; then
        curl -s -m 10 -X POST -H 'Content-Type: application/json' \
          -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"[SMI] VPS push 失败 3 次: ${JOB}，数据留本地待下窗口补推\"}}" \
          "$FEISHU_WEBHOOK_URL" >> "$LOG" 2>&1 || true
      fi
    fi
  fi
fi

# ---- 3. 数据健康告警（P0-b 同口径；webhook 未配置时降级为日志，不阻塞）----
case "$JOB" in
  close_snapshot) HEALTH_MODE=close-snapshot ;;
  t1_reconcile)   HEALTH_MODE=t1-reconcile ;;
  *)              HEALTH_MODE=generic ;;
esac
"$VENV/python" tools/alert/data_health.py --mode "$HEALTH_MODE" >> "$LOG" 2>&1 \
  && log "HEALTH_OK" || log "HEALTH_NONZERO (详见上方输出)"

log "JOB_DONE $JOB"
exit "$rc"
