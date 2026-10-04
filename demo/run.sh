#!/usr/bin/env bash
# Demo runner (bash): load demo/.env (or repo-root .env), then check the
# demo login screenshots. Results land in demo/reports/check-*/.
#
# Usage:  ./demo/run.sh              (extra CLI flags pass through)
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="demo/.env"
[ -f "$ENV_FILE" ] || ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    echo "Loaded env from $ENV_FILE"
else
    echo "No .env found (looked in demo/ and repo root) - using current shell env."
fi

uv run python -m jev_ui_agent check-screenshots \
    --dir demo/screens/login \
    --rules demo/rules/login.yaml \
    --out demo/reports "$@"
