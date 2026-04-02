#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
INSTALL_MODE="${1:-auto}"
PM2_HOME="$ROOT_DIR/run/.pm2"
GET_PIP_URL="${GET_PIP_URL:-https://mirrors.aliyun.com/pypi/get-pip.py}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.aliyun.com}"
MINICONDA_DIR="${MINICONDA_DIR:-$HOME/.local/miniconda3}"
MINICONDA_MIRROR_BASE_URL="${MINICONDA_MIRROR_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda}"
PADDLE_PACKAGE_VERSION="${PADDLE_PACKAGE_VERSION:-3.3.0}"
PADDLE_STABLE_BASE_URL="${PADDLE_STABLE_BASE_URL:-https://www.paddlepaddle.org.cn/packages/stable}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11

cd "$ROOT_DIR"

PIP_INSTALL_ARGS=(
    -i "$PIP_INDEX_URL"
    --trusted-host "$PIP_TRUSTED_HOST"
)

python_meets_requirement() {
    local python_bin="$1"
    "$python_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

download_file() {
    local url="$1"
    local output="$2"

    if command -v curl >/dev/null 2>&1; then
        curl -fL "$url" -o "$output"
        return 0
    fi

    if command -v wget >/dev/null 2>&1; then
        wget -O "$output" "$url"
        return 0
    fi

    echo "neither curl nor wget is available for downloading $url" >&2
    exit 1
}

bootstrap_user_python() {
    local os_name arch_name installer_name installer_path installer_args=()

    if [[ -x "$MINICONDA_DIR/bin/python" ]] && python_meets_requirement "$MINICONDA_DIR/bin/python"; then
        PYTHON_BIN="$MINICONDA_DIR/bin/python"
        return 0
    fi

    case "$(uname -s)" in
        Linux)
            os_name="Linux"
            ;;
        Darwin)
            os_name="MacOSX"
            ;;
        *)
            echo "unsupported operating system for automatic Miniforge bootstrap: $(uname -s)" >&2
            exit 1
            ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64)
            arch_name="x86_64"
            ;;
        aarch64|arm64)
            arch_name="aarch64"
            if [[ "$os_name" == "MacOSX" ]]; then
                arch_name="arm64"
            fi
            ;;
        ppc64le)
            arch_name="ppc64le"
            ;;
        *)
            echo "unsupported architecture for automatic Miniforge bootstrap: $(uname -m)" >&2
            exit 1
            ;;
    esac

    installer_name="Miniconda3-latest-${os_name}-${arch_name}.sh"
    installer_path="$(mktemp)"

    echo "python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required, bootstrapping user-scoped Miniconda from mirror" >&2
    download_file "$MINICONDA_MIRROR_BASE_URL/$installer_name" "$installer_path"

    if [[ -d "$MINICONDA_DIR" ]]; then
        installer_args=(-u)
    fi

    bash "$installer_path" -b "${installer_args[@]}" -p "$MINICONDA_DIR"
    rm -f "$installer_path"

    PYTHON_BIN="$MINICONDA_DIR/bin/python"
    if ! python_meets_requirement "$PYTHON_BIN"; then
        echo "bootstrapped Miniconda python does not satisfy python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ requirement" >&2
        exit 1
    fi
}

ensure_supported_python() {
    if python_meets_requirement "$PYTHON_BIN"; then
        return 0
    fi

    bootstrap_user_python
}

bootstrap_host_pip() {
    if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
        return 0
    fi

    if "$PYTHON_BIN" -m ensurepip --upgrade --user >/dev/null 2>&1; then
        return 0
    fi

    local get_pip_script
    get_pip_script="$(mktemp)"

    download_file "$GET_PIP_URL" "$get_pip_script"

    "$PYTHON_BIN" "$get_pip_script" --user -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST"
    rm -f "$get_pip_script"
}

create_virtualenv() {
    if "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        return 0
    fi

    echo "python3 -m venv failed, trying user-scoped virtualenv bootstrap" >&2
    bootstrap_host_pip
    "$PYTHON_BIN" -m pip install --user virtualenv
    "$PYTHON_BIN" -m virtualenv "$VENV_DIR"
}

bootstrap_venv_pip() {
    if "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
        return 0
    fi

    if "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1; then
        return 0
    fi

    echo "venv exists but pip is unavailable, recreating it via user-scoped virtualenv" >&2
    rm -rf "$VENV_DIR"
    bootstrap_host_pip
    "$PYTHON_BIN" -m pip install --user virtualenv
    "$PYTHON_BIN" -m virtualenv "$VENV_DIR"
}

ensure_supported_python

if [[ -x "$VENV_PYTHON" ]] && ! python_meets_requirement "$VENV_PYTHON"; then
    echo "existing venv uses unsupported Python, recreating it with $PYTHON_BIN" >&2
    rm -rf "$VENV_DIR"
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    create_virtualenv
fi

bootstrap_venv_pip

"$VENV_PYTHON" -m pip install "${PIP_INSTALL_ARGS[@]}" --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install "${PIP_INSTALL_ARGS[@]}" -e .

detect_paddle_package() {
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        echo "paddlepaddle"
        return 0
    fi

    local cuda_version
    cuda_version="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9.]\+\).*/\1/p' | head -n 1)"
    case "$cuda_version" in
        11.8*)
            echo "paddlepaddle-gpu|$PADDLE_STABLE_BASE_URL/cu118/"
            return 0
            ;;
        12.0*|12.1*|12.2*|12.3*|12.4*|12.5*)
            echo "paddlepaddle-gpu|$PADDLE_STABLE_BASE_URL/cu118/"
            return 0
            ;;
        12.6*|12.7*|12.8*)
            echo "paddlepaddle-gpu|$PADDLE_STABLE_BASE_URL/cu126/"
            return 0
            ;;
        12.9*|13.0*)
            echo "paddlepaddle-gpu|$PADDLE_STABLE_BASE_URL/cu129/"
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
PADDLE_PACKAGE_INDEX_URL=""
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
        PADDLE_PACKAGE="${DETECTED_PACKAGE%%|*}"
        if [[ "$DETECTED_PACKAGE" == *"|"* ]]; then
            PADDLE_PACKAGE_INDEX_URL="${DETECTED_PACKAGE#*|}"
        fi
        ;;
    auto)
        DETECTED_PACKAGE="$(detect_paddle_package)"
        PADDLE_PACKAGE="${DETECTED_PACKAGE%%|*}"
        if [[ "$DETECTED_PACKAGE" == *"|"* ]]; then
            PADDLE_PACKAGE_INDEX_URL="${DETECTED_PACKAGE#*|}"
        fi
        ;;
    *)
        echo "usage: $0 [auto|cpu|gpu]" >&2
        exit 1
        ;;
esac

if [[ "$PADDLE_PACKAGE" == "paddlepaddle-gpu" ]]; then
    echo "Installing OCR runtime package: $PADDLE_PACKAGE==$PADDLE_PACKAGE_VERSION from $PADDLE_PACKAGE_INDEX_URL"
    "$VENV_PYTHON" -m pip install \
        --index-url "$PADDLE_PACKAGE_INDEX_URL" \
        "paddlepaddle-gpu==$PADDLE_PACKAGE_VERSION"
    "$VENV_PYTHON" -m pip install "${PIP_INSTALL_ARGS[@]}" paddleocr "paddlex[ocr]"
else
    echo "Installing OCR runtime package: $PADDLE_PACKAGE"
    "$VENV_PYTHON" -m pip install "${PIP_INSTALL_ARGS[@]}" "$PADDLE_PACKAGE" paddleocr "paddlex[ocr]"
fi

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
