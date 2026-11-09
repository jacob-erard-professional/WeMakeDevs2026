# FastAPI integration

Use this table to discuss UI needs. The paths come from the initial frontend brief. The [backend draft](../../backend/docs/README.md) uses different routes for some operations. Reconcile both with the implemented FastAPI OpenAPI schema before adding an HTTP adapter.

| UI operation | Initial endpoint sketch |
| --- | --- |
| Import schedule and preview warnings | `POST /conferences/import` |
| Confirm edited talks and receive join link | `POST /conferences/import/{id}/confirm` |
| Edit a published talk | `PATCH /conferences/{id}/talks/{talk_id}` |
| Read organizer insights | `GET /conferences/{id}/insights` |
| Resolve a conference join link | `GET /conferences/{slug}` |
| Save attendee profile | `POST /conferences/{id}/profiles` |
| Get recommended talks | `GET /conferences/{id}/talks/recommend?profile_id=…` |
| Get the proposed schedule | `GET /conferences/{id}/schedules?profile_id=…` — returns up to three relevance-weighted, non-overlapping options |
| Refresh recommended people | `GET /conferences/{id}/people/recommend?profile_id=…` |
| Request a connection | `POST /conferences/{id}/connections` |

## Confirm before wiring

- **Identity and authorization.** Confirm how a slug resolves to an ID, how attendee sessions prove ownership of a profile, and how organizer access is granted without bundling an admin key. Confirm whether join links carry a secret.
- **Inputs and errors.** Confirm supported import and resume formats, size limits, multipart fields, LinkedIn validation, unavailable time ranges, validation error shapes, and which writes support idempotency.
- **Recommendations.** Confirm talk and person IDs, safe explanation fields, empty results, refresh semantics, and schedule overlap and timezone rules.
- **Privacy and connections.** Confirm discovery opt-in, the precise meaning and audience of public resume visibility, connection request and acceptance states, and who can read each field at each stage. A profile ID by itself grants no access.
## Same-origin `/api` on the hosted web build

On the cluster the web build is served by nginx (`frontend/Dockerfile`, `frontend/nginx.conf`) behind the public URL, and the same nginx proxies `/api/*` to the backend Service with the prefix stripped: `/api/health` reaches FastAPI's `/health`. The HTTP adapter should build URLs from `API_BASE_URL` in `src/apiBase.ts` (default `/api`, overridable at build time with `EXPO_PUBLIC_API_URL`), so web needs no CORS and native builds point the same code at an absolute URL.

- **Transport.** Confirm the development API URL, web CORS, native reachability, authentication transport, and telemetry propagation. Map response shapes at the data boundary and use timeouts and actionable errors.

## Backend handoff for the conference experience

- **Public attendee links already work.** The web route `/join/{conference_id}` calls `GET /join/{conference_id}` for a published schedule. The frontend keeps that URL on check-in so reloads, copied links, and QR scans can resolve the same event. Verify the public frontend origin in `PUBLIC_BASE_URL` (API response) and `EXPO_PUBLIC_SITE_URL` (frontend link generation) for each deployment. A link contains the public conference ID only. If we want the HTTPS link to open an installed app directly, coordinate iOS associated domains and Android App Links on that same host. Browser check-in is the current default.
- **Persist event details.** Extend `POST /conferences` and the public join response with optional date range, IANA timezone, venue, and description, plus an organizer-authorized update path. For now the frontend keeps date, venue, and description in the organizer session. Time display and structured text import use America/Denver.
- **Suggest details during import.** Return optional event detail suggestions with the parsed talks and warnings for URL and file sources. Keep suggestions editable and let organizers confirm them before publication. Existing structured text input converts a single day of rows to the confirmed talk format locally. Free-form or multi-day pasted text would benefit from a third mutually exclusive `text` input on `POST /upload-schedule`.
- **Archive lookup is already available.** The attendee schedule calls `GET /conferences/{conference_id}/talks/{talk_id}/related-archive` with the conference-scoped attendee bearer token. Confirm whether unregistered attendees should eventually see related talks. The current flow asks them to finish their profile and returns them to the selected talk.
