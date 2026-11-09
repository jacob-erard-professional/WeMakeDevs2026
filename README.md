# WeMakeDevs2026
Hackathon repo for: https://luma.com/cnh

Make conferences easier, built with Gitar (Sonar), Dash0, Radar, Elasticsearch and OpenAI.

Setup and the remaining manual steps are in [SETUP.md](SETUP.md); how to set up and use each sponsor tool is in [AGENTS.md](AGENTS.md).

Live demo: https://wearedevs.cnh.radarhq.io (API under `/api`, docs at `/api/docs`).

## AI disclosure

Per the hackathon rules, here is how we used AI coding assistants:

- **Claude Code (Anthropic: Claude Opus 5.5 and Claude Fable 5.1)** wrote and edited code, docs, deploy config and scripts across the repo (backend, frontend site shell, Elasticsearch setup, CI/deploy), and ran checks against our dev stack. Commits it contributed to carry a `Co-Authored-By: Claude …` trailer.
- **OpenAI Codex** was used for some frontend and backend work (branches prefixed `codex/`).
- **Gitar** reviewed every pull request, and some of its suggested fixes were applied as commits (`Co-Authored-By: Gitar` trailer).
- **In the product:** OpenAI models parse uploaded conference schedules (`backend/app/schedule_parser.py`). Recommendations use Elastic-hosted Jina embeddings for vector search, not a chat model.

Every change landed through a pull request reviewed by Gitar; some small PRs were approved and merged by Gitar without a human review.
