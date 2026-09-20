#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -n "${VIRTUAL_ENV:-}${CONDA_PREFIX:-}" ]; then
    PYTHON_BIN="$(command -v python || command -v python3)"
else
    if [ -x ".venv/bin/python" ]; then
        PYTHON_BIN=".venv/bin/python"
    else
        # Let run.py forward its Kokoro options when it bootstraps setup.
        PYTHON_BIN="$(command -v python3 || command -v python)"
    fi
fi

exec "$PYTHON_BIN" run.py "$@"
