#!/usr/bin/env bash
# Create or update Secret app-env in team-wearedevs from selected .env values.
# Run it yourself with the team kubeconfig (README of skyhook-io/cnh-starter, "kubectl"):
#   KUBECONFIG=~/cnh-kubeconfig ./scripts/push-secrets.sh
# Values never touch git or stdout. Restart the app afterwards so pods read the new values.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$repo_dir/.env"
namespace="team-wearedevs"
keys=(
  ES_URL ES_API_KEY OPENAI_API_KEY OPENAI_MODEL ORGANIZER_API_KEY PUBLIC_BASE_URL
  OTEL_RESOURCE_ATTRIBUTES OTEL_EXPORTER_OTLP_ENDPOINT OTEL_EXPORTER_OTLP_HEADERS
  OTEL_EXPORTER_OTLP_PROTOCOL OTEL_TRACES_EXPORTER OTEL_METRICS_EXPORTER OTEL_LOGS_EXPORTER
)

[[ -f "$env_file" ]] || { echo "No .env at $env_file" >&2; exit 1; }
[[ -n "${KUBECONFIG:-}" ]] || { echo "Set KUBECONFIG to the team kubeconfig first." >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

args=()
for key in "${keys[@]}"; do
  if [[ -n "${!key:-}" ]]; then
    args+=("--from-literal=${key}=${!key}")
  fi
done

kubectl -n "$namespace" create secret generic app-env "${args[@]}" --dry-run=client -o yaml \
  | kubectl apply -f - >/dev/null
echo "Secret app-env updated in $namespace with ${#args[@]} keys."
