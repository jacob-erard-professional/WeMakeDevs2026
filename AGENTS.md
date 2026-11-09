# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Cursor, Gitar) working in this repo.

This repo is our entry for the **Cloud Native Hackathon** (WeMakeDevs, KubeCon NA): **Monday Nov 9 2026**, The Shop Workspace, Salt Lake City, in person. Theme: **make conferences easier**, before, during or after, for attendees, speakers, sponsors or organizers.
Source pages: https://www.wemakedevs.org/hackathons/cnh (overview, FAQ, judging), [/resources](https://www.wemakedevs.org/hackathons/cnh/resources), [/schedule](https://www.wemakedevs.org/hackathons/cnh/schedule).

A project enters **every sponsor track whose tool it genuinely uses**, plus Merge Forward, plus best overall (NVIDIA DGX Spark). The plan is to use all of them for real. Each section below covers what the judges want, what is already set up, and how to set up and use the tool while building.

Local setup, URLs and the remaining manual steps are in [SETUP.md](SETUP.md). Start the stack with `./scripts/dev-up.sh`.

## Ground rules for agents

- **Every change goes through a pull request** that Gitar reviews. Never push to `main`. Small PRs, one feature each. The judges check that features landed through Gitar-reviewed PRs.
- **Secrets live in `.env` only** (gitignored). Add new variable names to `.env.example` with a `<PLACEHOLDER>`. Quote values that contain spaces. Never print `.env` values in logs or output.
- **Elasticsearch is the single store** for conference data (talks, speakers, attendees, side events). Don't add a second database for the same data.
- **Instrument as you go**, not at the end: every new service, endpoint, Elasticsearch query and LLM call gets traces/logs/metrics.
- **Everything runs on Kubernetes** (the kind cluster from `dev-up.sh`, or the namespace organizers hand out). Manifests live in `k8s/`.
- Python, formatted and linted with `ruff`; tests in `tests/` with pytest. CI (`.github/workflows/ci.yml`) starts enforcing these once `pyproject.toml` exists.
- Accessibility is a requirement, not polish (Merge Forward track): labelled inputs, keyboard navigation, alt text, sufficient contrast, captions/transcripts for media.

## Event-day timeline (Mountain Time)

| Time | What |
|---|---|
| 9:00 | Check-in, breakfast |
| 10:00 | Kickoff and talks |
| 11:00–14:00 | Build |
| 14:00 | Lunch, panel, more build time |
| **17:30** | **Project submission deadline** |
| 17:30–18:30 | Presentations |
| 18:30–19:00 | Winners |

Aim to have a deployable vertical slice by 14:00, then spend the afternoon on depth: observability, rollouts and search quality. Leave 30 minutes before 17:30 for the demo run-through.

---

## Track 1: Sonar / Gitar, "Never Merge Broken" ($4,000)

Gitar is Sonar's AI code verification agent. It reviews PRs against our conventions, finds problems, generates fixes and diagnoses CI failures. It runs as a GitHub App, so there's nothing to install locally.

**Judges look for**
- Gitar is part of how we built: features landing through PRs it reviewed, "not one PR at the end".
- Project-aware setup: review instructions and repository rules that reflect how the team works.
- CI failure diagnosis and auto-apply used to fix real problems.

**Already set up**
- Gitar GitHub App installed on this repo; 14-day Pro trial (auto-apply and custom rules included).
- `.gitar/review/conventions.md`: review instructions (secrets, timeouts, input validation, accessibility, OTel, Elasticsearch, Kubernetes, style).
- `.gitar/rules/`: `secrets-guard.md` and `k8s-manifest-review.md` (YAML frontmatter: `title`, `description`, `when`, `actions`, `type`).
- `.gitar/config/apply.md`: what auto-apply may fix by itself.
- CI: `python` (ruff + pytest) and `manifests` (kubeconform) jobs.
- This file: Gitar reads `AGENTS.md` too.

