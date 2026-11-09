# `POST /confirm-schedule`

Authorized organizers confirm the reviewed schedule and receive attendee join materials.

## Request

JSON with `conference_id` and either `draft_id` from `/upload-schedule` or a reviewed `talks` array. Each talk requires title and timezone-aware `start_time` / `end_time`; optional fields are `talk_id`, `abstract`, `tags`, `speaker_names`, and `room`. Drafts expire after 24 hours. Authentication uses `X-Organizer-Key` matching `ORGANIZER_API_KEY`.

## Response

Returns `conference_id`, `schedule_id`, `talk_count`, `join_url`, and a PNG `qr_code_data_url`. The public URL is based on `PUBLIC_BASE_URL`.

## Publication behavior

Talks are indexed in Elasticsearch with conference and schedule identifiers, timestamps normalized to UTC, and `confirmed=true`. After the complete bulk write succeeds, the conference's `active_schedule_id` pointer is updated. Attendee recommendations query only that active schedule, so replacement does not expose a partial schedule. Old schedule records remain available but inactive. Reconfirming the same draft returns its stored confirmation.

Invalid/expired drafts return `404`/`410`; invalid talk times return `422`; Elasticsearch failures return `503`. Traces cover schedule writes and pointer publication.
