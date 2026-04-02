#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/run"
PID_FILE="$RUN_DIR/wechat_stream_ocr.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "wechat_stream_ocr is not running"
    exit 0
fi

PID="$(cat "$PID_FILE")"
if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "stopped wechat_stream_ocr pid=$PID"
else
    echo "stale pid file removed"
fi

rm -f "$PID_FILE"
