#!/usr/bin/env bash
# Stop the local stack. Pass --delete to also delete the kind cluster.
set -euo pipefail

pkill -f kubectl-radar && echo "Radar stopped" || true

if [ "${1:-}" = "--delete" ]; then
  kind delete cluster --name wemakedevs2026
fi
