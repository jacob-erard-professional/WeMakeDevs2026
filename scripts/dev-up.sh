#!/usr/bin/env bash
# Bring up the local hackathon stack:
#   1. kind cluster "wemakedevs2026" (Radar + Elasticsearch tracks)
#   2. `elasticsearch` Secret (ES_URL + ES_API_KEY from .env) so pods can reach the
#      shared Elastic Cloud Serverless project; Kibana lives in that cloud project
#   3. Radar UI + MCP at http://localhost:9280 (MCP: /mcp)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER=wemakedevs2026
ENV_FILE="$REPO_ROOT/.env"

for bin in docker kind kubectl kubectl-radar curl; do
  command -v "$bin" >/dev/null || { echo "Missing $bin. See SETUP.md." >&2; exit 1; }
done

if kind get clusters | grep -qx "$CLUSTER"; then
  echo "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$REPO_ROOT/k8s/kind-config.yaml" --wait 120s
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

# Read one KEY=value line from .env without sourcing it (values may contain spaces).
# Strips surrounding single/double quotes. Never echoes the value.
env_value() {
  [ -f "$ENV_FILE" ] || return 0
  { grep -m1 -E "^[[:space:]]*$1=" "$ENV_FILE" || true; } \
    | sed -E "s/^[[:space:]]*$1=//; s/^[[:space:]]+//; s/[[:space:]]+\$//; s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/"
}

ES_URL="$(env_value ES_URL)"
ES_API_KEY="$(env_value ES_API_KEY)"

if [ -n "$ES_URL" ] && [ -n "$ES_API_KEY" ]; then
  kubectl create secret generic elasticsearch \
    --from-literal=ES_URL="$ES_URL" \
    --from-literal=ES_API_KEY="$ES_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
  code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' \
    -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/" || true)"
  echo "Elasticsearch: HTTP ${code:-000} from ES_URL (200 = key works, 401 = check ES_API_KEY in .env)"
  echo "Pods: envFrom the 'elasticsearch' Secret for ES_URL and ES_API_KEY"
else
  echo "ES_URL and/or ES_API_KEY not set in .env; skipping the elasticsearch Secret. See SETUP.md." >&2
fi

if curl -fs -o /dev/null http://localhost:9280/; then
  echo "Radar already running at http://localhost:9280"
else
  nohup kubectl-radar -no-browser >"$REPO_ROOT/.radar.log" 2>&1 &
  echo "Radar starting at http://localhost:9280 (log: .radar.log)"
fi
