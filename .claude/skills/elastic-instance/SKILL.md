---
name: elastic-instance
description: >-
  Work with this team's shared Elastic Cloud Serverless project, the single data store behind the
  conference app (FastAPI backend in backend/app/main.py, indices talks / attendees / connections,
  read-only archive alias talks-archive). Use it whenever someone queries, inspects, debugs, seeds,
  counts, reindexes or changes Elasticsearch data, indices, mappings or inference endpoints for this
  app; writes or reviews backend code that calls Elasticsearch (semantic, hybrid RRF/linear,
  reranker, highlight, bulk, es_call); needs ES_URL / ES_API_KEY / Kibana / Agent Builder / MCP for
  this project; or asks why a search returns the wrong people or talks. Also use it for "check the
  cluster", "what's in the index", "why is the mapping not updating", "run this against Elastic" and
  any curl or Python against the .es. / .kb. elastic.cloud hosts, even if Elasticsearch isn't named.
---

# Elastic instance: the team's Elastic Cloud Serverless project

One shared project, used at the same time by the deployed backend (Argo CD, namespace
`team-wearedevs`), every teammate's local backend, Kibana, and coding agents. Anything you change
in it is live for everyone immediately. Read freely; write only when the task calls for it and the
team knows.

Source of truth for mappings and queries is the code, `backend/app/main.py` (`INDEX_BODIES`,
`es_call`, the `recommended_*` functions). `backend/docs/vector-matching.md` is the design spec
with test results, `backend/docs/elasticsearch-connection.md` the connection notes. When a doc and
the code disagree, the code wins.

## Instance facts

| What | Where to find it |
|---|---|
| Elasticsearch | `ES_URL` in the repo-root `.env` (also in `.env.example`; the URL itself is not secret). Host pattern `my-elasticsearch-project-<id>.es.us-east4.gcp.elastic.cloud:443` |
| Kibana | same host with `.kb.` instead of `.es.` and no `:443` |
| Agent Builder MCP | `<kibana>/api/agent_builder/mcp` |
| Version | Elasticsearch 9.7.0, `build_flavor: serverless`, GCP us-east4 |
| Auth | header `Authorization: ApiKey <ES_API_KEY>`; Kibana APIs also need `kbn-xsrf: true` |
| Local credentials | `.env` at the repo root (gitignored): `ES_URL`, `ES_API_KEY` |
| Hosted credentials | Secret `app-env` in `team-wearedevs`, created by `scripts/push-secrets.sh`, mounted on Deployment `backend` only. The local kind cluster uses a Secret named `elasticsearch` from `scripts/dev-up.sh` instead |

Serverless means: no `_cluster/health`, `_nodes` or `_cat/nodes`; `GET /` and `_count` are the
health checks. Index settings must not include `number_of_shards`, `number_of_replicas` or
`refresh_interval`; the request is rejected.

## Secret handling

The `.env` holds the Elastic key, the OpenAI key, the organizer key and the Dash0 token, and some
values contain spaces. So:

- Never `source .env` or `cat .env`. Sourcing breaks on the spaces and the shell error echoes part
  of the Dash0 token into your transcript.
- Read one key at a time into a variable and never echo it:
  ```sh
  ES_URL="$(grep -m1 '^ES_URL=' .env | cut -d= -f2-)"
  ES_API_KEY="$(grep -m1 '^ES_API_KEY=' .env | cut -d= -f2-)"
  ```
- Never put the key in a commit, a log line, a span attribute, `.mcp.json` (committed) or chat.
  `claude mcp add --header "Authorization: ApiKey ..."` stores it in your user config, which is fine.
- If a command fails, show the HTTP status and the response body, not the command line that
  carried the header.

`scripts/es-check.sh` (next to this file) follows these rules and runs every recipe below in one
go. Start there when you need a picture of the project.

## Indices and ownership

| Index | Owner | `dynamic` | `_id` | Notes |
|---|---|---|---|---|
| `talks` | backend | `strict` | `{conference_id}:{talk_id}` | live schedule; `semantic_content` = title + "\n\n" + abstract (title alone without abstract) |
| `attendees` | backend | `strict` | `{conference_id}:{attendee_id}` | four `semantic_text` fields: `profile`, `looking_for`, `can_help_with`, `resume_text`; `interests`/`skills` are keywords with the `lower` normalizer; `email`, `linkedin_url`, `access_token_sha256` are stored but not indexed |
| `connections` | backend | `true` | `{conference_id}:{connection_id}` | the only non-strict app index; written with `op_type="create"` so a duplicate id is a 409, not an overwrite |
| `talks-archive` | read-only, not ours | strict | archive `id` | alias over `talks-jina`: 24,691 past KubeCon (`source: kubecon`) and PyVideo (`source: pyvideo`) talks, `semantic_content` embedded with Jina v5. Never write to it; to change it, build a new index and move the alias |

