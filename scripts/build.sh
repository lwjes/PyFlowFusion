#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$PROJECT_ROOT/workspace/python-cov"
cd "$PROJECT_ROOT/workspace/python-cov"

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
