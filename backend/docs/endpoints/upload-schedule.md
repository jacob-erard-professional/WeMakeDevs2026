# Endpoint Contract Template: `/upload-schedule`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

## Purpose and actor

Allow an organizer to provide a schedule URL or upload a supported image/document for parsing. Return extracted schedule data for organizer review; this operation does not itself confirm the schedule.

## Request

- HTTP method and content type: **TBD** (URL, multipart upload, or both)
- Conference scope and organizer authorization: **TBD**
- Supported URL schemes/domains: **TBD**
- Supported file formats, maximum size, and number of files: **TBD**
- Parser selection, timeout, and callback/asynchronous behavior: **TBD**

## Response

- Status code and schema for extracted draft: **TBD**
- Extraction confidence, warnings, and fields needing review: **TBD**
- Draft identifier and expiry, if applicable: **TBD**

## Validation and errors

- Validate authorization, file type/size, URL and parser output before returning data.
- Malformed schedule, unsupported content, parser timeout/failure, unsafe/unreachable URL, and Elasticsearch failure behavior: **TBD**.
- Retry and duplicate-upload behavior: **TBD**.

## Side effects and Elasticsearch

- Parse input and return structured draft data for review.
- Whether the draft is persisted in Elasticsearch before confirmation is **TBD**; see the `schedule_drafts` candidate in [`../elasticsearch.md`](../elasticsearch.md).
- If the URL or source file is retained, define access controls, retention, and sensitive-data handling before implementation (**TBD**).
- Do not publish talks into the confirmed searchable schedule from this endpoint.

## Observability

Trace parsing and any Elasticsearch operations. Record parser type, duration, outcome, and safe counts; avoid logging uploaded contents, signed URLs, or sensitive query parameters.
