# Backend API and Elasticsearch Documentation

These documents are implementation templates for the conference experience backend. The route names and behavior below reflect the current draft contract and may change during merge. Anything marked **TBD** needs an implementation decision; examples are not finalized schemas.

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
| [`/upload-schedule`](endpoints/upload-schedule.md) | Organizer | Extraction is a parser workflow; whether any draft data is stored in Elasticsearch is **TBD**. |
| [`/confirm-schedule`](endpoints/confirm-schedule.md) | Organizer | Persist the reviewed schedule and make its talks available to attendee search and recommendations. |

## Elasticsearch template

See [`elasticsearch.md`](elasticsearch.md) for candidate indices, mapping and document templates, and query/read/write behavior. These are planning prompts, not a finalized schema or query plan.

## Implemented API defaults

The initial service lives in `backend/app/main.py` and runs with `uvicorn app.main:app` from the
`backend` directory. Provisional defaults fill the draft's TBDs: attendee identity is
conference-scoped and established by the first `/save-user-data` call, which returns a bearer
token; later attendee calls send `Authorization: Bearer <conference>:<attendee>:<secret>`.
Organizers send `X-Organizer-Key`, configured with `ORGANIZER_API_KEY`. `/save-user-data` accepts
JSON (including `resume_text`) or multipart form data with a JSON `profile` field and optional PDF,
TXT, or DOCX `resume` file up to 10 MiB. `/upload-schedule` accepts one URL or PDF/PNG/JPEG/WEBP
file up to 10 MiB. The parser client is an integration boundary until one is selected. Connections
require explicit sharing flags on acceptance. Elasticsearch indices are `attendees`, `connections`,
and `talks`; mappings are dynamically created. Review these defaults before production use.

Start locally:

```sh
cd backend
python -m pip install -e .
uvicorn app.main:app --reload
```

Set `ES_URL`, `ES_API_KEY`, `ORGANIZER_API_KEY`, and `PUBLIC_BASE_URL` in the environment.

## Completion checklist

- [ ] Confirm route names, HTTP methods, authentication/authorization approach, and versioning.
- [ ] Define conference identification and validate that every read and write is scoped to it.
- [ ] Fill in request and response schemas, including required/optional fields and size limits.
- [ ] Define validation, error responses, idempotency, and retry behavior.
- [ ] Decide opt-in, connection acceptance, contact disclosure, and resume-sharing rules.
- [ ] Finalize Elasticsearch indices, mappings, lifecycle, and query/recommendation strategy.
- [ ] Document upload limits, supported formats, parser failures, and draft schedule handling.
- [ ] Add tracing/logging/metrics expectations for each endpoint, Elasticsearch operation, and parser/LLM call.
- [ ] Review accessibility and privacy implications for any user-facing behavior.
- [ ] Keep API documentation aligned with the implementation and frontend contract.
