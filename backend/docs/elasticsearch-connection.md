# Connecting to Elasticsearch

The team shares one **Elastic Cloud Serverless** project (Elasticsearch project type). Nobody runs Elasticsearch locally.

| What | Value |
|---|---|
| Elasticsearch | `https://my-elasticsearch-project-ec6837.es.us-east4.gcp.elastic.cloud:443` |
| Kibana | `https://my-elasticsearch-project-ec6837.kb.us-east4.gcp.elastic.cloud` |
| Agent Builder MCP | `https://my-elasticsearch-project-ec6837.kb.us-east4.gcp.elastic.cloud/api/agent_builder/mcp` |
| Version | 9.7.0, `build_flavor: serverless` |
| Auth | API key: `Authorization: ApiKey <ES_API_KEY>` |

## 1. Credentials

Both values live in the repo-root `.env` (gitignored; get it from Jacob privately, never through git, Slack or Discord):

```sh
ES_URL=https://my-elasticsearch-project-ec6837.es.us-east4.gcp.elastic.cloud:443
ES_API_KEY=<encoded API key>
```

To make your own key instead: Kibana → **Connection details** (top right) or **Manage → API keys** → create, then copy the **encoded** value.

Check it without printing the key:

```sh
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: ApiKey $(grep -m1 '^ES_API_KEY=' .env | cut -d= -f2-)" \
  "$(grep -m1 '^ES_URL=' .env | cut -d= -f2-)/"      # 200 = works, 401 = bad key
```

Don't `source .env` in a shell: other values in it contain spaces and the shell would print part of the Dash0 token.

## 2. From Python (host)

```sh
uv add elasticsearch
uv run --env-file .env python -m app      # uv only loads .env with --env-file
```

```python
import os
from elasticsearch import Elasticsearch

es = Elasticsearch(
    os.environ["ES_URL"],
    api_key=os.environ["ES_API_KEY"],
    request_timeout=10,          # every external call needs a timeout
    retry_on_timeout=True,
    max_retries=2,
)
print(es.info()["version"]["number"])
```

The `elasticsearch` client emits OpenTelemetry spans for every request on its own once the OpenTelemetry SDK is set up (see AGENTS.md, Dash0), so Elasticsearch calls show up in Dash0 without extra code.

## 3. From pods (kind cluster)

`./scripts/dev-up.sh` turns `ES_URL` and `ES_API_KEY` from `.env` into a Secret named `elasticsearch`. Pods use the same URL as the host:

```yaml
containers:
  - name: backend
    envFrom:
      - secretRef:
          name: elasticsearch
```

Rerun `./scripts/dev-up.sh` after changing the key in `.env`.

## 4. Serverless differences

- Don't set `number_of_shards`, `number_of_replicas` or `refresh_interval`: Serverless manages them and rejects the request.
- No ML nodes to manage. Inference runs on Elastic-hosted endpoints. Endpoints on the `elastic` service (Jina, ELSER, the rerankers) are always on. Endpoints on the `elasticsearch` service (e.g. `.multilingual-e5-small-elasticsearch`) scale **down to zero**: after a quiet period the first query returns **HTTP 408 `model_deployment_timeout_exception`** for about 50 s. `talks` uses Jina, so it has no cold start.
- No cluster/node APIs (`_cluster/health`, `_nodes`, `_cat/nodes`). Use `GET /` and `GET /<index>/_count` for health checks.

## 5. The `talks-archive` index

24,691 conference talks: KubeCon + CloudNativeCon schedules (`source: kubecon`) and PyVideo talks (`source: pyvideo`), embedded with Jina by Elasticsearch on write.

`talks-archive` is an **alias** for the index `talks-jina`: past talks for reference and "similar past talks". It is read-only for the app. The backend owns a separate `talks` index for the live conference schedule (mapping in [vector-matching.md](vector-matching.md)). To change the archive's mapping or model, build a new index and move the alias (`POST /_aliases`).

| Field | Type | Notes |
|---|---|---|
| `id` | keyword | stable ID, also the document `_id` |
| `source` | keyword | `kubecon` or `pyvideo` |
| `conference` | text (+`.raw` keyword) | e.g. `KubeCon + CloudNativeCon Europe 2025` |
| `conference_id` | keyword | e.g. `kccnceu2025` |
| `year` | integer | |
| `title` | text (+`.raw` keyword) | |
| `abstract` | text | missing on ~4,200 talks |
| `speakers` | keyword | array |
| `speakers_text` | text | speakers joined, for full-text search |
| `tracks` | keyword | array |
| `room` | text | KubeCon only |
| `start`, `end` | date | KubeCon only (UTC) |
| `duration_s` | integer | |
| `language` | keyword | |
| `url`, `video_url` | keyword | schedule page / recording |
| `semantic_content` | semantic_text | title + abstract, embedded with `.jina-embeddings-v5-text-small` (1024 dims, cosine) |

