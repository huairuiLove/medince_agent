#!/usr/bin/env bash
# Start MedSafe API server
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

exec python -m uvicorn src.app:app \
  --host "${MEDSAFE_SERVER__HOST:-0.0.0.0}" \
  --port "${MEDSAFE_SERVER__PORT:-8000}" \
  --reload
