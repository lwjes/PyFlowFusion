#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
CONFIG_PATH="$PROJECT_ROOT/configs/python_san.py"
TMP_DIR="$PROJECT_ROOT/workspace/tmp_dir"
PY_FUSED_DIR="$PROJECT_ROOT/workspace/py_fused"
BUGS_DIR="$PROJECT_ROOT/workspace/bugs"
FIXME_DIR="$PROJECT_ROOT/workspace/fixme"
SAN_RECORD_DIR="$PROJECT_ROOT/workspace/san_record"
RUN_LOG="$SAN_RECORD_DIR/run_24h.log"
STATUS_FILE="$SAN_RECORD_DIR/status.txt"
SUMMARY_FILE="$SAN_RECORD_DIR/summary.txt"

mkdir -p "$TMP_DIR" "$PY_FUSED_DIR" "$BUGS_DIR" "$FIXME_DIR" "$SAN_RECORD_DIR"

find "$TMP_DIR" -mindepth 1 -delete
find "$PY_FUSED_DIR" -mindepth 1 -delete
find "$BUGS_DIR" -mindepth 1 -delete
find "$FIXME_DIR" -mindepth 1 -delete
find "$SAN_RECORD_DIR" -mindepth 1 -delete

mkdir -p "$SAN_RECORD_DIR"

{
  echo "status=running"
  echo "start_time=$(date -Is)"
  echo "config=$CONFIG_PATH"
  echo "python_bin=$PROJECT_ROOT/workspace/python-san/python"
} > "$STATUS_FILE"

set +e
env \
  FLOWFUSION_CONFIG="$CONFIG_PATH" \
  PYTHONUNBUFFERED=1 \
  ASAN_OPTIONS="detect_leaks=0:abort_on_error=1" \
  UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1" \
  LSAN_OPTIONS="detect_leaks=0" \
  timeout --signal=INT --kill-after=30s 24h \
  python3 -m flowfusion > "$RUN_LOG" 2>&1
RC=$?
set -e

BUG_COUNT=0
FIXME_COUNT=0

if [[ -d "$BUGS_DIR" ]]; then
  BUG_COUNT="$(find "$BUGS_DIR" -mindepth 1 -maxdepth 1 | wc -l)"
fi

if [[ -d "$FIXME_DIR" ]]; then
  FIXME_COUNT="$(find "$FIXME_DIR" -mindepth 1 -maxdepth 1 | wc -l)"
fi

{
  echo "status=finished"
  echo "end_time=$(date -Is)"
  echo "return_code=$RC"
  echo "bug_count=$BUG_COUNT"
  echo "fixme_count=$FIXME_COUNT"
} >> "$STATUS_FILE"

{
  echo "return_code=$RC"
  echo "bug_count=$BUG_COUNT"
  echo "fixme_count=$FIXME_COUNT"
} > "$SUMMARY_FILE"

exit "$RC"
