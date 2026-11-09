# Vector matching spec: people, talks and the archive

Spec for the backend (`backend/app/main.py` on the `backend` branch). Everything below was run against the shared Elastic Cloud project on 2026-11-09 using throwaway indices and fake attendees; results are in [Test results](#test-results). Connection details are in [elasticsearch-connection.md](elasticsearch-connection.md).

All text fields are embedded with the same model, `.jina-embeddings-v5-text-small` (Elastic-hosted, always on, no cold start). Because people and talks live in **one vector space**, a person's profile can query talks, and a talk's abstract can query people.

## What this replaces

Today `recommend_talks` returns every talk in the conference (filter only, then drops blockout overlaps in Python), and `recommend_attendees` returns any opted-in attendee (filter only). Nothing is ranked by relevance. The queries below rank them.

## Indices

| Index | Owner | Contents |
|---|---|---|
| `attendees` | backend | one doc per attendee per conference, `_id` = `{conference_id}:{attendee_id}` |
| `talks` | backend | the confirmed live schedule, `_id` = `{conference_id}:{talk_id}` |
| `talks-archive` | read-only | 24,691 past KubeCon + PyVideo talks (alias of `talks-jina`). Don't write to it. |

Create `attendees` and `talks` with these mappings at startup if they don't exist (`es.indices.exists` → `es.indices.create`). Don't let the first write create them with dynamic mapping: you'd get no vectors and no strict checking. On Serverless don't pass shard, replica or refresh settings.

### `attendees`

```python
ATTENDEES = {
    "settings": {"analysis": {"normalizer": {"lower": {"type": "custom", "filter": ["lowercase", "asciifolding"]}}}},
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "conference_id": {"type": "keyword"},
            "attendee_id": {"type": "keyword"},
            "name": {"type": "text"},
            "headline": {"type": "text"},            # e.g. "SRE at a fintech"
            "bio": {"type": "text"},
            "interests": {"type": "keyword", "normalizer": "lower"},
            "skills": {"type": "keyword", "normalizer": "lower"},
            "working_on": {"type": "text"},
            "profile": {"type": "semantic_text", "inference_id": ".jina-embeddings-v5-text-small"},
            "looking_for": {"type": "semantic_text", "inference_id": ".jina-embeddings-v5-text-small"},
            "can_help_with": {"type": "semantic_text", "inference_id": ".jina-embeddings-v5-text-small"},
            "resume_text": {"type": "semantic_text", "inference_id": ".jina-embeddings-v5-text-small"},
            "discovery_opt_in": {"type": "boolean"},
            "blockout_times": {"properties": {"start_time": {"type": "date"}, "end_time": {"type": "date"}}},
            "access_token_sha256": {"type": "keyword", "index": False, "doc_values": False},
            "updated_at": {"type": "date"},
        },
    },
}
```

New profile fields for the API and `ProfileForm.tsx`: `headline`, `interests`, `skills`, `working_on`, `looking_for` ("I'm looking for…"), `can_help_with` ("I can help with…"). All optional; matching gets better the more people fill in.

`profile` is **built by the backend**, not sent by the client:

```python
def profile_text(p) -> str:
    parts = [p.headline, p.bio,
             f"Working on: {p.working_on}" if p.working_on else "",
             f"Interests: {', '.join(p.interests)}" if p.interests else "",
             f"Skills: {', '.join(p.skills)}" if p.skills else ""]
    return ". ".join(x for x in parts if x)
```

`resume_text`: extract text from the uploaded PDF/DOCX/TXT in the backend (e.g. `pypdf`, `python-docx`) and store only the text. Don't store the file as base64 in Elasticsearch (`resume_asset` today): it bloats every attendee doc and every read.

`access_token_sha256`: store `hashlib.sha256(token.encode()).hexdigest()` and compare with `hmac.compare_digest`. Today the raw `access_token` sits in the attendee doc. It's in `_source`, so any query that returns `_source` returns it.

### `talks`

```python
TALKS = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "conference_id": {"type": "keyword"},
            "talk_id": {"type": "keyword"},
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "speakers": {"type": "keyword"},
            "room": {"type": "keyword"},
            "track": {"type": "keyword"},
            "start_time": {"type": "date"},
            "end_time": {"type": "date"},
            "confirmed": {"type": "boolean"},
            "semantic_content": {"type": "semantic_text", "inference_id": ".jina-embeddings-v5-text-small"},
        },
    },
}
```

In `confirm_schedule`, set `semantic_content = f"{title}\n\n{abstract}"` on each talk before the bulk. With `dynamic: strict`, any extra key the schedule parser emits is rejected, so either add it to the mapping or drop it before indexing.

**Write latency:** `semantic_text` embeds on write, so indexing an attendee or a schedule takes about a second longer. Keep `refresh="wait_for"` where the response needs to include the new doc.

## Privacy rules (enforce in code)

1. **Every query on `attendees` sets `_source` explicitly** to `attendee_id`, `name`, `headline`. Tested: without it, `resume_text` comes back in `_source`. Never return `bio`, `resume_text`, `looking_for` or `can_help_with` of *another* attendee except through the highlight rules below and the accept-connection flow.
2. Highlight only `profile` and `can_help_with`. **Never highlight `resume_text`**: highlights return the matching passage verbatim.
3. Eligible candidates are always: same `conference_id`, `discovery_opt_in: true`, not the requester.
4. No profile, bio or resume text in logs or span attributes. Put counts and IDs on spans (`match.candidates`, `match.top_score`).

## Queries

Shared helpers:

```python
SAFE_SOURCE = {"includes": ["attendee_id", "name", "headline"]}
JINA = ".jina-embeddings-v5-text-small"

def eligible(conference_id: str, me: str) -> dict:
    return {"filter": [{"term": {"conference_id": conference_id}}, {"term": {"discovery_opt_in": True}}],
            "must_not": [{"term": {"attendee_id": me}}]}

def semantic(field: str, text: str, conference_id: str, me: str) -> dict:
    return {"bool": {"must": [{"semantic": {"field": field, "query": text}}], **eligible(conference_id, me)}}
```

### Q1. Similar people

Hybrid: profile meaning + resume meaning + shared skills/interests, merged with RRF.

```python
es.search(index="attendees", size=10, source=SAFE_SOURCE,
    retriever={"rrf": {"rank_window_size": 50, "retrievers": [
        {"standard": {"query": semantic("profile", my_profile, cid, me)}},
        {"standard": {"query": semantic("resume_text", my_profile, cid, me)}},
        {"standard": {"query": {"bool": {"should": [{"terms": {"skills": my_skills}}, {"terms": {"interests": my_interests}}],
                                         "minimum_should_match": 1, **eligible(cid, me)}}}},
    ]}},
    highlight={"fields": {"profile": {"type": "semantic", "number_of_fragments": 1}}})
```

If the person has no skills or interests, drop the third retriever (an empty `terms` list is an error). Each hit's `highlight.profile[0]` is the passage of *their* profile that best matched: show it as "Why: …".

### Q2. Two-sided matchmaking ("you two should meet")

Who can help with what I'm looking for (weight 0.7), plus who is looking for what I can help with (0.3). Use `linear` with `minmax`, not RRF. Tested: RRF only looks at ranks and put the wrong person first. `linear` scored the right match 0.74 vs 0.49 for the next one.

```python
es.search(index="attendees", size=10, source=SAFE_SOURCE,
    retriever={"linear": {"rank_window_size": 50, "normalizer": "minmax", "retrievers": [
        {"retriever": {"standard": {"query": semantic("can_help_with", my_looking_for, cid, me)}}, "weight": 0.7},
        {"retriever": {"standard": {"query": semantic("looking_for", my_can_help_with, cid, me)}}, "weight": 0.3},
    ]}},
    highlight={"fields": {"can_help_with": {"type": "semantic", "number_of_fragments": 1}}})
```

Skip whichever retriever's input is empty. `highlight.can_help_with[0]` is what they can help with: "Ben can help with: OpenTelemetry instrumentation and collector pipelines".

### Q3. Talk recommendations for a person

The attendee's profile (plus what they're looking for) queries the schedule. Blockouts are excluded **in Elasticsearch**, one `must_not` clause per blockout (a talk overlaps when it starts before the blockout ends and ends after it starts), which replaces the Python loop.

