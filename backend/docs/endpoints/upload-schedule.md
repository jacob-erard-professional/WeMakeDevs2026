# `POST /upload-schedule`

Authorized organizers submit one schedule source for extraction and review. This endpoint creates a 24-hour Elasticsearch draft; it does not publish talks.

## Request

- `multipart/form-data`: required `conference_id`; exactly one of `source_url` (HTTPS) or `file`.
- Organizer authentication: `X-Organizer-Key`, matching `ORGANIZER_API_KEY`.
- Maximum source size: 10 MiB. Supported media: PDF, DOCX, PNG, JPEG, WEBP, HTML, and plain text.
- URL sources must resolve to public IP addresses. Redirects are not followed.
- Extraction uses OpenAI Responses structured output with `OPENAI_MODEL` (default `gpt-4o-mini`); no source is retained in the draft.

## Response

`200` returns `draft_id`, `conference_id`, `expires_at`, and `schedule`: title, source timezone, warnings, and talks. Each talk contains title, abstract, tags, speaker names, ISO-8601 start/end timestamps, and optional room/id. Times must include an offset and end after start. Organizers should review and edit these values before confirmation.

Errors: `401` missing/invalid organizer key, `413` oversized input, `415` unsupported type, `422` invalid source or extraction, `502` OpenAI extraction failure, `503` missing OpenAI configuration or Elasticsearch outage.

## Data and observability

Drafts in `schedule_drafts` are confirmable for 24 hours, contain extracted schedule data only, and are scoped by conference. Expired documents are not automatically deleted. Spans cover extraction and Elasticsearch writes; logs include safe counts and duration, not source content or URLs.
