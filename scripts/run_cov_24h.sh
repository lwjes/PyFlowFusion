#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
COV_RECORD_DIR="$PROJECT_ROOT/workspace/cov_record"
BUILD_ROOT="$PROJECT_ROOT/workspace/python-cov"
RUN_LOG="$COV_RECORD_DIR/run_24h.log"
CSV_PATH="$COV_RECORD_DIR/coverage_24h.csv"

mkdir -p "$COV_RECORD_DIR"
find "$BUILD_ROOT" -name '*.gcda' -delete
find "$COV_RECORD_DIR" -maxdepth 1 -type f -name 'gcovr-*.xml' -delete
rm -f "$RUN_LOG" "$CSV_PATH"

if ! command -v gcovr >/dev/null 2>&1; then
  echo "[run_cov_24h] gcovr command not found in PATH" | tee "$RUN_LOG"
  exit 1
fi

PYTHONUNBUFFERED=1 timeout --signal=INT --kill-after=30s 24h \
  python3 -m flowfusion > "$RUN_LOG" 2>&1 &
RUN_PID=$!

wait "$RUN_PID" || true
python3 scripts/rebuild_coverage_csv.py \
  --cov-record-dir "$COV_RECORD_DIR" \
  --output "$CSV_PATH"
