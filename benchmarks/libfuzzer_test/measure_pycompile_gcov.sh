#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_ROOT="$PROJECT_ROOT/benchmarks/libfuzzer_test"
CPYTHON_SRC="$PROJECT_ROOT/../cpython-src"
GCOV_BUILD_ROOT="$TEST_ROOT/python_cov"
CORPUS_DIR="$PROJECT_ROOT/benchmarks/libfuzzer_cov/corpus"
BIN_DIR="$TEST_ROOT/bin"
RESULT_DIR="$TEST_ROOT/results"
REPLAY_BIN="$BIN_DIR/replay_fuzz_pycompile"
REPLAY_SRC="$TEST_ROOT/replay_fuzz_pycompile.c"
REPORT_XML="$RESULT_DIR/libfuzzer_pycompile_gcov.xml"
SUMMARY_TXT="$RESULT_DIR/libfuzzer_pycompile_gcov_summary.txt"

mkdir -p "$BIN_DIR" "$RESULT_DIR"
export REPORT_XML

if [ ! -x "$GCOV_BUILD_ROOT/python" ]; then
  echo "[measure] missing gcov build at $GCOV_BUILD_ROOT/python" >&2
  echo "[measure] build it first with $TEST_ROOT/build.sh" >&2
  exit 1
fi

if [ ! -d "$CORPUS_DIR" ]; then
  echo "[measure] missing corpus dir at $CORPUS_DIR" >&2
  exit 1
fi

echo "[measure] clearing old gcda files under $GCOV_BUILD_ROOT"
find "$GCOV_BUILD_ROOT" -name '*.gcda' -delete

echo "[measure] building replay binary at $REPLAY_BIN"
gcc \
  -O0 \
  -g \
  --coverage \
  -D_Py_FUZZ_ONE \
  -D_Py_FUZZ_fuzz_pycompile \
  -I"$GCOV_BUILD_ROOT" \
  -I"$CPYTHON_SRC/Include" \
  -I"$CPYTHON_SRC/Include/internal" \
  -I"$CPYTHON_SRC" \
  "$REPLAY_SRC" \
  "$CPYTHON_SRC/Modules/_xxtestfuzz/fuzzer.c" \
  "$GCOV_BUILD_ROOT/libpython3.15d.a" \
  -o "$REPLAY_BIN" \
  -ldl \
  -lm \
  -lpthread \
  -lutil

echo "[measure] replaying corpus from $CORPUS_DIR"
PYTHONHOME="$CPYTHON_SRC" \
PYTHONPATH="$CPYTHON_SRC/Lib" \
"$REPLAY_BIN" "$CORPUS_DIR"

echo "[measure] collecting gcovr xml report at $REPORT_XML"
gcovr \
  -r "$CPYTHON_SRC" \
  --object-directory "$GCOV_BUILD_ROOT" \
  -o "$REPORT_XML" \
  --xml \
  --gcov-ignore-parse-errors

python3 - <<'PY' > "$SUMMARY_TXT"
from pathlib import Path
import os
import re

xml_path = Path(os.environ["REPORT_XML"])
text = xml_path.read_text(errors="ignore")

def get_attr(name: str) -> str:
    match = re.search(rf'<coverage\b[^>]*{name}="([^"]+)"', text)
    if not match:
        raise SystemExit(f"missing {name} in {xml_path}")
    return match.group(1)

line_rate = float(get_attr("line-rate"))
lines_covered = get_attr("lines-covered")
lines_valid = get_attr("lines-valid")
branch_rate = float(get_attr("branch-rate"))
branches_covered = get_attr("branches-covered")
branches_valid = get_attr("branches-valid")

print(f"report_xml={xml_path}")
print(f"line_rate={line_rate:.16f}")
print(f"line_pct={line_rate * 100:.4f}")
print(f"lines_covered={lines_covered}")
print(f"lines_valid={lines_valid}")
print(f"branch_rate={branch_rate:.16f}")
print(f"branch_pct={branch_rate * 100:.4f}")
print(f"branches_covered={branches_covered}")
print(f"branches_valid={branches_valid}")
PY

echo "[measure] summary written to $SUMMARY_TXT"
cat "$SUMMARY_TXT"
