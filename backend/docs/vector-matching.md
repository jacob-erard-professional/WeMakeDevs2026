# Vector matching: people, talks and the archive

How `backend/app/main.py` and `backend/app/matching.py` rank talks and people. Everything below runs against the shared Elastic Cloud Serverless project (connection details in [elasticsearch-connection.md](elasticsearch-connection.md)) and was verified there with throwaway conference ids on 2026-11-09.

All text fields are embedded with one model, `.jina-embeddings-v5-text-small` (Elastic-hosted, always on). People and talks share one vector space, so a profile can query talks and a talk can query people.

## Indices

| Index | Owner | Contents |
|---|---|---|
| `attendees` | backend | one doc per attendee per conference, `_id` = `{conference_id}:{attendee_id}` |
| `talks` | backend | the confirmed live schedule, `_id` = `{conference_id}:{talk_id}` |
| `talks-archive` | read-only | 24,691 past KubeCon + PyVideo talks (alias of `talks-jina`). Never written. |

`attendees`, `talks` and `connections` are **aliases** over versioned physical indices (`attendees-v1`, `talks-v1`, `connections-v1`, `PHYSICAL_INDEX` in `matching.py`); the app only ever uses the alias names. At startup `ensure_indices` (retried in the background) does, per alias: alias exists → verify the live mapping against the expected one (`mapping_mismatches`: every property with the same `type`, same `inference_id` on semantic_text, no extra fields on strict indices) and fail loudly on a mismatch; a concrete legacy index with that name → delete it only if it holds 0 docs (`es_legacy_index_replaced`), otherwise refuse to start until it is reindexed; otherwise create the versioned index with its alias in one call. Every write path calls `ensure_indices_ready()` and returns 503 until setup succeeded, so a write can never create an index with dynamic mapping. A mapping change ships as `-v2` plus an alias move, never an in-place edit. No shard, replica or refresh settings (Serverless rejects them).

### `attendees` (`ATTENDEES_INDEX`, `dynamic: strict`)

| Field | Type | Notes |
|---|---|---|
| `conference_id`, `attendee_id` | keyword | |
| `name`, `bio` | text | |
| `interests` | keyword, `lower` normalizer | list, or the frontend's comma-separated string |
| `profile` | semantic_text (Jina) | **built by the backend**: `bio. Interests: a, b` |
| `resume_text` | semantic_text (Jina) | text extracted from the uploaded PDF/DOCX/TXT (`pypdf`, `python-docx`); the file itself is never stored |
| `resume_public` | boolean | stored; disclosure still only via `/accept-connection` |
| `discovery_opt_in` | boolean | |
| `blockout_times` | `{start_time, end_time}` date | |
| `email`, `linkedin_url` | keyword, `index: false` | disclosed only via `/accept-connection` |
| `access_token_sha256` | keyword, `index: false`, `doc_values: false` | SHA-256 of the attendee token, compared with `hmac.compare_digest` |
| `updated_at` | date | |

These are exactly the fields the frontend sends (`frontend/src/conference.ts`) plus what the backend derives. Empty strings, empty lists and nulls are dropped before indexing (`semantic_text` rejects empty input).

### `talks` (`TALKS_INDEX`, `dynamic: strict`)

`conference_id`, `talk_id`, `speakers`, `room`, `track` (keyword); `title`, `abstract` (text); `start_time`, `end_time` (date); `confirmed` (boolean); `semantic_content` (semantic_text, `title\n\nabstract`). `confirm_schedule` projects parser output onto this set and drops anything else.

**Write latency:** `semantic_text` embeds on write. Attendee and schedule writes use a 60 s client timeout (`es_writer`) and `refresh="wait_for"` so the next request already sees them.

## Privacy rules (enforced in code)

1. Every query on `attendees` sets `_source` to `SAFE_SOURCE = attendee_id, name`. Another attendee's `bio`, `resume_text`, `email` and `linkedin_url` are never returned by a recommendation; `/accept-connection` is the only disclosure path.
2. Highlight only `profile`. Never `resume_text`: highlights return the matching passage verbatim.
3. Candidates are always: same `conference_id`, `discovery_opt_in: true`, not the requester (`eligible()`).
4. No profile, bio or resume text in logs or span attributes; spans carry counts (`match.candidates`, `match.top_score`, `match.blockouts`).

