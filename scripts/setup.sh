#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "============================================"
echo " MedSafe Setup (v2 — Multi-Agent LLM API)"
echo "============================================"

python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" || {
  echo "ERROR: Python 3.10+ required"; exit 1;
}

VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt -q

ENV_FILE="${PROJECT_ROOT}/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
  echo "Created .env from .env.example"
fi

mkdir -p data/cases data/processed data/case_templates logs

python -m compileall src -q
python scripts/run_integration_tests.py

echo ""
echo "Setup complete. Start server:"
echo "  source .venv/bin/activate && medsafe serve"
echo "  or: docker compose up -d"
