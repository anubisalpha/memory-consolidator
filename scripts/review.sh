#!/usr/bin/env bash
# Interactive review session for one area.
# Usage: scripts/review.sh <area-name>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=""
for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "No working Python interpreter found (tried python3, python, py)." >&2
    exit 1
fi

if [ "${1:-}" = "" ]; then
    echo "Usage: scripts/review.sh <area-name>" >&2
    exit 1
fi

exec "$PY" main.py review --area "$1"
