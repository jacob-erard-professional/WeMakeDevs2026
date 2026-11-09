#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
port="${PORT:-8000}"
pid_file="$repo_dir/.backend-$port.pid"

if [[ ! -f "$pid_file" ]]; then
  echo "No backend PID file found at $pid_file"
  exit 0
fi

pid="$(<"$pid_file")"
if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$pid_file"
  echo "Backend is not running; removed stale PID file"
  exit 0
fi

cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
if [[ "$cmdline" != *"uvicorn app.main:app"* ]]; then
  echo "PID $pid is not the expected backend process; leaving it running"
  exit 1
fi

kill "$pid"
for _ in {1..50}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "Backend stopped"
    exit 0
  fi
  sleep 0.1
done

echo "Backend did not stop within 5 seconds; send SIGTERM again or stop it manually"
exit 1
