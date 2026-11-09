# Endpoint Contract Template: `/confirm-schedule`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

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