`talk_id` is either what the organizer supplied or `sha256(conference_id, title, start_utc, room,
tracks, speakers)[:32]`, so re-confirming a schedule overwrites instead of duplicating.
`access_token_sha256` is `sha256(token)`; the raw bearer token `{conference_id}:{attendee_id}:{token}`
is only ever returned once, to the client.

A field that is not in the strict mapping fails the write with `400 strict_dynamic_mapping_exception`.
The backend protects itself by filtering documents through `ATTENDEE_FIELDS` / `TALK_FIELDS` before
indexing; a seed script or an ad-hoc write does not get that protection.

Other things you will see in `_cat/indices` and can ignore: `.ds-traces-agent_builder.otel-*`
(Agent Builder's own traces) and anything not listed above that a teammate created by hand
(check with them before touching it). `docs.count` in `_cat/indices` counts `semantic_text` chunk
documents too; use `GET /<index>/_count` for the real number.

## Mapping changes

`ensure_indices()` only creates an index that does not exist. It never compares or updates an
existing mapping, so editing `INDEX_BODIES` and deploying changes nothing in the cloud; the old
mapping stays and writes with the new field fail with 400. Treat every mapping change as a
migration:

1. Tell the team first. The deployed backend and everyone's local backend read the same index, and
   deleting `attendees` invalidates every attendee token (the seed script re-creates its demo
   attendees on 401/403 for exactly this reason).
2. `GET /<index>/_count`. If it is empty, `DELETE /<index>` and either restart a backend (startup
   recreates it from `INDEX_BODIES`) or `PUT /<index>` with the body from `INDEX_BODIES`.
3. If it has data you need: `PUT /<index>-v2` with the new body, `POST /_reindex`
   `{"source":{"index":"<index>"},"dest":{"index":"<index>-v2"}}` (semantic_text fields re-embed,
   so budget about a second per document), verify `_count` matches, then either repoint the code or
   delete the old index and reindex back. The app uses plain index names, not aliases, so a swap is
   two steps and the backend is briefly unable to write in between.
4. Land the `INDEX_BODIES` change in the same PR so a fresh environment matches the cloud.

## Inference endpoints

`GET /_inference/_all` lists them. What matters here:

| Endpoint | Use | Behaviour |
|---|---|---|
| `.jina-embeddings-v5-text-small` | every `semantic_text` field in `talks`, `attendees`, `talks-archive` (1024 dims, cosine) | `service: elastic`, always on, no cold start |
| `.jina-reranker-v3.5` | `text_similarity_reranker` | always on, adds about 1 s |
| `.elser-2-elastic` | sparse embeddings, the `semantic_text` default if you omit `inference_id` | works; do not mix it into an index that uses Jina |
| `.multilingual-e5-small-elasticsearch` | `service: elasticsearch`, scales to zero | first call after idle returns `408 model_deployment_timeout_exception` for about 50 s |
| `.anthropic-claude-*`, `.gp-llm-v2-*`, other `completion` / `chat_completion` | hosted LLMs | `403 Forbidden` on this trial when called through `_inference`. Generate with OpenAI (`OPENAI_API_KEY`) or use Agent Builder (below), which has its own connector |

`semantic_text` embeds on write, so each attendee save or schedule confirm costs roughly an extra
second. The backend client is `Elasticsearch(ES_URL, api_key=ES_API_KEY, request_timeout=5)`:
a bulk of a few hundred talks can approach that budget (`BULK_BATCH_SIZE = 500` action pairs).
If a bulk write 503s, suspect the timeout before suspecting the cluster.

## Query patterns that work on this project

All of these are the shapes `main.py` uses. Python: `es.search(index=..., **body)`.

**Semantic query**, filtered to one conference and confirmed talks:
```json
{"query": {"bool": {
  "must": [{"semantic": {"field": "semantic_content", "query": "something on eBPF and security"}}],
  "filter": [{"term": {"conference_id": "cnh-slc-2026"}}, {"term": {"confirmed": true}}]}},
 "_source": ["talk_id", "title", "room", "start_time", "end_time"], "size": 20}
```

**Blockout exclusion** (a talk overlaps a blockout when it starts before the blockout ends and ends
after it starts; one clause per blockout, inside `must_not` of the same `bool`):
```json
{"bool": {"filter": [{"range": {"start_time": {"lt": "<blockout end>"}}},
                     {"range": {"end_time":   {"gt": "<blockout start>"}}}]}}
```

**Hybrid RRF** (rank-based fusion; used for "similar people" where the signals are heterogeneous):
```json
{"retriever": {"rrf": {"rank_window_size": 50, "retrievers": [
   {"standard": {"query": {"semantic": {"field": "profile", "query": "<my profile>"}}}},
   {"standard": {"query": {"semantic": {"field": "resume_text", "query": "<my profile>"}}}},
   {"standard": {"query": {"bool": {"should": [{"terms": {"skills": ["kubernetes"]}}],
                                     "minimum_should_match": 1}}}}]}},
 "size": 10, "_source": {"includes": ["attendee_id", "name", "headline"]}}
```
Each retriever carries its own `bool.filter`/`must_not` for eligibility (see Privacy). An empty
`terms` list is an error: drop that retriever when the person has no skills or interests.

**Linear with minmax** (score-based fusion; used for two-sided matching). RRF only sees ranks and
in testing put the wrong person first; `linear` kept the real match at 0.74 vs 0.49:
```json
{"retriever": {"linear": {"rank_window_size": 50, "normalizer": "minmax", "retrievers": [
   {"retriever": {"standard": {"query": {"semantic": {"field": "can_help_with", "query": "<what I'm looking for>"}}}}, "weight": 0.7},
   {"retriever": {"standard": {"query": {"semantic": {"field": "looking_for",   "query": "<what I can help with>"}}}}, "weight": 0.3}]}}}
```

**Reranker wrap** (sharper top results, about +1 s). The reranker's `rank_window_size` must be at
most the inner retriever's; the inner default is 10, so set both:
```json
{"retriever": {"text_similarity_reranker": {
   "retriever": {"rrf": {"rank_window_size": 50, "retrievers": [ ... ]}},
   "field": "semantic_content", "inference_id": ".jina-reranker-v3.5",
   "inference_text": "<query>", "rank_window_size": 20}}}
```

**Semantic highlight** (the passage that matched, for a "Why: ..." line):
```json
{"highlight": {"fields": {"profile": {"type": "semantic", "number_of_fragments": 1}}}}
```

**Keyword / aggregations on the archive**: `multi_match` over `title^3, abstract, speakers_text,
tracks`; `terms` aggs on `conference.raw`, `tracks`, `year`. Archive filters: `source`, `year`,
`conference_id`.

## Privacy rules (enforce in code and in ad-hoc queries)

The attendee document holds a bio, a resume, contact details and a token hash. The default
`_source` returns all of it. Tested: a search on `attendees` without `_source` hands back
`resume_text`.

1. Every query on `attendees` sets `_source` explicitly. In code that is
   `SAFE_ATTENDEE_SOURCE = {"includes": ["attendee_id", "name", "headline"]}`. Use the same
   list when poking at the index by hand unless you are debugging your own test attendee.
2. Highlight only `profile` and `can_help_with`. Never highlight `resume_text`; highlights return
   the matching passage verbatim.
3. A candidate is eligible only when: same `conference_id`, `discovery_opt_in: true`, and not the
   requester (`eligible_attendees()` in `main.py`). Every people retriever carries this filter.
4. `email`, `linkedin_url`, `resume_text` leave the index only through `/accept-connection`, and
   only the fields the acceptor chose to share.
5. No profile, bio, resume or query text in logs or span attributes. Put IDs and counts on spans.

## Backend code pattern

```python
hits = await es_call(
    "recommend_talk_attendees",                      # span name, also db.operation
    lambda: es.search(index="attendees", size=10, source=SAFE_ATTENDEE_SOURCE, query=...)["hits"]["hits"],
    **{"db.elasticsearch.index": "attendees"},       # attributes: ids and counts only
)
```

- `es_call` runs the sync client in `run_in_threadpool` inside an OTel span, maps `NotFoundError`
  to 404 and anything else to 503 (the real exception goes to the log, not the client). Do not call
  `es.*` directly from an `async def`; it blocks the event loop.
- Writes call `await ensure_indices_ready()` first so a write can never create an index with a
  dynamic mapping.
- Use `refresh="wait_for"` when the response must include the write (save-user-data recommends
  from the doc it just wrote; confirm-schedule returns a count). Skip it for fire-and-forget
  writes such as connection records.
- New field: add it to `INDEX_BODIES`, to the Pydantic model, and to the `_source` lists that
  need it; then run the mapping migration above. The strict mapping will tell you if you forget.
- New endpoint that touches `attendees`: start from `eligible_attendees()` and
  `SAFE_ATTENDEE_SOURCE`; a reviewer will look for both.

## Operator recipes (read-only unless marked)

With `ES_URL` and `ES_API_KEY` in variables as above:

```sh
H="Authorization: ApiKey $ES_API_KEY"
KB_URL="${ES_URL/.es./.kb.}"; KB_URL="${KB_URL%:443}"                 # Kibana host
curl -s -H "$H" "$ES_URL/"                                       # 200 + version; 401 = bad key
curl -s -H "$H" "$ES_URL/_cat/indices?v&h=index,docs.count,store.size&s=index"
curl -s -H "$H" "$ES_URL/_cat/aliases?v"                         # talks-archive -> talks-jina
curl -s -H "$H" "$ES_URL/talks,attendees,connections/_mapping"
curl -s -H "$H" "$ES_URL/attendees/_count?q=conference_id:cnh-slc-2026"
curl -s -H "$H" -H 'Content-Type: application/json' "$ES_URL/talks-archive/_search" -d '{
  "size": 3, "_source": ["title", "conference", "year"],
  "query": {"semantic": {"field": "semantic_content", "query": "something on eBPF and security"}}}'
curl -s -H "$H" "$ES_URL/_inference/_all"
```

Or run all of them: `.claude/skills/elastic-instance/scripts/es-check.sh`.

Destructive calls need a human yes first, every time, because the project is shared and live:
`DELETE /<index>`, `POST /<index>/_delete_by_query`, `PUT /<index>/_mapping`, `POST /_reindex`
into an existing index, `POST /_aliases` on `talks-archive`, and any write to `talks-jina`. Say what
will be deleted and how many documents (`_count` first), then wait for confirmation.

## Agent Builder and MCP

Kibana's Agent Builder has an agent `elastic-ai-agent` (Claude Sonnet connector) with index-search
and ES|QL tools over this project. It answers RAG questions over `talks-archive` in about 9 s:

```sh
curl -s -H "$H" -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \
  "$KB_URL/api/agent_builder/converse" \
  -d '{"agent_id": "elastic-ai-agent", "input": "Which past KubeCon talks covered eBPF runtime security?"}'
```

The same agent is reachable as an MCP server at `$KB_URL/api/agent_builder/mcp` (streamable HTTP,
same `ApiKey` header). `claude mcp add --transport http elastic <url> --header "Authorization: ApiKey <key>"`
adds it to Claude Code at user scope; never put that header in the committed `.mcp.json`.

Elastic's official skills plugin (`claude plugin marketplace add https://github.com/elastic/agent-skills`)
covers general Elasticsearch, ES|QL and Kibana knowledge. It complements this skill: that one knows
Elasticsearch, this one knows our project.

## Hard rules

1. Never print, echo, source or commit `.env` values; read one key at a time into a variable.
2. Writes to the shared project happen only when the task calls for them and the team knows; destructive calls wait for an explicit yes.
3. `talks-archive` / `talks-jina` is read-only for us.
4. Every `attendees` query sets `_source`; highlight only `profile` and `can_help_with`; filter by conference, opt-in and not-self.
5. No profile, bio, resume or query text in logs or span attributes.
6. Backend Elasticsearch calls go through `es_call`, off the event loop, with `refresh="wait_for"` when the response depends on the write.
7. A mapping change is a migration: check `_count`, delete-and-recreate or reindex, update `INDEX_BODIES` in the same PR.
8. No shard, replica or refresh_interval settings; no `_cluster`/`_nodes` APIs on Serverless.
9. `semantic_text` fields in one index share one `inference_id`; the app's is `.jina-embeddings-v5-text-small`.
10. When a doc and `backend/app/main.py` disagree, follow the code and flag the doc.
