#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAMLIT_BIN="$ROOT_DIR/.venv/bin/streamlit"

if [ ! -x "$STREAMLIT_BIN" ]; then
  echo "Virtual environment atau Streamlit belum tersedia. Jalankan: bash scripts/setup.sh"
  exit 1
fi

cd "$ROOT_DIR"
exec "$STREAMLIT_BIN" run src/app.py "$@"
