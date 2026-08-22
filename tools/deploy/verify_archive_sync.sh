#!/usr/bin/env bash
# archive-raw 发布自检（R13-P3-04 / R15 修订）：
#   必需集合完备 + 内容一致；optional 语义严格化——
#   optional absent = warning（允许缺失，产品裁决的诚实缺口）
#   optional present = exact-match required（存在则必须一致，否则 FAIL）
# 环境变量（测试/排障用，生产 workflow 不设）：
#   SMI_VERIFY_LOCAL_ROOT    本地归档目录（默认 web/dist/data/archive）
#   SMI_VERIFY_REMOTE_BASE   线上基址（默认生产 Pages）
#   SMI_VERIFY_FAKE_REMOTE_DIR  伪远程目录（离线自测：以 cp 替代 curl）
#   SMI_VERIFY_SLEEP         重试间隔秒（默认 20，自测设 0）
set -euo pipefail

LOCAL_ROOT="${SMI_VERIFY_LOCAL_ROOT:-web/dist/data/archive}"
BASE="${SMI_VERIFY_REMOTE_BASE:-https://smi-6s2.pages.dev/data/archive}"
SLEEP_SECS="${SMI_VERIFY_SLEEP:-20}"

REQUIRED_FILES="track-board-close track-board-flow limit-up-pool industry-universe-snapshot"
OPTIONAL_FILES="track-membership-snapshot"

ok=1
required=0
checked=0

fetch_remote() {
  local f="$1" out="$2"
  if [ -n "${SMI_VERIFY_FAKE_REMOTE_DIR:-}" ]; then
    cp -f "$SMI_VERIFY_FAKE_REMOTE_DIR/$f.jsonl" "$out" 2>/dev/null
  else
    curl -fsS --max-time 20 -H 'Cache-Control: no-cache' "$BASE/$f.jsonl" -o "$out"
  fi
}

check_one() {
  local f="$1"
  local required_flag="$2"
  local LOCAL="$LOCAL_ROOT/$f.jsonl"

  if [ ! -s "$LOCAL" ]; then
    if [ "$required_flag" = "required" ]; then
      echo "REQUIRED_LOCAL_ARCHIVE_MISSING_OR_EMPTY: $LOCAL"
      ok=0
    else
      echo "OPTIONAL_LOCAL_ARCHIVE_MISSING: $LOCAL (warning only)"
    fi
    return
  fi

  checked=$((checked + 1))
  local LOCAL_SHA256
  LOCAL_SHA256="$(sha256sum "$LOCAL" | cut -d' ' -f1)"

  local matched=0
  for attempt in 1 2 3 4 5 6; do
    [ "$SLEEP_SECS" != "0" ] && sleep "$SLEEP_SECS"

    local REMOTE="/tmp/smi-$f.jsonl"
    rm -f "$REMOTE"

    if ! fetch_remote "$f" "$REMOTE"; then
      echo "attempt=$attempt $f unreachable"
      continue
    fi

    local SITE_SHA256
    SITE_SHA256="$(sha256sum "$REMOTE" | cut -d' ' -f1)"

    if [ "$SITE_SHA256" = "$LOCAL_SHA256" ]; then
      echo "MATCH $f.jsonl sha256=$SITE_SHA256"
      matched=1
      break
    fi

    echo "attempt=$attempt $f mismatch (local=$LOCAL_SHA256 site=$SITE_SHA256)"
  done

  if [ "$matched" != "1" ]; then
    # R15：optional 存在则必须一致（present = exact-match required）
    if [ "$required_flag" = "required" ]; then
      echo "REQUIRED_ARCHIVE_MISMATCH: $f.jsonl"
    else
      echo "OPTIONAL_ARCHIVE_MISMATCH: $f.jsonl (present => exact-match required)"
    fi
    ok=0
  fi
}

for f in $REQUIRED_FILES; do
  required=$((required + 1))
  check_one "$f" required
done
for f in $OPTIONAL_FILES; do
  check_one "$f" optional
done

if [ "$checked" -lt "$required" ]; then
  echo "LOCAL_ARCHIVE_SET_INCOMPLETE: checked=$checked required=$required"
  ok=0
fi

if [ "$ok" != "1" ]; then
  echo "SITE_ARCHIVE_INCOMPLETE_OR_MISMATCH"
  exit 1
fi

echo "SITE_ARCHIVE_EXACT_MATCH"
