#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CPYTHON_SRC="$PROJECT_ROOT/../cpython-src"
PY_LIBFUZZ_COV="$PROJECT_ROOT/benchmarks/libfuzzer_cov/python-cov"
PY_COV_PY="$PROJECT_ROOT/benchmarks/libfuzzer_cov/python-cov/python"
PYTHONHOME_FOR_FUZZ="$CPYTHON_SRC"
PYTHONPATH_FOR_FUZZ="$CPYTHON_SRC/Lib"

RUN_ROOT="$PROJECT_ROOT/benchmarks/libfuzzer_cov"
BIN_DIR="$RUN_ROOT/bin"
FUZZ_BIN="$BIN_DIR/fuzz_pycompile"

CORPUS_SEED_ROOT="$RUN_ROOT/corpus_seed_from_libtest"
CORPUS_DIR="$RUN_ROOT/corpus"
ARTIFACT_DIR="$RUN_ROOT/artifacts"
LOG_DIR="$RUN_ROOT/logs"
META_DIR="$RUN_ROOT/meta"

BUILD_LOG="$META_DIR/build_fuzz_pycompile.log"
PREP_LOG="$META_DIR/prepare_corpus.log"
STATS_CSV="$RUN_ROOT/stats.csv"
SUMMARY_TXT="$RUN_ROOT/summary.txt"
STATUS_TXT="$RUN_ROOT/status.txt"

rm -rf "$CORPUS_SEED_ROOT" "$CORPUS_DIR" "$ARTIFACT_DIR" "$LOG_DIR" "$META_DIR"
rm -f "$STATS_CSV" "$SUMMARY_TXT" "$STATUS_TXT"
mkdir -p "$RUN_ROOT" "$BIN_DIR" "$CORPUS_SEED_ROOT" "$CORPUS_DIR" "$ARTIFACT_DIR" "$LOG_DIR" "$META_DIR"

echo "running" > "$STATUS_TXT"
echo "run_root=$RUN_ROOT" >> "$STATUS_TXT"
echo "started_at=$(date --iso-8601=seconds)" >> "$STATUS_TXT"

build_fuzz_pycompile() {
  echo "[build] building fuzz_pycompile at $FUZZ_BIN" | tee -a "$BUILD_LOG"
  rm -f "$FUZZ_BIN"
  clang \
    -O1 \
    -g \
    -fno-omit-frame-pointer \
    -fsanitize=fuzzer \
    -D_Py_FUZZ_ONE \
    -D_Py_FUZZ_fuzz_pycompile \
    -I"$PY_LIBFUZZ_COV" \
    -I"$CPYTHON_SRC/Include" \
    -I"$CPYTHON_SRC/Include/internal" \
    -I"$CPYTHON_SRC" \
    "$CPYTHON_SRC/Modules/_xxtestfuzz/fuzzer.c" \
    "$PY_LIBFUZZ_COV/libpython3.15d.a" \
    -o "$FUZZ_BIN" \
    -ldl \
    -lm \
    -lpthread \
    -lutil 2>&1 | tee -a "$BUILD_LOG"
}

prepare_corpus() {
  echo "[prepare] generating initial corpus from Lib/test" | tee -a "$PREP_LOG"
  "$PY_COV_PY" \
    "$PROJECT_ROOT/benchmarks/libfuzzer_cov/prepare_pycompile_corpus.py" \
    --lib-test-root "$CPYTHON_SRC/Lib/test" \
    --out-dir "$CORPUS_SEED_ROOT" \
    --max-payload 16380 2>&1 | tee -a "$PREP_LOG"

  echo "[prepare] copying seeds into active corpus dir" | tee -a "$PREP_LOG"
  cp -a "$CORPUS_SEED_ROOT/seeds/." "$CORPUS_DIR/"
}

parse_round_metrics() {
  local round_log="$1"
  local cov ft exec_units

  cov="$(grep -E "DONE[[:space:]]+cov:" "$round_log" | tail -n 1 | sed -n 's/.*cov: \([0-9][0-9]*\).*/\1/p')"
  ft="$(grep -E "DONE[[:space:]]+cov:" "$round_log" | tail -n 1 | sed -n 's/.*ft: \([0-9][0-9]*\).*/\1/p')"
  exec_units="$(grep -E "stat::number_of_executed_units:" "$round_log" | tail -n 1 | awk '{print $2}')"

  cov="${cov:-NA}"
  ft="${ft:-NA}"
  exec_units="${exec_units:-NA}"

  echo "$cov,$ft,$exec_units"
}

run_rounds() {
  echo "round,started_at,ended_at,cov,ft,executed_units,round_log" > "$STATS_CSV"

  for round in $(seq 1 48); do
    local round_name
    local round_log
    local started_at
    local ended_at
    local metrics
    local cov
    local ft
    local exec_units

    round_name="$(printf "%02d" "$round")"
    round_log="$LOG_DIR/round_${round_name}.log"
    started_at="$(date --iso-8601=seconds)"

    echo "[round $round_name] start $started_at" | tee -a "$round_log"

    PYTHONHOME="$PYTHONHOME_FOR_FUZZ" \
    PYTHONPATH="$PYTHONPATH_FOR_FUZZ" \
    "$FUZZ_BIN" \
      "$CORPUS_DIR" \
      -dict="$CPYTHON_SRC/Modules/_xxtestfuzz/dictionaries/fuzz_pycompile.dict" \
      -artifact_prefix="$ARTIFACT_DIR/" \
      -max_total_time=1800 \
      -print_final_stats=1 >> "$round_log" 2>&1

    ended_at="$(date --iso-8601=seconds)"
    metrics="$(parse_round_metrics "$round_log")"
    cov="${metrics%%,*}"
    metrics="${metrics#*,}"
    ft="${metrics%%,*}"
    exec_units="${metrics##*,}"

    echo "$round,$started_at,$ended_at,$cov,$ft,$exec_units,$round_log" >> "$STATS_CSV"
    echo "[round $round_name] done cov=$cov ft=$ft executed_units=$exec_units" | tee -a "$round_log"
  done
}

finalize_summary() {
  local last_row
  local final_cov
  local final_ft
  local final_exec

  last_row="$(tail -n 1 "$STATS_CSV")"
  final_cov="$(echo "$last_row" | awk -F',' '{print $4}')"
  final_ft="$(echo "$last_row" | awk -F',' '{print $5}')"
  final_exec="$(echo "$last_row" | awk -F',' '{print $6}')"

  {
    echo "run_root=$RUN_ROOT"
    echo "finished_at=$(date --iso-8601=seconds)"
    echo "final_cov=$final_cov"
    echo "final_ft=$final_ft"
    echo "final_executed_units=$final_exec"
    echo "stats_csv=$STATS_CSV"
    echo "artifacts_dir=$ARTIFACT_DIR"
    echo "corpus_dir=$CORPUS_DIR"
    echo "logs_dir=$LOG_DIR"
  } > "$SUMMARY_TXT"

  echo "finished" > "$STATUS_TXT"
  echo "run_root=$RUN_ROOT" >> "$STATUS_TXT"
  echo "finished_at=$(date --iso-8601=seconds)" >> "$STATUS_TXT"
  echo "summary=$SUMMARY_TXT" >> "$STATUS_TXT"
}

build_fuzz_pycompile
prepare_corpus
run_rounds
finalize_summary

echo "[done] $SUMMARY_TXT"
