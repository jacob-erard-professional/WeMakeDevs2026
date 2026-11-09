# Endpoint Contract: `/upload-schedule`

**Status:** Implemented.

## Purpose and actor

Allow an organizer to provide a schedule URL or upload a supported image/document for parsing. Return extracted schedule data for organizer review; this operation does not itself confirm the schedule.

## Request

- HTTP: `POST /upload-schedule`, `multipart/form-data`.
- Required `conference_id`; provide exactly one of `source_url` or `file`.
- Requires `Authorization: Bearer <ORGANIZER_API_KEY>`.
- URL inputs must use HTTPS, resolve only to public IP addresses, and may not redirect.
- Supported files: PDF, DOCX, PNG, JPEG, WEBP, HTML and plain text; 20 MiB default maximum.
- PDF/DOCX/text/HTML are converted to text; image inputs use OpenRouter vision extraction. Extraction timeout is 45 seconds.

## Response

- Returns `201` with `draft_id`, `conference_id`, `status: review`, and editable `title`, `timezone`, and `talks` JSON.
- The schedule includes `warnings`; timezone assumptions are flagged for review. Each talk includes `talk_id`, `title`, `abstract`, `tags`, `speaker_names`, timezone-aware `start_time` / `end_time`, and optional `room`.
- Draft expiry is returned as `expires_at`; default lifetime is 24 hours.
- Extraction is a proposal for organizer review; the API does not provide confidence scores.

## Validation and errors

- Validate authorization, file type/size, URL and parser output before returning data.
- Invalid input returns `400`/`422`; oversized upload returns `413`; extraction provider failure returns `502`; Elasticsearch failure returns `503`.
- Uploads are independent drafts; retries create a new draft.

## Side effects and Elasticsearch

- Parse input and return structured draft data for review.
- The parsed draft is stored in the Elasticsearch `schedule_drafts` index with conference scope and expiry. Raw file bytes and source URLs are not stored.
- Expired drafts are rejected at confirmation; automatic physical deletion/ILM is not yet configured.
- Do not publish talks into the confirmed searchable schedule from this endpoint.

## Observability

OpenTelemetry spans cover parsing, OpenRouter, and Elasticsearch. Metrics record endpoint success/error counts. Safe attributes include parser/model, conference ID, and talk count; uploaded contents, source URLs, and credentials are not recorded.
