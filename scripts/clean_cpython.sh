#!/usr/bin/env bash
set -euo pipefail

CPYTHON_SRC="${1:-../cpython-src}"

if [[ ! -d "$CPYTHON_SRC/.git" ]]; then
  echo "[clean] not a git repo: $CPYTHON_SRC" >&2
  exit 1
fi

cd "$CPYTHON_SRC"
git reset --hard HEAD
git clean -fdx
git status --short
