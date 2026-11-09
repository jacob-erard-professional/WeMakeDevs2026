#!/usr/bin/env bash
# Run the local FastAPI API used by the Expo app (default: http://localhost:8000).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$REPO_ROOT/.env"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env. Copy .env.example to .env and set ES_URL and ES_API_KEY." >&2
  exit 1
fi

cd "$REPO_ROOT/backend"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --env-file "$ENV_FILE"
