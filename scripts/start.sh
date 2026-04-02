#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

HOST="${WSOCR_WS_HOST:-0.0.0.0}"
PORT="${WSOCR_WS_PORT:-8765}"
OCR_BACKEND="${WSOCR_OCR_BACKEND:-paddleocr}"
PADDLE_DEVICE="${WSOCR_PADDLE_DEVICE:-auto}"
LOG_LEVEL="${WSOCR_LOG_LEVEL:-INFO}"

ensure_runtime_dirs
ensure_python_installed
ensure_pm2_installed

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
export WSOCR_OCR_BACKEND="$OCR_BACKEND"
export WSOCR_PADDLE_DEVICE="$PADDLE_DEVICE"
export WSOCR_WS_HOST="$HOST"
export WSOCR_WS_PORT="$PORT"
export WSOCR_LOG_LEVEL="$LOG_LEVEL"

if ! pm2_cmd describe pm2-logrotate >/dev/null 2>&1; then
    echo "pm2-logrotate is not installed for PM2_HOME=$PM2_HOME" >&2
    echo "run ./scripts/install.sh first" >&2
    exit 1
fi

pm2_cmd startOrRestart "$ROOT_DIR/ecosystem.config.js" --only "$APP_NAME" --update-env >/dev/null

PID="$(pm2_cmd pid "$APP_NAME" | tr -d '[:space:]')"
if [[ -z "$PID" || "$PID" == "0" ]]; then
    echo "failed to start $APP_NAME, inspect logs with ./scripts/logs.sh" >&2
    exit 1
fi

echo "started $APP_NAME pid=$PID ws://$HOST:$PORT backend=$OCR_BACKEND"
echo "paddle device mode: $PADDLE_DEVICE"
echo "pm2 home: $PM2_HOME"
echo "log directory: $LOG_DIR"
