#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
INSTALL_MODE="${1:-auto}"
PM2_HOME="$ROOT_DIR/run/.pm2"

cd "$ROOT_DIR"

create_virtualenv() {
    if "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        return 0
    fi

    echo "python3 -m venv failed, trying user-scoped virtualenv bootstrap" >&2
    "$PYTHON_BIN" -m pip install --user virtualenv
    "$PYTHON_BIN" -m virtualenv "$VENV_DIR"
}

if [[ ! -x "$VENV_PYTHON" ]]; then
    create_virtualenv
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -e .

detect_paddle_package() {
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        echo "paddlepaddle"
        return 0
    fi

    local cuda_version
    cuda_version="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9.]\+\).*/\1/p' | head -n 1)"
    case "$cuda_version" in
        11.8*)
            echo "paddlepaddle-gpu"
            return 0
            ;;
        12.6*|12.7*|12.8*)
            echo "paddlepaddle-gpu"
            return 0
            ;;
        12.9*|13.0*)
            echo "paddlepaddle-gpu"
            return 0
            ;;
        "")
            echo "paddlepaddle"
            return 0
            ;;
        *)
            echo "paddlepaddle"
            return 0
            ;;
    esac
}

PADDLE_PACKAGE="paddlepaddle"
case "$INSTALL_MODE" in
    cpu)
        PADDLE_PACKAGE="paddlepaddle"
        ;;
    gpu)
        if ! command -v nvidia-smi >/dev/null 2>&1; then
            echo "GPU install requested, but nvidia-smi is unavailable" >&2
            exit 1
        fi
        DETECTED_PACKAGE="$(detect_paddle_package)"
        if [[ "$DETECTED_PACKAGE" == "paddlepaddle" ]]; then
            CUDA_VERSION="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9.]\+\).*/\1/p' | head -n 1)"
            echo "GPU install requested, but CUDA version '$CUDA_VERSION' is not mapped by scripts/install.sh" >&2
            echo "Install the matching paddlepaddle-gpu wheel manually based on the official matrix" >&2
            exit 1
        fi
        PADDLE_PACKAGE="$DETECTED_PACKAGE"
        ;;
    auto)
        PADDLE_PACKAGE="$(detect_paddle_package)"
        ;;
    *)
        echo "usage: $0 [auto|cpu|gpu]" >&2
        exit 1
        ;;
esac

echo "Installing OCR runtime package: $PADDLE_PACKAGE"
"$VENV_PYTHON" -m pip install "$PADDLE_PACKAGE" paddleocr "paddlex[ocr]"

if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to install local pm2 tooling" >&2
    exit 1
fi

mkdir -p "$ROOT_DIR/run/logs" "$PM2_HOME"

npm install

PM2_HOME="$PM2_HOME" npx --no-install pm2 describe pm2-logrotate >/dev/null 2>&1 || \
    PM2_HOME="$PM2_HOME" npx --no-install pm2 install pm2-logrotate

PM2_HOME="$PM2_HOME" npx --no-install pm2 set pm2-logrotate:retain 1
PM2_HOME="$PM2_HOME" npx --no-install pm2 set pm2-logrotate:compress true
PM2_HOME="$PM2_HOME" npx --no-install pm2 set pm2-logrotate:max_size 10M
PM2_HOME="$PM2_HOME" npx --no-install pm2 set pm2-logrotate:workerInterval 30
PM2_HOME="$PM2_HOME" npx --no-install pm2 set pm2-logrotate:rotateInterval '0 0 * * *'
