#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT/benchmarks/libfuzzer_test"
mkdir -p python_cov
cd python_cov

CC="gcc" \
CXX="g++" \
CFLAGS="-O0 -g --coverage -fprofile-arcs -ftest-coverage" \
CXXFLAGS="-O0 -g --coverage -fprofile-arcs -ftest-coverage" \
LDFLAGS="--coverage" \
"$PROJECT_ROOT/../cpython-src/configure" \
  --with-pydebug \
  --without-ensurepip \
  --disable-shared

make -j8
