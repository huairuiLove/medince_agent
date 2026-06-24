#!/usr/bin/env bash
# Start MedSafe remote segment worker (AutoDL / cloud GPU).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export MEDSAFE_IMAGING__DEVICE="${MEDSAFE_IMAGING__DEVICE:-cuda}"
export MEDSAFE_IMAGING__REMOTE__WORKER__HOST="${MEDSAFE_IMAGING__REMOTE__WORKER__HOST:-127.0.0.1}"
export MEDSAFE_IMAGING__REMOTE__WORKER__PORT="${MEDSAFE_IMAGING__REMOTE__WORKER__PORT:-9000}"

echo "Segment worker on ${MEDSAFE_IMAGING__REMOTE__WORKER__HOST}:${MEDSAFE_IMAGING__REMOTE__WORKER__PORT} (device=${MEDSAFE_IMAGING__DEVICE})"
echo "Local tunnel example:"
echo "  ssh -p <port> -L 9000:127.0.0.1:9000 root@connect.xxx.seetacloud.com"

exec python -m src.cli segment-worker \
  --host "${MEDSAFE_IMAGING__REMOTE__WORKER__HOST}" \
  --port "${MEDSAFE_IMAGING__REMOTE__WORKER__PORT}"
