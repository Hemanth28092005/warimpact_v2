#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT"

if [[ ! -f requirements.lock ]]; then
  echo "requirements.lock not found. Run this script from the repository checkout." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required.")
PY

"$PYTHON_BIN" -m venv .venv
./.venv/bin/python -m ensurepip --upgrade
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.lock
./.venv/bin/python -m pip install -e .

echo "Virtual environment ready: .venv"
echo "Activate with: source .venv/bin/activate"
