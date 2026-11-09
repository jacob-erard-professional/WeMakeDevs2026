# Setup

Hackathon: Cloud Native Hackathon, Mon Nov 9, Salt Lake City (https://luma.com/cnh).
Track details and resources: https://wemakedevs.org/hackathons/cnh/resources

## Already done in this repo

| Thing | Where | Track |
|---|---|---|
| Review conventions, rules, auto-apply criteria | `.gitar/` | Sonar / Gitar |
| CI (ruff + pytest once `pyproject.toml` exists; manifest validation) | `.github/workflows/ci.yml` | Sonar / Gitar |
| Local kind cluster config (app NodePort 30080 → localhost:8081) | `k8s/kind-config.yaml` | Radar |
| In-cluster `elasticsearch:9200` Service pointing at start-local | `k8s/elasticsearch-bridge.yaml.tpl` | Elasticsearch |
| Env var template (OpenRouter, Elasticsearch, Dash0 OTLP, organizer API) | `.env.example` | all |
| Organizer schedule API, parser and Elasticsearch mappings | `backend/app/` | all |
| Radar MCP server for Claude Code | `.mcp.json` | Radar |
| Start/stop everything | `scripts/dev-up.sh`, `scripts/dev-down.sh` | all |

Installed on this machine: `kubectl`, `kind`, `kubectl-radar` (in `~/.local/bin`) and
Elasticsearch + Kibana via start-local in `../elastic-start-local` (trial license
until Nov 29, then it drops to the free Basic license).

`scripts/dev-up.sh` also needs `curl` and `envsubst` (from gettext:
`sudo apt install gettext-base` on Debian/Ubuntu, `brew install gettext` on macOS).

## Daily use

```sh
./scripts/dev-up.sh            # kind cluster + Elasticsearch/Kibana + Radar
./scripts/dev-down.sh          # stop Radar and Elasticsearch (cluster keeps running)
./scripts/dev-down.sh --delete # also delete the cluster
```

- Radar UI: http://localhost:9280
- Kibana: http://localhost:5601 (user `elastic`, password in `../elastic-start-local/.env`)
- Elasticsearch: `http://localhost:9200` from this machine, `http://elasticsearch:9200` from pods

## You still need to do

### 1. Gitar (do this first)
1. Sign up at https://gitar.ai with GitHub and start the free 14-day Pro trial (no card).
   It lasts 14 days, so starting it any time from now on covers Nov 9.
2. Install the Gitar GitHub App on `jacob-erard-professional/WeMakeDevs2026` only.
3. Dashboard → **Settings → Configuration**: check the auto-apply criteria card and
   **Behavior → Retry unrelated CI failures**.
4. Push this setup branch and open it as the first PR so Gitar reviews it. From then on,
   every feature goes through a PR. On a PR, comment `gitar auto-apply:on` (or add the
   `gitar-managed` label) to let Gitar push fixes, including for failing CI.

### 2. Dash0
1. Sign up at https://app.dash0.com and pick a region.
2. Run the in-app onboarding for your language. It shows the OTLP endpoint and an auth
   token pre-filled. Copy them into `.env` (`OTEL_EXPORTER_OTLP_ENDPOINT`,
   `OTEL_EXPORTER_OTLP_HEADERS`).
3. Connect the Dash0 MCP server to Claude Code (get the URL from
   **Settings → Endpoints → MCP**):
   ```sh
   claude mcp add --transport http --scope user dash0 https://api.<region>.aws.dash0.com/mcp
   ```
   Then run `/mcp` in Claude Code, pick **dash0** and sign in with OAuth.
4. Try **Agent0** (https://www.dash0.com/agent0). The judges want to see it, or the MCP
   server, find a real bug during the day.

### 3. Radar
- Nothing to install. Run `./scripts/dev-up.sh`, then open Claude Code in this repo and
  approve the `radar` MCP server from `.mcp.json`.
- AI investigations use your local `claude` (or `codex`) CLI, with no API key. Pick the
  model in the Radar UI under **Settings → AI investigations**.

### 4. OpenRouter and organizer backend
- Add an OpenRouter key to `.env` as `OPENROUTER_API_KEY`; `OPENROUTER_MODEL` defaults to `openai/gpt-4o-mini`.
- Set `ORGANIZER_API_KEY` to a long random secret. Organizer requests send it as `Authorization: Bearer ...`.
- Build and load the backend image, create/update its Kubernetes Secret from `.env`, then apply the workload:
  ```sh
  docker build -f backend/Dockerfile -t wemakedevs2026-backend:dev .
  kind load docker-image wemakedevs2026-backend:dev --name wemakedevs2026
  uv run python scripts/create-backend-secret.py
  kubectl apply -f k8s/backend.yaml
  ```
- The helper reads `.env` and never prints secret values. It includes optional Dash0 OTLP endpoint and headers when configured.
- API docs are available at http://localhost:8081/docs. See `backend/docs/endpoints/` for the organizer request shapes.

### 5. Before Nov 9
- `cp .env.example .env` and fill it in.
- Run `./scripts/dev-up.sh` once on the venue Wi-Fi day (or the night before) so the
  Docker images are already cached.
- Confirm the hackathon rules on whether pre-event backend implementation is allowed.
