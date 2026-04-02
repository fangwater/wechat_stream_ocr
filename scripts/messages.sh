#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZMQ_CONNECT="${WSOCR_ZMQ_CONNECT:-tcp://127.0.0.1:5556}"
ZMQ_TOPIC="${WSOCR_ZMQ_TOPIC:-wechat.chat}"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "python virtualenv not found at $PYTHON_BIN" >&2
    echo "run ./scripts/install.sh first" >&2
    exit 1
fi

exec "$PYTHON_BIN" -c '
import os
import sys

import zmq

connect = os.environ.get("WSOCR_ZMQ_CONNECT", "'"$ZMQ_CONNECT"'")
topic = os.environ.get("WSOCR_ZMQ_TOPIC", "'"$ZMQ_TOPIC"'")

ctx = zmq.Context.instance()
sock = ctx.socket(zmq.SUB)
sock.connect(connect)
sock.setsockopt_string(zmq.SUBSCRIBE, topic)

print(f"[messages] subscribed to {connect} topic={topic}", flush=True)
while True:
    parts = sock.recv_multipart()
    if len(parts) == 1:
        payload = parts[0].decode("utf-8", errors="replace")
    else:
        payload = parts[-1].decode("utf-8", errors="replace")
    print(payload, flush=True)
'
