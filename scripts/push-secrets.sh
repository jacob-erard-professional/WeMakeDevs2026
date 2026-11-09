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

tmp="$(mktemp)"
chmod 600 "$tmp"
trap 'rm -f "$tmp"' EXIT

key_count=0
for key in "${keys[@]}"; do
  if [[ -n "${!key:-}" ]]; then
    printf '%s=%s\n' "$key" "${!key}" >> "$tmp"
    ((key_count += 1))
  fi
done

kubectl -n "$namespace" create secret generic app-env --from-env-file="$tmp" --dry-run=client -o yaml \
  | kubectl apply -f - >/dev/null
echo "Secret app-env updated in $namespace with $key_count keys."
