#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
COV_RECORD_ROOT="$PROJECT_ROOT/workspace/cov_record"
BUILD_ROOT="$PROJECT_ROOT/workspace/python-cov"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
if [[ -e "$COV_RECORD_ROOT/$RUN_ID" ]]; then
  RUN_ID="${RUN_ID}_$$"
fi
RUN_DIR="$COV_RECORD_ROOT/$RUN_ID"
RUN_LOG="$RUN_DIR/run_24h.log"
CSV_PATH="$RUN_DIR/coverage_24h.csv"
SNAPSHOT_DIR="$RUN_DIR/gcovr_snapshots"
OVERRIDE_CONFIG="$RUN_DIR/config.py"

mkdir -p "$RUN_DIR"
mkdir -p "$SNAPSHOT_DIR"
find "$BUILD_ROOT" -name '*.gcda' -delete
find "$SNAPSHOT_DIR" -maxdepth 1 -type f -name 'gcovr-*.xml' -delete
rm -f "$RUN_LOG" "$CSV_PATH" "$OVERRIDE_CONFIG"

python3 - "$OVERRIDE_CONFIG" "$CSV_PATH" "$SNAPSHOT_DIR" <<'PY'
from pathlib import Path
import sys

override_path = Path(sys.argv[1])
csv_path = Path(sys.argv[2])
snapshot_dir = Path(sys.argv[3])
override_path.write_text(
    f"""CONFIG = {{
    'coverage': {{
        'csv_path': {str(csv_path)!r},
        'snapshot_dir': {str(snapshot_dir)!r},
    }},
}}
""",
    encoding='utf-8',
)
PY

export FLOWFUSION_CONFIG="$OVERRIDE_CONFIG"

if ! command -v gcovr >/dev/null 2>&1; then
  echo "[run_cov_24h] gcovr command not found in PATH" | tee "$RUN_LOG"
  exit 1
fi

PYTHONUNBUFFERED=1 timeout --signal=INT --kill-after=30s 24h \
  python3 -m flowfusion > "$RUN_LOG" 2>&1 &
RUN_PID=$!

wait "$RUN_PID" || true
python3 scripts/rebuild_coverage_csv.py \
  --cov-record-dir "$SNAPSHOT_DIR" \
  --output "$CSV_PATH"
