#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/run/wechat_stream_ocr.log"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

tail -f "$LOG_FILE"
