# Endpoint Contract Template: `/request-connection`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

## Purpose and actor

Allow an attendee to request a connection with another attendee in the same conference.

## Request

- HTTP method and content type: **TBD**
- Conference scope identifier: **TBD**
- Requester identity/token mechanism: **TBD**
- Recipient identifier: **TBD**
- Optional message or context: **TBD**

## Response

- Status code and response schema: **TBD**
- Request/connection identifier and state: **TBD**
- Whether the recipient is notified and by what channel: **TBD**

## Validation and errors

- Confirm both attendees belong to this conference and that discovery/connection eligibility is satisfied: exact policy **TBD**.
- Self-requests, unknown recipient, duplicate/pending requests, blocked users, and already-accepted connections: behavior **TBD**.
- Error statuses and retry/idempotency behavior: **TBD**.

## Side effects and Elasticsearch

- Read conference-scoped attendee and connection state; enforce the finalized discovery opt-in rule.
- Write a pending request or update the chosen connection representation described in [`../elasticsearch.md`](../elasticsearch.md).
- Do not disclose email, LinkedIn, or resume content as a result of a request. Disclosure follows `/accept-connection` and the finalized sharing policy.
- Index/mapping, concurrency control, and atomicity: **TBD**.

## Observability

Trace the endpoint and Elasticsearch reads/writes. Use safe identifiers and state/result attributes; do not record message content or private contact data.
