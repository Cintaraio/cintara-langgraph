#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
PACKAGE_SPEC='cintara-langgraph[langgraph] @ git+https://github.com/Cintaraio/cintara-langgraph.git'

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required. Install Python 3.11+ and re-run this command." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11+ is required. Re-run with PYTHON=/path/to/python3.11 if needed." >&2
  exit 1
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
  fi
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

python -m pip install "$PACKAGE_SPEC"

echo
echo "Initializing Cintara LangGraph onboarding files..."

if [ -t 0 ]; then
  python -m cintara_langgraph init "$@"
elif [ -r /dev/tty ] && { true < /dev/tty; } 2>/dev/null; then
  python -m cintara_langgraph init "$@" < /dev/tty
else
  python -m cintara_langgraph init "$@"
fi
