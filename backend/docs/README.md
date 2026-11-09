# Backend API and Elasticsearch Documentation

These documents describe the implemented organizer schedule flow and the planned attendee flows. Organizer API choices are finalized below; attendee route and privacy decisions remain **TBD**.

## User flows

- **Organizer:** submit a schedule URL or file for extraction, review the proposed schedule, then confirm it and receive attendee join materials (link and QR code).
- **Attendee:** join a conference without creating an account, provide a name and bio, optionally provide blockout times and opt in to discovery, then receive recommendations.
- **Connection:** attendees can request to connect. Contact details and any resume sharing become available only after the recipient accepts, subject to the final sharing policy (**TBD**).

All conference data and attendee interactions are scoped to one conference. The mechanism for identifying that conference on each request (for example, a conference ID, join token, or another value) is **TBD**. Do not assume a global attendee identity or cross-conference profile.

## Draft endpoint contracts

| Operation | Actor | Elasticsearch touchpoints |
|---|---|---|
| [`/save-user-data`](endpoints/save-user-data.md) | Attendee | Save conference-scoped attendee data; read talks and eligible attendees for recommendations. |
| [`/request-connection`](endpoints/request-connection.md) | Attendee | Check conference-scoped discovery/connection eligibility and record a request. |
| [`/accept-connection`](endpoints/accept-connection.md) | Attendee | Update connection state; enable approved contact or resume sharing. |
| [`/upload-schedule`](endpoints/upload-schedule.md) | Organizer | Parse input with OpenRouter and persist a conference-scoped draft in Elasticsearch. |
| [`/confirm-schedule`](endpoints/confirm-schedule.md) | Organizer | Publish talks to Elasticsearch, switch the conference's active schedule, and return join link and QR code. |

Organizer endpoints require `Authorization: Bearer <ORGANIZER_API_KEY>`. `conference_id` scopes drafts, schedules and attendee join links. Drafts expire after `SCHEDULE_DRAFT_TTL_HOURS` (24 by default). The API is served by `backend.app.main:app`; see [SETUP.md](../../SETUP.md) for local Kubernetes deployment.

## Elasticsearch implementation and remaining template

See [`elasticsearch.md`](elasticsearch.md) for candidate indices, mapping and document templates, and query/read/write behavior. These are planning prompts, not a finalized schema or query plan.

## Completion checklist

- [x] Confirm organizer route names, HTTP methods, bearer authorization, and request/response schemas.
- [x] Define conference identification and scope organizer reads/writes to it.
- [x] Define organizer request validation and upload limits.
- [x] Define organizer schedule validation, errors, idempotency, and retry behavior.
- [ ] Decide opt-in, connection acceptance, contact disclosure, and resume-sharing rules.
- [ ] Finalize attendee Elasticsearch mappings and query/recommendation strategy.
- [x] Document schedule upload limits, supported formats, parser failures, and draft retention behavior.
- [x] Instrument organizer endpoints, Elasticsearch operations, and OpenRouter extraction with spans and metrics.
- [ ] Review accessibility and privacy implications for any user-facing behavior.
- [x] Keep organizer API documentation aligned with the implementation and frontend contract.
