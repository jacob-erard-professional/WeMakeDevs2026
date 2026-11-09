#!/usr/bin/env bash
# Bring up the local hackathon stack:
#   1. kind cluster "wemakedevs2026" (Radar + Elasticsearch tracks)
#   2. Elasticsearch + Kibana from start-local, reachable from pods as http://elasticsearch:9200
#   3. Radar UI + MCP at http://localhost:9280 (MCP: /mcp)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER=wemakedevs2026
ES_DIR="${ES_DIR:-$REPO_ROOT/../elastic-start-local}"
ES_CONTAINER=es-local-dev

for bin in docker kind kubectl kubectl-radar envsubst curl; do
  command -v "$bin" >/dev/null || { echo "Missing $bin. See SETUP.md." >&2; exit 1; }
done

if kind get clusters | grep -qx "$CLUSTER"; then
  echo "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$REPO_ROOT/k8s/kind-config.yaml" --wait 120s
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

if [ -x "$ES_DIR/start.sh" ]; then
  (cd "$ES_DIR" && ./start.sh)
  # Join the ES container to kind's Docker network and point an in-cluster Service at it.
  docker network connect kind "$ES_CONTAINER" 2>/dev/null || true
  ES_IP="$(docker inspect -f '{{(index .NetworkSettings.Networks "kind").IPAddress}}' "$ES_CONTAINER")"
  ES_IP="$ES_IP" envsubst < "$REPO_ROOT/k8s/elasticsearch-bridge.yaml.tpl" | kubectl apply -f -
  echo "Elasticsearch: http://localhost:9200 from this machine, http://elasticsearch:9200 from pods"
  echo "Kibana:        http://localhost:5601 (credentials in $ES_DIR/.env)"
else
  echo "Elasticsearch not installed at $ES_DIR; skipping. See SETUP.md." >&2
fi

if curl -fs -o /dev/null http://localhost:9280/; then
  echo "Radar already running at http://localhost:9280"
else
  nohup kubectl-radar -no-browser >"$REPO_ROOT/.radar.log" 2>&1 &
  echo "Radar starting at http://localhost:9280 (log: .radar.log)"
fi