## Queries (`backend/app/matching.py`)

### Q1. Similar people: `similar_people_query`

`linear` retriever, `normalizer: minmax`, `rank_window_size: 50`, over:

| Retriever | Weight |
|---|---|
| `semantic(profile, my_profile)` | 0.6 |
| `semantic(resume_text, my_resume_text)`, only when I uploaded a resume | 0.25 |
| `terms(interests, my_interests)`, only when non-empty | 0.15 |

Weights of skipped retrievers are redistributed proportionally (no resume: 0.8 / 0.2). One retriever left: plain `query`. Nothing to match on: no search. `linear` rather than RRF because RRF only sees ranks, so two people who each share one interest tie no matter how close their profiles are.

Each hit returns `{attendee_id, name, score, why}`; `why` is `highlight.profile[0]`, the passage of *their* profile that matched.

### Q3. Talk recommendations: `recommend_talks_query`

`semantic(semantic_content, my_profile)` filtered to `conference_id` and `confirmed: true`. Blockouts are excluded **in Elasticsearch**, one `must_not` clause per blockout (a talk overlaps when `start_time < blockout.end` and `end_time > blockout.start`). Empty profile: no `must`, sorted by `start_time`. Source: `talk_id, title, abstract, speakers, room, track, start_time, end_time` plus `score`.

### Q4. Who would enjoy this talk: `talk_audience_query`

`GET /conferences/{conference_id}/talks/{talk_id}/audience`, organizer key only. `semantic(profile, "title. abstract")` over opted-in attendees of the conference; returns `count` and safe people.

### Q5. Past talks like this one: `similar_past_talks_query`

`GET /conferences/{conference_id}/talks/{talk_id}/similar-past`, attendee token for that conference or organizer key. `semantic(semantic_content, "title. abstract")` on `talks-archive`, source `title, conference, year, url, video_url`. `video_url` is set for PyVideo talks.

### Optional: reranking

Wrap a retriever in `text_similarity_reranker` with `inference_id: ".jina-reranker-v3.5"` (+~1 s). Example in elasticsearch-connection.md.

## Endpoints

| Endpoint | Behavior |
|---|---|
| `POST /save-user-data` | accepts `interests`, `resume_public` and a PDF/DOCX/TXT `resume` upload; builds `profile`; extracts `resume_text`; hashes the token; returns Q3 `recommendations.talks` and Q1 `recommendations.attendees` |
| `POST /confirm-schedule` | strict `talks` docs with `semantic_content`; stale talks of the conference pruned after the bulk |
| `GET /conferences/{id}/talks/{talk_id}/audience` | Q4 |
| `GET /conferences/{id}/talks/{talk_id}/similar-past` | Q5 |
| `POST /accept-connection` | unchanged: the only path that discloses `resume_text`, `email`, `linkedin_url` |

## Test results

Six fake attendees (one opted out, one with a resume), five talks, on the cloud project:

| Query | Input | Top results | Check |
|---|---|---|---|
| Q1 | Ana (SRE, OpenTelemetry, Kubernetes), no resume | Ben 1.00, Dee 0.87, Eve 0.00, Chen 0.00 | Ana and opted-out Fay excluded; `why` fragments present; no ties |
| Q1 | Ana with a resume (all three retrievers) | Ben 1.00, Dee 0.64, Eve 0.00, Chen 0.00 | |
| Q3 | Ana, blockout 19:45–20:15 | OTel tracing 0.79, Kubernetes bill 0.75, GitOps 0.73, eBPF 0.67 | postmortems talk (20:00) excluded in ES |
| Q3 | empty profile | 5 talks in `start_time` order | fallback |
| Q4 | eBPF runtime security talk | Chen 0.86, Ben 0.69, Ana 0.67 | 401 without organizer key |
| Q5 | same talk | "From Observability to Enforcement…", "eBPF + Wasm…", "Seccomp and eBPF…" | 401 without auth |
| privacy | all recommendation responses | no `resume_text`, token, email, linkedin or bio | resume text appeared only in `/accept-connection` with `share_resume` |
| strict mapping | unknown parser key on a talk | dropped before indexing | |
