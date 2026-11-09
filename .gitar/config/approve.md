# Auto-approve criteria for WeMakeDevs2026

We are building fast during a one-day hackathon, so approve generously: approve
any PR with no important or critical review findings. Withhold approval when:

- The diff adds a secret or real credential value: a `.env` file, an API key, a
  Dash0 / Elasticsearch / OpenAI token or a password (placeholders in
  `.env.example` are fine).
- The diff touches `.gitar/` (review conventions, rules or config) or
  `.github/workflows/`; a human approves those.
- The diff deletes or weakens `scripts/dev-up.sh`, `scripts/dev-down.sh` or
  `k8s/elasticsearch-bridge.yaml.tpl`.
- The PR is large (more than ~15 files or ~500 changed lines) and has review
  findings that are still unresolved.
