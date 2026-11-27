#!/usr/bin/env bash
set -Eeuo pipefail

# Always run from the project directory, even when launched from another folder.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python 3 was not found."
    echo "Install Python 3.10 or newer, then try again."
    exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python 3.10 or newer is required."
    "$PYTHON_BIN" --version
    exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Creating project virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"

    echo "Installing Power Socket dependencies..."
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r requirements.txt
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Could not create the project virtual environment at $VENV_DIR."
    exit 1
fi

echo "Starting Power Socket..."
exec "$VENV_PYTHON" -m power_socket "$@"
