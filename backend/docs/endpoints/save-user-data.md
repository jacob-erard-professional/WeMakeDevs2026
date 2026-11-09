# Endpoint Contract Template: `/save-user-data`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

## Purpose and actor

Allow an attendee to submit a name and bio and, where supported, blockout times and discovery opt-in for one conference. Return talk recommendations, conflict-free schedule options, and eligible people to meet according to the agreed product behavior (**TBD**).

## Request

- HTTP method and content type: **TBD**
- Conference scope identifier and validation: **TBD**
- Name and bio fields/limits: **TBD**
- Blockout-time schema and timezone semantics: **TBD**
- Discovery opt-in representation/default: **TBD**
- Optional file upload formats, size limits, and text extraction behavior: **TBD**
- Authentication or join-token requirements: **TBD**

## Response

- Status code and response schema: **TBD**
- Attendee identifier lifetime/scope: **TBD**
- Talk recommendation format and explanation: **TBD**
- Conflict-free schedule option format/count: **TBD**
- Discovery result eligibility and returned profile fields: **TBD**

## Validation and errors

- Validate conference scope, payload size, text, time ranges, and supported files: exact rules **TBD**.
- Error codes/statuses for invalid input, unknown conference, parser/search failure, and Elasticsearch unavailable: **TBD**.
- Retry/idempotency behavior for repeated saves: **TBD**.

## Side effects and Elasticsearch

- Write attendee data using the agreed conference-scoped document model in [`../elasticsearch.md`](../elasticsearch.md).
- Read confirmed talks for recommendation and schedule construction; exclude talks that conflict with attendee availability according to finalized time rules (**TBD**).
- Read only attendees who opted in to discovery and satisfy finalized eligibility rules (**TBD**).
- Never return another attendee's contact details or resume through this operation unless the finalized sharing rules explicitly allow it.
- Index names, mappings, query strategy, and atomicity: **TBD**.

## Observability

Trace the endpoint and Elasticsearch reads/writes. Record latency, error counts, result counts, and safe identifiers; do not record raw bios, contact details, or resume contents.
