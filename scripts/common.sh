#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/run"
LOG_DIR="$RUN_DIR/logs"
PM2_HOME="$RUN_DIR/.pm2"
APP_NAME="wechat-stream-ocr"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

ensure_runtime_dirs() {
    mkdir -p "$RUN_DIR" "$LOG_DIR" "$PM2_HOME"
}

ensure_python_installed() {
    if [[ -x "$PYTHON_BIN" ]]; then
        return 0
    fi

    echo "python virtualenv not found at $PYTHON_BIN" >&2
    echo "run ./scripts/install.sh first" >&2
    exit 1
}

ensure_pm2_installed() {
    if command -v npm >/dev/null 2>&1 && [[ -x "$ROOT_DIR/node_modules/.bin/pm2" ]]; then
        return 0
    fi

    echo "local pm2 not found under $ROOT_DIR/node_modules" >&2
    echo "run ./scripts/install.sh first" >&2
    exit 1
}

pm2_cmd() {
    PM2_HOME="$PM2_HOME" npx --no-install pm2 "$@"
}
