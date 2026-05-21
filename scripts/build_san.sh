#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$PROJECT_ROOT/workspace/python-san"
cd "$PROJECT_ROOT/workspace/python-san"

export LSAN_OPTIONS="detect_leaks=0"

CC="clang" \
CXX="clang++" \
CFLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -O0" \
CXXFLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -O0" \
LDFLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer" \
"$PROJECT_ROOT/../cpython/cpython-src/configure" \
  --with-pydebug \
  --without-pymalloc \
  --without-ensurepip

make -j8
