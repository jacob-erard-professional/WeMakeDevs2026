# Setup

Hackathon: Cloud Native Hackathon, Mon Nov 9, Salt Lake City (https://luma.com/cnh).
Track details and resources: https://wemakedevs.org/hackathons/cnh/resources

## Already done in this repo

| Thing | Where | Track |
|---|---|---|
| Review conventions, rules, auto-apply criteria | `.gitar/` | Sonar / Gitar |
| CI (ruff + pytest once `pyproject.toml` exists; manifest validation) | `.github/workflows/ci.yml` | Sonar / Gitar |
| Local kind cluster config (app NodePort 30080 → localhost:8081) | `k8s/kind-config.yaml` | Radar |
| `elasticsearch` Secret (ES_URL + ES_API_KEY) for pods, created from `.env` | `scripts/dev-up.sh` | Elasticsearch |
| Env var template (OpenAI, Elasticsearch, Dash0 OTLP) | `.env.example` | all |
| Radar MCP server for Claude Code | `.mcp.json` | Radar |
| Start/stop everything | `scripts/dev-up.sh`, `scripts/dev-down.sh` | all |

Installed on this machine: `kubectl`, `kind`, `kubectl-radar` (in `~/.local/bin`).
Elasticsearch is a shared **Elastic Cloud Serverless** project (nothing to run locally):
`ES_URL` is in `.env.example`; put your API key in `.env` as `ES_API_KEY` (create one in
the project's Manage/Kibana → API keys, or use the shared key passed around out-of-band).

`scripts/dev-up.sh` also needs `curl`.

## Daily use

```sh
./scripts/dev-up.sh            # kind cluster + elasticsearch Secret + Radar
./scripts/dev-down.sh          # stop Radar (cluster keeps running)
./scripts/dev-down.sh --delete # also delete the cluster
```

- Radar UI: http://localhost:9280
- Elasticsearch: `ES_URL` from `.env`, same URL from this machine and from pods.
  `dev-up.sh` creates the `elasticsearch` Secret (`ES_URL`, `ES_API_KEY`) in the cluster;
  pods use `envFrom: [{secretRef: {name: elasticsearch}}]`. It prints the HTTP status of a
  test request (200 = key works, 401 = fix `ES_API_KEY`).
- Kibana: part of the cloud project; open it from the Elastic Cloud console.
- Serverless notes: don't set `number_of_shards` / `number_of_replicas` in index settings
  (Serverless rejects them); `semantic_text` uses Elastic-hosted inference endpoints by
  default, no local ML allocation needed.

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

### 4. OpenAI
- Claim the $50 credits at the event, create an API key and put it in `.env` as `OPENAI_API_KEY`.

### 5. Before Nov 9
- `cp .env.example .env` and fill it in.
- Run `./scripts/dev-up.sh` once on the venue Wi-Fi day (or the night before) so the
  Docker images are already cached.
- Read the hackathon rules on whether code written before the event is allowed. This
  repo only has tooling and config, no product code.
