#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Virtual environment belum siap."
  echo "Jalankan dulu: bash scripts/setup.sh"
  exit 1
fi

exec "$PYTHON_BIN" -m src.pipeline "$@"
