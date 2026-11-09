# Elasticsearch Data and Query Template

This document records Elasticsearch decisions needed for the backend. Candidate names and examples are prompts only. Mark unresolved choices **TBD** and update this document when implementation decisions are made. Elasticsearch is the single store for conference data such as talks and attendees; do not introduce another database for the same records.

## Connection and configuration

- Client/library and supported Elasticsearch version: **TBD**
- Endpoint and credential configuration: `ES_URL` and `ES_API_KEY` from `.env` (pods: the `elasticsearch` Secret). See [elasticsearch-connection.md](elasticsearch-connection.md) for the shared cloud project, the `talks` index and tested queries.
- Connection timeout, request timeout, retry policy, and startup health behavior: **TBD**
- Index creation/upgrade ownership and idempotency strategy: **TBD**

## Candidate indices

| Candidate index | Purpose | Conference scope | Status |
|---|---|---|---|
| `talks` | Confirmed sessions and searchable schedule content | Required; exact representation **TBD** | Candidate |
| `attendees` | Attendee name, bio, availability, and discovery settings | Required; document identity and privacy model **TBD** | Candidate |
| `connections` | Connection requests and accepted state, if modeled separately | Required; representation versus attendee embedding **TBD** | Candidate |
| `schedule_drafts` | Parsed but unconfirmed schedule data, if persistence is needed | Required if persisted; retention/access rules **TBD** | Candidate |
| `speakers` / `events` | Separate entities if needed by the finalized schedule model | **TBD** | Candidate |

Index names, aliases, shard/replica settings, lifecycle policies, and whether some candidate indices should be combined are **TBD**.

## Document templates

Replace placeholders after agreeing on the API schema and privacy model. These snippets are intentionally incomplete and are not ready to index.

### Talk document

```json
{
  "conference_id": "<TBD: conference scope key>",
  "talk_id": "<TBD: stable identifier>",
  "title": "<TBD>",
  "abstract": "<TBD>",
  "tags": ["<TBD>"],
  "speaker_ids": ["<TBD>"],
  "start_time": "<TBD: UTC representation>",
  "end_time": "<TBD: UTC representation>",
  "room": "<TBD>",
  "semantic_representation": "<TBD: semantic_text, vector, or other strategy>"
}
```

### Attendee document

```json
{
  "conference_id": "<TBD: conference scope key>",
  "attendee_id": "<TBD: conference-scoped identifier>",
  "name": "<TBD>",
  "bio": "<TBD>",
  "blockout_times": "<TBD: representation and timezone rules>",
  "discovery_opt_in": "<TBD: field and default>",
  "contact_details": "<TBD: storage and access policy>",
  "resume_or_bio_asset": "<TBD: whether/how any file is stored>"
}
```

Do not expose contact details or resume content to another attendee before an accepted connection and the agreed sharing permissions. Decide whether sensitive values should be stored in Elasticsearch at all; this is **TBD**.

### Connection document (if separate)

```json
{
  "conference_id": "<TBD>",
  "connection_id": "<TBD>",
  "requester_id": "<TBD>",
  "recipient_id": "<TBD>",
  "status": "<TBD: state model>",
  "sharing_permissions": "<TBD>",
  "created_at": "<TBD: UTC timestamp>",
  "updated_at": "<TBD: UTC timestamp>"
}
```

### Schedule draft document (if persisted)

```json
{
  "conference_id": "<TBD>",
  "draft_id": "<TBD>",
  "source_reference": "<TBD: avoid storing sensitive URL data unnecessarily>",
  "parsed_schedule": "<TBD>",
  "status": "<TBD: draft/review/confirmed lifecycle>",
  "created_at": "<TBD: UTC timestamp>"
}
```

## Mapping template

For each index, record:

- Field path and meaning: **TBD**
- Elasticsearch type and analyzers/normalizers: **TBD**
- Required versus optional and null/empty handling: **TBD**
- Conference scoping and identifier strategy: **TBD**
- Text search fields, boosts, synonyms, and language handling: **TBD**
- Semantic/vector field type, dimensions/model, and inference ownership: **TBD**
- Date/time format and timezone normalization (store instants in UTC; presentation timezone policy: **TBD**): **TBD**
- Privacy classification, retention, and deletion behavior: **TBD**
- Mapping versioning and migration/reindex approach: **TBD**

## Query and data flow template

| Use case | Reads | Writes | Query/consistency decisions |
|---|---|---|---|
| Confirm schedule | Existing schedule/draft state as needed | Confirmed talk documents | Duplicate detection, atomicity, replacement/merge behavior: **TBD** |
| Talk recommendations | Confirmed talks; attendee preferences/availability if stored | Optional recommendation cache or feedback | Keyword/semantic/hybrid strategy, ranking, conflict filtering: **TBD** |
| Attendee discovery | Conference attendees with discovery opt-in | Optional recommendation feedback | Eligibility, similarity inputs, exclusions, and ranking: **TBD** |
| Connection request/accept | Attendee and current connection state | Request and accepted state | Duplicate requests, concurrent acceptance, authorization, and disclosure: **TBD** |
| Schedule upload | No Elasticsearch read required by default | Draft record only if chosen | Parser output validation and draft persistence/retention: **TBD** |

For each query, document the index/alias, required conference filter, request shape, sort/ranking, pagination, timeout, expected result count, and failure behavior. All values are **TBD** until implemented.

## Operational notes

- Do not log API keys, full bios, contact details, resume contents, or raw uploaded documents.
- Add spans and useful metrics around Elasticsearch operations; avoid sensitive user content in span attributes.
- Define behavior for Elasticsearch unavailable, mapping conflict, timeout, partial results, and index migration: **TBD**.
- Define deletion and retention behavior for attendee data and unconfirmed schedule drafts: **TBD**.
