# Click Talk

Conference networking that starts from a link. Built for the [Cloud Native Hackathon](https://luma.com/cnh) at KubeCon NA 2026, Salt Lake City.

**Live demo:** https://wearedevs.cnh.radarhq.io · **Join the demo conference:** https://wearedevs.cnh.radarhq.io/join/conference-671748c040a0 · API docs at `/api/docs`

## The problem

Big conferences publish hundreds of sessions across a dozen rooms; KubeCon NA 2026 has about 600. Attendees skim the schedule, miss the talks that matter to them, and rarely meet the people working on the same problems.

## What it does

**Organizers** create a conference, paste their schedule URL (or upload a PDF, DOCX, ICS or JSON file), review the parsed sessions in a time × room grid, and publish. They get a join link and QR code to put on Luma, badges or a slide.

**Attendees** open the link and drop in a résumé or LinkedIn PDF. The form prefills their name, email, LinkedIn, bio and interests, and they add what they want to see. Then they get:
- **Ranked talks:** the sessions closest to their profile, each labelled with a match percentage.
- **A best schedule:** the highest-relevance set of talks with no time overlaps, shown as a one-page plan they can export to their calendar (.ics).
- **People to meet:** other attendees who opted into discovery, matched on what they work on and what they're looking for, with a reason for each match. Contact details are shared only when a connection is accepted.

Progress is kept in the browser, so refreshing or pressing Back never loses a profile or a plan.

## How it works

```
Luma link / QR ─► Expo web app (nginx) ─/api─► FastAPI ─► Elastic Cloud Serverless
                                                 │          ├ talks, attendees, conferences, connections
                                                 │          └ talks-archive: 24,691 past KubeCon + PyVideo talks
                                                 ├─► OpenAI (résumé fields, fallback schedule parsing)
                                                 └─► OpenTelemetry ─► Dash0
```

- **Schedule import** (`backend/app/schedule_parser.py`, `schedule_adapters.py`): exact parsers for Sched, Sessionize, pretalx, frab, ICS and Linux Foundation event pages, with no LLM. The full KubeCon NA page parses to 576 talks in about 1.5 s. Anything else falls back to OpenAI structured output. URL fetches are SSRF-guarded.
- **Matching** ([vector-matching spec](backend/docs/vector-matching.md)): talks and profiles are embedded with Elastic-hosted Jina embeddings (`semantic_text`) into one vector space, so a profile can query talks and a talk can query people. People search is hybrid (BM25 + vectors, RRF) with mutual-interest matching.
- **Schedules** (`backend/app/schedule_recommendations.py`): Elasticsearch relevance scores become the weights for k-best weighted interval scheduling (dynamic programming), which returns the top 3 conflict-free schedules.
- **Publishing at scale:** large schedules are indexed in the background with progress recorded on the conference, so a 576-talk publish fits inside the gateway's 15 s request limit.
- **Privacy:** raw résumés are never stored. Contact details are extracted without the model and never enter the matchable fields. Organizer and attendee credentials are random tokens, stored only as SHA-256 hashes.

## How we used the sponsor tools

- **Elasticsearch (Elastic Cloud Serverless):** the only data store. It handles semantic and hybrid search, reranking, the talk archive, and the vectors behind every recommendation.
- **Radar:** the hosted vcluster (`team-wearedevs`) runs the frontend and backend. Argo CD syncs `deploy/` from a bot-written `deploy` branch on every merge to `main`. We used Radar's MCP and UI to debug rollouts and routing.
- **Gitar:** reviewed every PR against our repo rules (`.gitar/rules`: secrets guard, Kubernetes manifest review, OTel instrumentation, single data store, LLM call hygiene). It caught real bugs: a bulk-indexing batch that dropped a document, an SSRF bypass via DNS rebinding, and a timestamp crash in the organizer view. It auto-applied fixes and auto-merged small PRs.
- **Dash0:** the backend exports OpenTelemetry traces and metrics (FastAPI, every Elasticsearch call, background publishing) over OTLP to Dash0.
- **OpenAI:** structured-output parsing of résumés and of schedules that aren't in a known format.

## Team

[@jacob-erard-professional](https://github.com/jacob-erard-professional) · [@dpanchekha](https://github.com/dpanchekha) · [@SmithJaxon](https://github.com/SmithJaxon) · [@tuckerbolick](https://github.com/tuckerbolick)

Setup and the remaining manual steps are in [SETUP.md](SETUP.md); how each sponsor tool is set up and used is in [AGENTS.md](AGENTS.md).

## Local app development

After copying `.env.example` to `.env` and filling in the Elasticsearch values, start the API and
Expo web app together:

```sh
./run.sh
```

The API is at http://localhost:8000/docs and the web app at http://localhost:8081. `Ctrl-C` stops
both. Override the ports when needed, for example `BACKEND_PORT=8002 FRONTEND_PORT=8082 ./run.sh`.

## AI disclosure

Per the hackathon rules, here is how we used AI coding assistants:

- **Claude Code (Anthropic: Claude Opus 5.5 and Claude Fable 5.1)** wrote and edited code, docs, deploy config and scripts across the repo (backend, frontend site shell, Elasticsearch setup, CI/deploy), and ran checks against our dev stack. Commits it contributed to carry a `Co-Authored-By: Claude …` trailer.
- **OpenAI Codex** was used for some frontend and backend work (branches prefixed `codex/`).
- **Gitar** reviewed every pull request, and some of its suggested fixes were applied as commits (`Co-Authored-By: Gitar` trailer).
- **In the product:** OpenAI models parse uploaded conference schedules (`backend/app/schedule_parser.py`). Uploaded résumés are sent to OpenAI to extract a headline, skills and interests for matching (`backend/app/resume_parser.py`); the raw file is never stored. Recommendations use Elastic-hosted Jina embeddings for vector search, not a chat model.

Every change landed through a pull request reviewed by Gitar; some small PRs were approved and merged by Gitar without a human review.
