# Endpoint Contract Template: `/confirm-schedule`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

## Implemented behavior (as of 2026-11-09)

The platform gateway kills every request at 15 s and `semantic_text` embeds roughly 50 talks per
3.4 s, so the write cannot finish inside one request for a real conference.

- `POST /confirm-schedule` validates and normalizes synchronously (422 on bad input, 401 without the
  organizer token), writes `schedule_status=indexing` on the conference doc, and then:
  - `<= SYNC_TALK_LIMIT` (100) talks: indexes inline and returns `"status": "ready"`;
  - more talks: schedules the bulk index as a background task and returns `"status": "indexing"`.
- Response: `conference_id`, `talk_count`, `status`, `join_url`, `qr_code_data_url`.
- The stale-talk `delete_by_query` runs only after every bulk batch succeeded; a failure leaves the
  previous schedule intact and sets `schedule_status=failed` with `schedule_error`.
- Progress lives on the `conferences` doc (`schedule_status`, `schedule_talk_count`,
  `schedule_indexed_count`, `schedule_error`, `schedule_updated_at`) and is public via
  `GET /conferences/{conference_id}/schedule-status`; `GET /join/{conference_id}` also returns
  `schedule_status`, `schedule_error`, the indexed/total counts and `talk_count`, and no longer
  404s while indexing (name + empty `talks` + status). An `indexing` whose `schedule_updated_at`
  is older than 120 s is reported as `failed` (job died with its pod); re-confirming repairs it.
- Limit: the per-conference lock is in-process; with two replicas, concurrent confirms for one
  conference landing on different pods can still overlap on the stale delete.

## Purpose and actor

Allow an authorized organizer to confirm the reviewed, parsed schedule. Persist confirmed sessions so attendees can receive recommendations. Return the attendee join link and QR code described by the product flow; exact payload and generation mechanism are **TBD**.

## Request

- HTTP method and content type: **TBD**
- Conference scope and organizer authorization: **TBD**
- Draft identifier or reviewed schedule payload: **TBD**
- Organizer edits and required fields: **TBD**
- Confirmation/replacement semantics for an existing schedule: **TBD**

## Response

- Status code and schema: **TBD**
- Confirmation identifier/state: **TBD**
- Join link and QR representation (URL, image, or encoded value): **TBD**
- Partial success behavior if schedule storage succeeds but QR generation fails: **TBD**

## Validation and errors

- Validate conference and organizer authorization, schedule structure, times, and required session data: exact rules **TBD**.
- Invalid or expired draft, duplicate sessions, conflicting times, Elasticsearch unavailable, and QR generation failure behavior: **TBD**.
- Idempotency and retry semantics: **TBD**.

## Side effects and Elasticsearch

- Write the confirmed schedule to the agreed conference-scoped talk model in [`../elasticsearch.md`](../elasticsearch.md).
- Ensure attendee talk search and recommendations read only confirmed schedule records.
- Define duplicate detection, replacement/merge behavior, and atomic publication so attendees do not see a partial schedule (**TBD**).
- Store schedule times as instants in UTC; display timezone policy is **TBD**.

## Observability

Trace validation, Elasticsearch writes, and join/QR generation. Record duration and safe document/result counts; do not log uploaded source documents or credentials embedded in schedule URLs.
