#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT/benchmarks/libfuzzer_cov"
mkdir -p python-cov
cd python-cov

CC="clang" \
CXX="clang++" \
CFLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=fuzzer-no-link" \
CXXFLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=fuzzer-no-link" \
LDFLAGS="-fsanitize=fuzzer-no-link" \
"$PROJECT_ROOT/../cpython/cpython-src/configure" \
  --with-pydebug \
  --without-ensurepip \
  --disable-shared

make -j8
