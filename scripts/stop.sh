#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ensure_runtime_dirs
ensure_pm2_installed

if ! pm2_cmd describe "$APP_NAME" >/dev/null 2>&1; then
    echo "$APP_NAME is not running"
    exit 0
fi

pm2_cmd delete "$APP_NAME" >/dev/null
echo "stopped $APP_NAME"
