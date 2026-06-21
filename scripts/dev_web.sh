#!/usr/bin/env bash
# Run frontend dev server (proxies /api to localhost:8000)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
npm install
npm run dev
