#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir/backend"
port="${PORT:-8000}"
pid_file="$repo_dir/.backend-$port.pid"

if [[ -f "$pid_file" ]] && kill -0 "$(<"$pid_file")" 2>/dev/null; then
  echo "Backend already running with PID $(<"$pid_file")"
  exit 1
fi

if ! python -c 'import fastapi, uvicorn, elasticsearch, qrcode' >/dev/null 2>&1; then
  "$repo_dir/download_requirements.sh"
fi

python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "$port" "$@" &
pid=$!
echo "$pid" > "$pid_file"
trap 'rm -f "$pid_file"' EXIT INT TERM
wait "$pid"
