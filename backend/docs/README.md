# Backend API and Elasticsearch

The backend provides organizer schedule publishing and attendee discovery/connections. Elasticsearch is the sole durable data store for conferences, schedules, attendees, and connections.

## Flows

- Organizer uploads a URL or document/image to `POST /upload-schedule`, reviews the extracted JSON, then submits `POST /confirm-schedule` to publish and receive a join URL and QR code.
- Attendee uses `/save-user-data` for a profile and recommendations, then `/request-connection` and `/accept-connection` for opt-in connections.

| Endpoint | Actor | Contract |
|---|---|---|
| `/upload-schedule` | Organizer | [Upload and extract](endpoints/upload-schedule.md) |
| `/confirm-schedule` | Organizer | [Confirm and publish](endpoints/confirm-schedule.md) |
| `/save-user-data` | Attendee | [Profile and recommendations](endpoints/save-user-data.md) |
| `/request-connection` | Attendee | [Request a connection](endpoints/request-connection.md) |
| `/accept-connection` | Attendee | [Accept and share](endpoints/accept-connection.md) |

Organizer endpoints use `X-Organizer-Key` configured with `ORGANIZER_API_KEY`. Schedule extraction uses the OpenAI Responses API; configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (defaults to `gpt-4o-mini`). Elasticsearch connection settings are `ES_URL` and `ES_API_KEY`; join links use `PUBLIC_BASE_URL`. See [Elasticsearch mappings and lifecycle](elasticsearch.md).

## Run locally

```sh
cd backend
python -m pip install -e .
uvicorn app.main:app --reload
```
