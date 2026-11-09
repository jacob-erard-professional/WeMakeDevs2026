# Auto-merge criteria for WeMakeDevs2026

Arm auto-merge (squash) on every PR Gitar approved so features land without
waiting on a human. Branch protection enforces CI. Do not arm auto-merge when:

- The PR is a draft or has unresolved review threads.
- The diff touches `.gitar/`, `.github/workflows/`, `scripts/dev-up.sh`,
  `scripts/dev-down.sh` or `k8s/elasticsearch-bridge.yaml.tpl`; a human merges
  those.
- The diff adds a secret or real credential value anywhere, including `.env`.
- The PR is large (more than ~15 files or ~500 changed lines); leave the merge to
  the author so the demo stack does not change under them unnoticed.
