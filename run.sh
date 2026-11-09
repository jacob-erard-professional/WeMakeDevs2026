#!/usr/bin/env bash
# Start the local FastAPI API and Expo web client together.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_ROOT/.env"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8081}"
BACKEND_PID_FILE="$REPO_ROOT/.backend-$BACKEND_PORT.pid"
FRONTEND_PID_FILE="$REPO_ROOT/.frontend-$FRONTEND_PORT.pid"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env. Copy .env.example to .env and set ES_URL and ES_API_KEY." >&2
  exit 1
fi

for command in uv npm; do
  command -v "$command" >/dev/null || {
    echo "Missing $command. See SETUP.md." >&2
    exit 1
  }
done

for pid_file in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
  if [[ -f "$pid_file" ]]; then
    pid="$(<"$pid_file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      echo "A development service is already running (PID $pid in $pid_file). Run ./stop.sh first." >&2
      exit 1
    fi
    rm -f "$pid_file"
  fi
done

# These exports take precedence over .env for a coherent local stack, while callers can still
# override them (for example, FRONTEND_PORT=19006 ./run.sh).
export EXPO_PUBLIC_API_URL="${EXPO_PUBLIC_API_URL:-http://localhost:$BACKEND_PORT}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:$FRONTEND_PORT}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:$FRONTEND_PORT}"

if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$REPO_ROOT/frontend" && npm ci)
fi

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
  rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
  exit "$status"
}
trap cleanup EXIT INT TERM

(
  cd "$REPO_ROOT/backend"
  exec uv run uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --env-file "$ENV_FILE"
) &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" >"$BACKEND_PID_FILE"

(
  cd "$REPO_ROOT/frontend"
  exec npm run web -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!
printf '%s\n' "$FRONTEND_PID" >"$FRONTEND_PID_FILE"

echo "Backend:  http://localhost:$BACKEND_PORT/docs"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Press Ctrl-C to stop both services."

if wait -n "$BACKEND_PID" "$FRONTEND_PID"; then
  echo "A development service stopped."
else
  echo "A development service exited with an error." >&2
  exit 1
fi