```python
es.search(index="talks", size=20, source=["talk_id", "title", "room", "start_time", "end_time"],
    query={"bool": {
        "must": [{"semantic": {"field": "semantic_content", "query": f"{my_profile} {my_looking_for}"}}],
        "filter": [{"term": {"conference_id": cid}}, {"term": {"confirmed": True}}],
        "must_not": [{"bool": {"filter": [{"range": {"start_time": {"lt": b.end_time.isoformat()}}},
                                          {"range": {"end_time": {"gt": b.start_time.isoformat()}}}]}}
                     for b in blockouts]}})
```

With an empty profile, fall back to sorting by `start_time` (no `must`).

### Q4. Who would enjoy this talk (organizers and speakers)

```python
es.search(index="attendees", size=10, source=SAFE_SOURCE,
    query={"bool": {"must": [{"semantic": {"field": "profile", "query": f"{talk['title']}. {talk['abstract']}"}}],
                    "filter": [{"term": {"conference_id": cid}}, {"term": {"discovery_opt_in": True}}]}})
```

Show organizers only counts or opted-in names, per the discovery rules.

### Q5. Past talks like this one (archive)

"Liked this session? Watch these recordings." `video_url` is set for PyVideo talks.

```python
es.search(index="talks-archive", size=5, source=["title", "conference", "year", "url", "video_url"],
    query={"semantic": {"field": "semantic_content", "query": f"{talk['title']}. {talk['abstract']}"}})
```

