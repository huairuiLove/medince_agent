#!/usr/bin/env bash
# Start MedSafe full stack: API (background) + Vue dev server (foreground)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ ! -d .venv ]; then
  echo "未找到 .venv，请先运行: bash scripts/setup.sh"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node.js 18+ required for frontend. Install from https://nodejs.org/"
  exit 1
fi

source .venv/bin/activate

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

API_HOST="${MEDSAFE_SERVER__HOST:-0.0.0.0}"
API_PORT="${MEDSAFE_SERVER__PORT:-8000}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"

cleanup() {
  if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" 2>/dev/null; then
    echo ""
    echo "Stopping API (pid ${API_PID})..."
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "============================================"
echo " MedSafe — starting API + frontend"
echo "============================================"
echo " API:       http://localhost:${API_PORT}"
echo " Frontend:  http://localhost:5173"
echo " Press Ctrl+C to stop both services"
echo "============================================"

python -m uvicorn src.app:app \
  --host "$API_HOST" \
  --port "$API_PORT" \
  --reload &
API_PID=$!

ready=0
for _ in $(seq 1 120); do
  if curl -sf "$HEALTH_URL" >/dev/null 2>&1 \
    && curl -sf "http://127.0.0.1:${API_PORT}/api/v1/auth/departments" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "ERROR: API process exited before /health became ready."
    exit 1
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "ERROR: API not ready after 120s. Check logs above."
  exit 1
fi

echo "API ready (${HEALTH_URL})"

cd frontend
npm install
exec npm run dev
