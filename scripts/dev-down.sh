#!/usr/bin/env bash
# Stop the local stack. Pass --delete to also delete the kind cluster.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ES_DIR="${ES_DIR:-$REPO_ROOT/../elastic-start-local}"

pkill -f kubectl-radar && echo "Radar stopped" || true
[ -x "$ES_DIR/stop.sh" ] && (cd "$ES_DIR" && ./stop.sh)

if [ "${1:-}" = "--delete" ]; then
  kind delete cluster --name wemakedevs2026
fi
