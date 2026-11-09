# WeMakeDevs2026 review conventions

This is a one-day hackathon project that makes conferences easier for attendees,
speakers, sponsors or organizers. Optimise reviews for "works in the demo and is
easy to change", not for long-term enterprise polish.

## Must fix

- No secrets in the repo: API keys, Dash0 tokens, Elasticsearch passwords and
  OpenAI keys come from environment variables only (see `.env.example`).
- Every external call (OpenAI, Elasticsearch, HTTP APIs) has a timeout and handles
  failure with a clear error instead of crashing the request.
- New HTTP endpoints validate their input.
- Anything shown to attendees must work with a keyboard and a screen reader:
  labelled form fields, alt text on images, no information conveyed by colour alone.

## Observability (Dash0 track)

- New services and entrypoints are instrumented with OpenTelemetry. Do not
  hand-roll a custom metrics or tracing client.
- Use structured logs with useful attributes (talk id, user action, query), never
  `print` for operational output.
- Wrap LLM calls and Elasticsearch queries in spans so they show up in traces.

## Search (Elasticsearch track)

- Elasticsearch is the source of truth for talks, speakers, attendees and events.
  Do not add a second store for the same data.
- Index mappings live in code and are created idempotently on startup.
- Prefer hybrid (keyword + vector) search for user-facing queries.

## Kubernetes (Radar track)

- Every Deployment has resource requests/limits plus readiness and liveness probes.
- Configuration comes from ConfigMaps and Secrets, not values baked into images.

## Style

- Python: formatted and linted with `ruff`; type hints on public functions.
- Keep functions small and name things after the conference domain (talk,
  session, speaker, attendee, sponsor).
