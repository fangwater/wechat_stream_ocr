#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/run"
PID_FILE="$RUN_DIR/wechat_stream_ocr.pid"
LOG_FILE="$RUN_DIR/wechat_stream_ocr.log"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
HOST="${WSOCR_WS_HOST:-0.0.0.0}"
PORT="${WSOCR_WS_PORT:-8765}"
OCR_BACKEND="${WSOCR_OCR_BACKEND:-paddleocr}"
PADDLE_DEVICE="${WSOCR_PADDLE_DEVICE:-auto}"
LOG_LEVEL="${WSOCR_LOG_LEVEL:-INFO}"

mkdir -p "$RUN_DIR"
touch "$LOG_FILE"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "python virtualenv not found at $PYTHON_BIN" >&2
    echo "run ./scripts/install.sh first" >&2
    exit 1
fi

if [[ -f "$PID_FILE" ]]; then
    EXISTING_PID="$(cat "$PID_FILE")"
    if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "wechat_stream_ocr is already running with pid=$EXISTING_PID"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
export WSOCR_OCR_BACKEND="$OCR_BACKEND"
export WSOCR_PADDLE_DEVICE="$PADDLE_DEVICE"
export WSOCR_WS_HOST="$HOST"
export WSOCR_WS_PORT="$PORT"
export WSOCR_LOG_LEVEL="$LOG_LEVEL"

LOG_START_SIZE="$(wc -c <"$LOG_FILE")"

nohup "$PYTHON_BIN" -u -m wechat_stream_ocr.main \
    --ws-host "$HOST" \
    --ws-port "$PORT" \
    --ocr-backend "$OCR_BACKEND" \
    --log-level "$LOG_LEVEL" \
    >>"$LOG_FILE" 2>&1 < /dev/null &

PID="$!"
echo "$PID" >"$PID_FILE"

READY=0
for _ in $(seq 1 30); do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "failed to start wechat_stream_ocr, see $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    if tail -c +"$((LOG_START_SIZE + 1))" "$LOG_FILE" 2>/dev/null | grep -q "WebSocket server listening on ws://"; then
        READY=1
        break
    fi
    sleep 1
done

if [[ "$READY" -ne 1 ]]; then
    echo "wechat_stream_ocr is still starting, check $LOG_FILE"
    exit 0
fi

echo "started wechat_stream_ocr pid=$PID ws://$HOST:$PORT backend=$OCR_BACKEND"
echo "paddle device mode: $PADDLE_DEVICE"
echo "log file: $LOG_FILE"