The mapping is strict: indexing a field that isn't listed fails. Change the mapping on purpose, not by accident.

## 6. Queries

All of these run as `POST /talks-archive/_search`. Python: `es.search(index="talks-archive", **body)`.

**Keyword**

```json
{
  "query": { "multi_match": { "query": "ebpf security",
    "fields": ["title^3", "abstract", "speakers_text", "tracks"] } },
  "_source": ["title", "conference", "speakers", "url"]
}
```

**Semantic** (finds "something on eBPF and security" even when those words aren't in the title)

```json
{
  "query": { "semantic": { "field": "semantic_content",
    "query": "something on eBPF and security" } },
  "_source": ["title", "conference", "speakers", "url"]
}
```

**Hybrid** (keyword + semantic, merged with reciprocal rank fusion)

```json
{
  "retriever": { "rrf": { "rank_window_size": 50, "retrievers": [
    { "standard": { "query": { "multi_match": { "query": "ebpf security",
        "fields": ["title^3", "abstract", "speakers_text", "tracks"] } } } },
    { "standard": { "query": { "semantic": { "field": "semantic_content",
        "query": "ebpf security" } } } }
  ] } },
  "_source": ["title", "conference", "url"]
}
```

**Hybrid + reranking** (a hosted reranker re-scores the top hits; the reranker's `rank_window_size` must be ≤ the inner `rrf` one, which defaults to 10)

```json
{
  "retriever": { "text_similarity_reranker": {
    "retriever": { "rrf": { "rank_window_size": 50, "retrievers": [
      { "standard": { "query": { "multi_match": { "query": "ebpf security",
          "fields": ["title^3", "abstract"] } } } },
      { "standard": { "query": { "semantic": { "field": "semantic_content",
          "query": "ebpf security" } } } }
    ] } },
    "field": "semantic_content",
    "inference_id": ".jina-reranker-v3.5",
    "inference_text": "ebpf security",
    "rank_window_size": 20
  } },
  "_source": ["title", "conference", "url"]
}
```

**Filters**: add them to each retriever's query (`bool.filter`), e.g. only KubeCon 2025:

```json
{ "bool": { "must": { "semantic": { "field": "semantic_content", "query": "gitops" } },
  "filter": [ { "term": { "source": "kubecon" } }, { "term": { "year": 2025 } } ] } }
```

**Aggregations** (for dashboards and facets)

```json
{ "size": 0, "aggs": {
  "by_conference": { "terms": { "field": "conference.raw", "size": 10 } },
  "top_tracks":    { "terms": { "field": "tracks", "size": 10 } } } }
```

## 7. Hosted models

List them all with `GET /_inference/_all`. The useful ones:

| Use | Endpoint |
|---|---|
| Embeddings, Jina (what `talks-archive` and the app's indices use; organizers recommend Jina) | `.jina-embeddings-v5-text-small`, `.jina-embeddings-v3` |
| Embeddings, e5 (scales to zero, see section 4) | `.multilingual-e5-small-elasticsearch` |
| Sparse embeddings (`semantic_text` default) | `.elser-2-elastic` |
| Reranking | `.jina-reranker-v3.5`, `.rerank-v1-elasticsearch` |

A new index with a `semantic_text` field embeds documents on write; pick the endpoint with `"inference_id"` in the mapping. Embeddings for one field must all come from the same endpoint.

Tested on this project: the Jina embedding, ELSER and Jina reranker endpoints all work. The hosted **LLM** endpoints (`.anthropic-claude-*`, `.gp-llm-v2-*`, the other `completion`/`chat_completion` ones) all return **403 Forbidden** on this trial, so for RAG answers retrieve with Elasticsearch and generate with the OpenAI key from the event credits (`OPENAI_API_KEY` in `.env`).

## 8. Agents and MCP

Kibana's **Agent Builder** exposes an MCP server at `<Kibana URL>/api/agent_builder/mcp`. It has tools to search indices and run ES|QL, so Claude Code, Codex or Cursor can query `talks-archive` (and the app's `talks`/`attendees`) directly. Add it to Claude Code with the same API key:

```sh
claude mcp add --transport http elastic \
  https://my-elasticsearch-project-ec6837.kb.us-east4.gcp.elastic.cloud/api/agent_builder/mcp \
  --header "Authorization: ApiKey <ES_API_KEY>"
```

That stores the key in your Claude config, so keep it out of `.mcp.json` (which is committed).

## 9. Rules

- Elasticsearch is the single store for conference data. Don't add another database for the same records.
- Every client call has a timeout.
- Never log or print `ES_API_KEY`, and don't put user content (bios, contact details, raw uploads) in logs or span attributes.
