#!/usr/bin/env bash
# Launch the Athena Shield server (serves UI + API).
set -euo pipefail
cd "$(dirname "$0")"
PY="../.venv/bin/python"
[ -x "$PY" ] || PY="python3"
exec "$PY" server.py