**How to use it while building**
1. Branch → commit → `gh pr create`. Wait for the `Gitar` check and read its comment (`gh pr view <n> --json comments`) and inline findings (`gh api repos/jacob-erard-professional/WeMakeDevs2026/pulls/<n>/comments`).
2. Let Gitar apply its own fixes: tick "Apply fix" on a finding, or comment `gitar auto-apply:on` on the PR (or add the label `gitar-managed`). Prefer this over fixing by hand, because it's evidence for the judges.
3. When CI fails, let Gitar diagnose it and push the fix rather than fixing it locally first.
4. Grow the config as the project takes shape: add a review file per topic in `.gitar/review/` (e.g. `timezones.md`: session times are stored in UTC and shown in the venue's time zone, America/Denver), and add rules for repeatable checks. The organizers' example: "a repository rule that kicks in whenever your API changes and checks your frontend still matches it."
5. Demo idea from the organizers: break CI on purpose and let auto-apply fix it live.

Docs: [quickstart](https://docs.gitar.ai/quickstart) · [docs](https://docs.gitar.ai/introduction) · [project-aware reviews](https://www.sonarsource.com/resources/library/gitar-context-ingestion-for-project-aware-code-reviews/) · [with SonarQube Cloud](https://www.sonarsource.com/resources/library/multilayered-code-verification-with-gitar-sonarqube-cloud/)

---

## Track 2: Dash0, "Stop Flying Blind" ($4,000)

Dash0 is an observability platform built natively on OpenTelemetry. Agent0 is its AI SRE agent. Its MCP server gives Claude Code and other agents our live traces, logs and metrics.

**Judges look for**
- Depth of instrumentation: traces, logs, metrics, and real-user monitoring (RUM) if there's a frontend.
- Agent0 or the MCP server finding and fixing something real during the day, shown in the demo.
- Observability that's part of the product experience, not bolted on at the end.
- **Bonus:** a Dash0 dashboard or SLO that shows how healthy the app is.

**Already set up**
- Dash0 org in **us-west-2**, dataset `default`.
- `.env`: `OTEL_EXPORTER_OTLP_ENDPOINT` (`https://ingress.us-west-2.aws.dash0.com`), `OTEL_EXPORTER_OTLP_HEADERS` (quoted, with token and `Dash0-Dataset=default`), `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, and traces/metrics/logs exporters set to `otlp`.
- Dash0 MCP server connected in Claude Code at user scope (`claude mcp list` shows `dash0 ✔ Connected`).
- Verified: a test span (service `setup-verify`) was accepted and read back through MCP.

**How to set it up in the app (first hour)**
1. Python auto-instrumentation:
   ```sh
   uv add opentelemetry-distro opentelemetry-exporter-otlp
   uv run opentelemetry-bootstrap -a requirements > otel-requirements.txt   # instrumentations for the libraries we use
   uv add -r otel-requirements.txt && rm otel-requirements.txt
   uv run opentelemetry-instrument python -m <app>                 # reads the OTEL_* vars from .env
   ```
   Set `OTEL_SERVICE_NAME` per service. In Kubernetes, put the OTEL_* values in a Secret and mount them as env vars on each Deployment.
2. Add manual spans around Elasticsearch queries and business actions (search, schedule build, check-in), with attributes like `talk.id`, `search.query`, `search.results`.
3. LLM calls: trace them with OpenLIT (organizers' suggestion) so tokens, latency and cost show up in Dash0.
4. Frontend: add Dash0 website monitoring / RUM ([guide](https://dash0.com/guides/website-monitoring-with-opentelemetry-and-dash0)).
5. Kubernetes-wide telemetry: optionally install the [Dash0 Operator](https://www.dash0.com/docs/dash0/monitoring/kubernetes/dash0-operator/overview) in the cluster.
6. Build a dashboard and an SLO (e.g. search p95 latency, error rate) in Dash0 for the bonus point.

**How to use it while building**
- Ask the Dash0 MCP before guessing: `getSpans` / `getLogRecords` filtered by `service.name`, `getServiceCatalog`, `promql`, and `runTask` for an Agent0 investigation ("why is search slow?").
- In the Dash0 app, Agent0 can explain a problem and open a pull request with the fix. That PR then goes through Gitar too.
- Demo pattern from the organizers: a "chaos" button that injects latency or errors, then Agent0 finds the cause.

Docs: [docs](https://www.dash0.com/docs/dash0) · [integrations hub](https://www.dash0.com/hub/integrations) · [Agent0](https://www.dash0.com/agent0) · [MCP](https://dash0.com/docs/dash0/ai/mcp) · [Dash0 CLI](https://dash0.com/docs/dash0/miscellaneous/tooling/dash0-cli/quickstart) · [OTel demo app](https://www.dash0.com/hub/integrations/int_opentelemetry-demo/overview)

---

## Track 3: Radar (Skyhook), "AI SRE" ($4,000)

Radar is an open-source Kubernetes UI. Its AI SRE finds root causes from the UI or from a coding agent through Radar's MCP server.

**Judges look for**
- The app runs on Kubernetes with Radar connected (our cluster, or the namespace organizers give the team), operated through Radar's MCP and UI.
- **Production ready, not just running:** GitOps deploys, autoscaling, a canary or blue-green rollout, and fixing what Radar's audit flags.
- Radar is part of how we ship: the agent deploys, debugs, triggers rollouts and checks audits through Radar's MCP.
- Radar's AI SRE finding and fixing something real during the day, shown in the demo.

**Already set up**
- `kubectl`, `kind` and `kubectl-radar` (v1.19) in `~/.local/bin`.
- `k8s/kind-config.yaml`: cluster `wemakedevs2026`, app NodePort `30080` → `http://localhost:8081`.
- `./scripts/dev-up.sh` creates the cluster and starts Radar at http://localhost:9280 (MCP at `/mcp`).
- `.mcp.json` registers the `radar` MCP server (approve it once when Claude Code starts in this folder).
- Radar's AI investigations use the local `claude`/`codex` CLI, so no API key is needed. Pick the model under Settings → AI investigations.

**How to set it up for the project**
1. Containerize each service and load images into kind: `docker build -t <svc>:dev . && kind load docker-image <svc>:dev --name wemakedevs2026`.
2. Manifests in `k8s/`: Deployment + Service per component, **resource requests/limits, readiness and liveness probes**, and config from ConfigMaps/Secrets (Gitar's `k8s-manifest-review` rule checks this). Expose the web app as NodePort 30080.
3. Autoscaling: add a HorizontalPodAutoscaler. kind has no metrics-server by default, so install it for the HPA to work.
4. Rollouts: do at least one canary or blue-green release, e.g. two Deployments behind one Service with weighted replicas, or Argo Rollouts.
5. GitOps: deploy from git (Argo CD or Flux watching `k8s/`) rather than ad-hoc `kubectl apply`.
6. Run Radar's audit and fix what it flags. Keep the before/after for the demo.
7. If organizers give us a namespace on their cluster, point `kubectl` at that kubeconfig and restart Radar against it.

**How to use it while building**
- Prefer Radar's MCP tools over raw kubectl for reads: issues, diagnose, get_changes, get_resource, list_resources, search, workload/pod logs, events.
- When something breaks, start an AI investigation in Radar (or ask through MCP), apply the fix in a PR, and capture it for the demo.

Docs: [docs](https://radarhq.io/docs) · [install](https://radarhq.io/docs/install) · [MCP](https://radarhq.io/docs/features/mcp) · [AI investigations](https://radarhq.io/product/ai-investigations) · [GitHub](https://github.com/skyhook-io/radar) · [Discord](https://radarhq.io/community/chat)

---

## Track 4: Elasticsearch, "Find the Right Talk" ($4,000)

Elasticsearch is the search engine and vector database behind our search, recommendations and the RAG for our AI features.

**Judges look for**
- Elasticsearch is the **core data layer** of the app, not a side feature.
- Smart use of search: keyword, semantic, vector or hybrid.

**Already set up**
- Elasticsearch 9.5.5 + Kibana via start-local in `../elastic-start-local` (trial with all features until Nov 29, then the free Basic license).
- `.env`: `ES_URL=http://localhost:9200` and `ES_API_KEY`. From pods use `http://elasticsearch:9200`: `dev-up.sh` connects the container to the kind network and applies `k8s/elasticsearch-bridge.yaml.tpl`.
- Kibana at http://localhost:5601 (user `elastic`, password in `../elastic-start-local/.env`).

**How to set it up in the app**
1. Client: `uv add elasticsearch` and connect with `Elasticsearch(os.environ["ES_URL"], api_key=os.environ["ES_API_KEY"])`.
2. Define index mappings in code and create them idempotently at startup: indices for `talks`, `speakers`, `attendees`, `events`. Talks get text fields (title, abstract, tags) plus a `semantic_text` or `dense_vector` field for the abstract.
3. Load the schedule data (talks, speakers, rooms, times in UTC) with a seed script.
4. Search: use **hybrid** (BM25 + vector, e.g. a retriever with RRF) for user-facing queries. Example target from the organizers: "something on eBPF and security" finds the right session even when those words aren't in the title.
5. RAG: retrieve abstracts from Elasticsearch, then answer with OpenAI. Trace both steps.
6. Use Kibana Dev Tools to inspect queries and relevance while tuning.

Docs: [start-local](https://github.com/elastic/start-local) · [get started with search](https://www.elastic.co/docs/solutions/search/get-started)

---

## Merge Forward: "Conferences for Everyone" (iPad)

For the project that makes conferences more inclusive and accessible. Every project enters automatically. Merge Forward is a CNCF community group home to seven diversity groups ([about](https://ocgroups.dev/cncf/group/merge-forward)).

**What to do:** treat accessibility as a feature in the demo. Remove a real barrier: screen-reader-friendly schedule, captions/transcripts, quiet-room or step-free routes, low-bandwidth mode, plain-language summaries, first-timer guidance. Test with keyboard only and a screen reader.

---

## OpenAI ($50 credits per participant)

No track of its own; the credits are for the LLM features. Claim them at the event, create an API key, and set `OPENAI_API_KEY` in `.env` (and in the Kubernetes Secret). Wrap every call with a timeout and trace it (see Dash0 above).

---

## Before you open a PR (checklist)

- [ ] `uvx ruff check . && uvx ruff format --check .` and `uv run pytest` pass
- [ ] New config is in `.env.example`; no secrets in the diff
- [ ] New code paths emit spans/logs; check in Dash0 (MCP `getSpans`) that they show up
- [ ] Manifests have requests/limits and probes; app still healthy in Radar
- [ ] Data goes through Elasticsearch; mappings updated in code
- [ ] UI changes are keyboard and screen-reader accessible
- [ ] `~/.claude/skills/cnh-setup/scripts/verify-stack.sh` still passes
