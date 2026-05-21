#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

RUN_ROOT="$PROJECT_ROOT/workspace/timing_record"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/$RUN_ID"
RUN_LOG="$RUN_DIR/run.log"

TMP_DIR="$PROJECT_ROOT/workspace/tmp_dir"
PY_FUSED_DIR="$PROJECT_ROOT/workspace/py_fused"
BUGS_DIR="$PROJECT_ROOT/workspace/bugs"
FIXME_DIR="$PROJECT_ROOT/workspace/fixme"
REAL_PYTHON_BIN="${FLOWFUSION_REAL_PYTHON_BIN:-$PROJECT_ROOT/workspace/python-cov/python}"

mkdir -p "$RUN_DIR" "$RUN_DIR/inflight"
mkdir -p "$TMP_DIR" "$PY_FUSED_DIR" "$BUGS_DIR" "$FIXME_DIR"

find "$TMP_DIR" -mindepth 1 -delete
find "$PY_FUSED_DIR" -mindepth 1 -delete
find "$BUGS_DIR" -mindepth 1 -delete
find "$FIXME_DIR" -mindepth 1 -delete

chmod +x "$PROJECT_ROOT/scripts/case_timer.py"

export FLOWFUSION_CONFIG="$PROJECT_ROOT/configs/timing_10000.py"
export FLOWFUSION_TIMING_PROXY_BIN="$PROJECT_ROOT/scripts/case_timer.py"
export FLOWFUSION_REAL_PYTHON_BIN="$REAL_PYTHON_BIN"
export FLOWFUSION_TIMING_RECORD_DIR="$RUN_DIR"
export FLOWFUSION_TIMING_CSV="$RUN_DIR/case_timing.csv"
export FLOWFUSION_FUSED_DIR="$PY_FUSED_DIR"
export FLOWFUSION_PY_DEPS_DIR="$PROJECT_ROOT/workspace/py_deps"
export FLOWFUSION_PY_SEEDS_DIR="$PROJECT_ROOT/workspace/py_seeds"
export FLOWFUSION_CPYTHON_ROOT="$PROJECT_ROOT/../cpython/cpython-src"
export FLOWFUSION_CASE_TIMEOUT=10
export FLOWFUSION_TIMER_MARGIN_MS="${FLOWFUSION_TIMER_MARGIN_MS:-150}"
export FLOWFUSION_MAX_HYDRATION_ATTEMPTS="${FLOWFUSION_MAX_HYDRATION_ATTEMPTS:-8}"
export PYTHONUNBUFFERED=1

{
  echo "run_id=$RUN_ID"
  echo "run_dir=$RUN_DIR"
  echo "config=$FLOWFUSION_CONFIG"
  echo "proxy_bin=$FLOWFUSION_TIMING_PROXY_BIN"
  echo "real_python_bin=$FLOWFUSION_REAL_PYTHON_BIN"
  echo "case_timeout=$FLOWFUSION_CASE_TIMEOUT"
  echo "timer_margin_ms=$FLOWFUSION_TIMER_MARGIN_MS"
  echo "max_hydration_attempts=$FLOWFUSION_MAX_HYDRATION_ATTEMPTS"
} > "$RUN_DIR/meta.env"

set +e
python3 -m flowfusion > "$RUN_LOG" 2>&1
RC=$?
set -e

python3 "$PROJECT_ROOT/scripts/summarize_case_timing.py" --run-dir "$RUN_DIR"

exit "$RC"
