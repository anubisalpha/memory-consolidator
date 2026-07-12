#!/usr/bin/env bash
# Interactively resolve diverged cross-area slug conflicts into a
# 'memory-diverged' area. Usage: scripts/resolve-conflicts.sh
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

exec "$PY" main.py resolve-conflicts
