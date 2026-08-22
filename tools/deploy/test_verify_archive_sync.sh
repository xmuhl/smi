#!/usr/bin/env bash
# verify_archive_sync.sh 离线自测（R13-P3-04 回归，CI ubuntu 运行）：
# 场景 1：optional absent          → PASS
# 场景 2：optional present + match → PASS
# 场景 3：optional present + mismatch → FAIL（存在则必须一致）
# 附带：required mismatch → FAIL
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$ROOT/verify_archive_sync.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

failures=0

make_local() {
  # $1 = 目录；生成 4 个必需文件（可选第 5 个由调用方决定）
  local dir="$1"
  mkdir -p "$dir"
  for f in track-board-close track-board-flow limit-up-pool industry-universe-snapshot; do
    echo "{\"date\":\"2026-08-20\",\"src\":\"$f\"}" > "$dir/$f.jsonl"
  done
}

run_case() {
  local name="$1" expect="$2" local_dir="$3" remote_dir="$4"
  local out
  out="$(SMI_VERIFY_LOCAL_ROOT="$local_dir" \
        SMI_VERIFY_FAKE_REMOTE_DIR="$remote_dir" \
        SMI_VERIFY_SLEEP=0 \
        bash "$SCRIPT" 2>&1)"
  local code=$?
  if [ "$expect" = "PASS" ] && [ "$code" -eq 0 ]; then
    echo "PASS: $name"
  elif [ "$expect" = "FAIL" ] && [ "$code" -ne 0 ]; then
    echo "PASS: $name (rejected as expected)"
  else
    echo "FAIL: $name (expected $expect, exit=$code)"
    echo "$out" | tail -5
    failures=$((failures + 1))
  fi
}

# 场景 1：optional 本地缺失 → PASS
L1="$WORK/l1"; R1="$WORK/r1"
make_local "$L1"; make_local "$R1"
run_case "optional absent -> PASS" PASS "$L1" "$R1"

# 场景 2：optional 本地存在且线上一致 → PASS
L2="$WORK/l2"; R2="$WORK/r2"
make_local "$L2"; make_local "$R2"
echo '{"member":true}' > "$L2/track-membership-snapshot.jsonl"
cp "$L2/track-membership-snapshot.jsonl" "$R2/track-membership-snapshot.jsonl"
run_case "optional present+match -> PASS" PASS "$L2" "$R2"

# 场景 3：optional 本地存在但线上不一致 → FAIL
L3="$WORK/l3"; R3="$WORK/r3"
make_local "$L3"; make_local "$R3"
echo '{"member":true}' > "$L3/track-membership-snapshot.jsonl"
echo '{"member":false}' > "$R3/track-membership-snapshot.jsonl"
run_case "optional present+mismatch -> FAIL" FAIL "$L3" "$R3"

# 场景 4：required 不一致 → FAIL
L4="$WORK/l4"; R4="$WORK/r4"
make_local "$L4"; make_local "$R4"
echo '{"tampered":1}' > "$R4/limit-up-pool.jsonl"
run_case "required mismatch -> FAIL" FAIL "$L4" "$R4"

if [ "$failures" -ne 0 ]; then
  echo "SELFTEST_FAILURES=$failures"
  exit 1
fi
echo "SELFTEST_ALL_PASS"
