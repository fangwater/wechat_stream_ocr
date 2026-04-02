#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ensure_runtime_dirs
ensure_pm2_installed

PM2_HOME="$PM2_HOME" exec npx --no-install pm2 logs "$APP_NAME" "$@"
