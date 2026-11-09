# Endpoint Contract Template: `/accept-connection`

**Status:** Draft; route and schema are subject to merge. **TBD** means the decision is intentionally open.

## Purpose and actor

Allow the recipient of a connection request to accept it. The draft product contract says acceptance finalizes the connection and may expose LinkedIn/email and share a resume; the exact consent and disclosure rules are **TBD**.

## Request

- HTTP method and content type: **TBD**
- Conference scope identifier: **TBD**
- Accepting attendee identity/token mechanism: **TBD**
- Connection/request identifier: **TBD**
- Explicit contact/resume sharing choices, if separately consented: **TBD**

## Response

- Status code and response schema: **TBD**
- Final connection state: **TBD**
- Which contact fields or resume access are returned, to whom, and when: **TBD**

## Validation and errors

- Verify the caller is the intended recipient and that the request belongs to the same conference.
- Already accepted, withdrawn, expired, missing, or unauthorized request behavior: **TBD**.
- Error statuses, concurrency handling, and idempotency: **TBD**.

## Side effects and Elasticsearch

- Read and update the request/connection state using the agreed model in [`../elasticsearch.md`](../elasticsearch.md).
- Apply only the sharing permissions explicitly defined by the final consent model. Acceptance alone must not imply resume sharing unless the product decision says so.
- Ensure contact information and resume access are limited to the connected parties and remain conference-scoped.
- Atomicity and access-control enforcement: **TBD**.

## Observability

Trace the state transition and Elasticsearch operations. Never place contact information, bio text, or resume content in logs or span attributes.
