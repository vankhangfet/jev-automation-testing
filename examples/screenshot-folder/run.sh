#!/usr/bin/env bash
# Screenshot-folder example runner (bash): load this folder's .env (or
# repo-root .env), then check the demo login screenshots.
# Results land in examples/screenshot-folder/reports/check-*/.
#
# Usage:  ./examples/screenshot-folder/run.sh   (extra CLI flags pass through)
set -euo pipefail

cd "$(dirname "$0")/../.."   # repo root

ENV_FILE="examples/screenshot-folder/.env"
[ -f "$ENV_FILE" ] || ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    # Strip UTF-8 BOM (first line) and CRLF endings before sourcing, so files
    # saved by Windows editors load the same as on Linux/macOS.
    CLEAN_ENV=$(mktemp)
    sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' "$ENV_FILE" > "$CLEAN_ENV"
    set -a
    # shellcheck disable=SC1090
    . "$CLEAN_ENV"
    set +a
    rm -f "$CLEAN_ENV"
    echo "Loaded env from $ENV_FILE"
else
    echo "No .env found (looked in examples/screenshot-folder/ and repo root) - using current shell env."
fi

uv run python -m jev_ui_agent check-screenshots \
    --dir examples/screenshot-folder/screens/login \
    --rules examples/screenshot-folder/rules/login.yaml \
    --out examples/screenshot-folder/reports "$@"
