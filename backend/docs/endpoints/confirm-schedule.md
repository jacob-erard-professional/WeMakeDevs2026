# Endpoint Contract: `/confirm-schedule`

**Status:** Implemented.

## Purpose and actor

Allow an authorized organizer to confirm the reviewed, parsed schedule. Persist confirmed sessions so attendees can receive recommendations, and return the attendee join link and QR code.

## Request

- HTTP: `POST /confirm-schedule`, JSON body with `conference_id`, `draft_id`, and optional edited `schedule`.
- Requires `Authorization: Bearer <ORGANIZER_API_KEY>`.
- If provided, the edited schedule replaces the parsed draft and is validated before publication. Times must include timezone offsets and are normalized to UTC.
- The draft ID is also the stable schedule ID. Confirming it again is idempotent and returns the already-confirmed schedule.
- A new confirmation replaces the active schedule for that conference; the prior schedule remains stored but inactive.

## Response

- Returns `200` with `conference_id`, `schedule_id`, `status`, `talk_count`, `join_url`, and a PNG `qr_code_data_uri`.
- Join URL is `{PUBLIC_BASE_URL}/join/{conference_id}`.
- Publication is complete before QR generation and the response is returned.

## Validation and errors

- Missing/unknown draft returns `404`; expired draft returns `410`; invalid schedule returns `422`; Elasticsearch failure returns `503`.
- Talk IDs must be unique, titles non-empty, list sizes bounded, and end times later than start times. Overlapping talks are allowed because parallel sessions are valid.
- Repeating confirmation is safe; the original confirmed schedule is authoritative.

## Side effects and Elasticsearch

- Write talk documents to `talks` using conference and schedule IDs. Then atomically switch `conferences/{conference_id}.active_schedule_id`; attendee searches must resolve/filter through this active schedule pointer.
- Replaced schedule documents remain in Elasticsearch but are no longer active. Draft status changes to `confirmed` after publication.
- Store schedule times as UTC instants; the source timezone is retained on the schedule.

## Observability

OpenTelemetry spans cover validation, Elasticsearch writes, and the confirmation request; metrics record success/error. Record safe counts and IDs only; do not log schedule text or credentials.