### Optional: reranking

Wrap any `retriever` in `text_similarity_reranker` with `inference_id: ".jina-reranker-v3.5"` for sharper top results (+~1 s). Its `rank_window_size` must be ≤ the inner retriever's. Example in elasticsearch-connection.md.

## Endpoints affected

| Endpoint | Change |
|---|---|
| `/save-user-data` | accept the new profile fields; build `profile`; extract `resume_text`; hash the token; return Q3 talks and Q1/Q2 people |
| `/confirm-schedule` | set `semantic_content`; ensure `talks` exists with the mapping |
| new `GET` recommend endpoints | the frontend's `frontend/docs/integration.md` expects `GET /conferences/{id}/talks/recommend?profile_id=…`; agree on one contract between frontend and backend |
| `/accept-connection` | unchanged: still the only path that discloses `resume_text` |

## Test results

Five fake attendees plus one opted-out, five talks, run on the cloud project:

| Query | Input | Top results | Check |
|---|---|---|---|
| Q1 similar people | Ana (SRE, OpenTelemetry, Kubernetes) | Ben (OTel maintainer), Dee, Chen, Eve | Ana and opted-out Fay excluded ✅ |
| Q2 two-sided | Ana looks for "OpenTelemetry tracing advice" | Ben 0.74, Chen 0.49, Eve 0.14 | highlight: "OpenTelemetry instrumentation and collector pipelines" ✅ |
| Q3 talk recs | Ana, blockout 19:45–20:15 | OTel tracing, Kubernetes bill, GitOps, eBPF | postmortems talk (20:00) excluded ✅ |
| Q4 reverse | eBPF runtime security talk | Chen 0.91, Ana 0.69, Ben 0.67 | ✅ |
| Q5 archive | same talk | "From Observability to Enforcement…", "eBPF + Wasm…", "Hacking GPU Observability: eBPF…" | ✅ |
| strict mapping | unknown field | `400 strict_dynamic_mapping_exception` | ✅ |
| keyword case | `skills: "Kubernetes"` vs stored `kubernetes` | 2 hits with the `lower` normalizer (0 without) | ✅ |
| `_source` leak | default `_source` | contains `resume_text` | ⚠️ why rule 1 exists |
