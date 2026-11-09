from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch, NotFoundError

from .config import Settings
from .observability import tracer

DRAFTS_INDEX = "schedule_drafts"
TALKS_INDEX = "talks"
CONFERENCES_INDEX = "conferences"


def create_client(settings: Settings) -> AsyncElasticsearch:
    options: dict[str, object] = {"request_timeout": 10, "max_retries": 2, "retry_on_timeout": True}
    if settings.es_api_key:
        options["api_key"] = settings.es_api_key
    return AsyncElasticsearch(settings.es_url, **options)


async def ensure_indices(client: AsyncElasticsearch) -> None:
    mappings = {
        DRAFTS_INDEX: {
            "properties": {
                "conference_id": {"type": "keyword"},
                "draft_id": {"type": "keyword"},
                "status": {"type": "keyword"},
                "created_at": {"type": "date"},
                "expires_at": {"type": "date"},
                "schedule": {"type": "object", "enabled": False},
            }
        },
        TALKS_INDEX: {
            "properties": {
                "conference_id": {"type": "keyword"},
                "schedule_id": {"type": "keyword"},
                "talk_id": {"type": "keyword"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "abstract": {"type": "text"},
                "tags": {"type": "keyword"},
                "speaker_names": {"type": "keyword"},
                "start_time": {"type": "date"},
                "end_time": {"type": "date"},
                "room": {"type": "keyword"},
            }
        },
        CONFERENCES_INDEX: {
            "properties": {
                "conference_id": {"type": "keyword"},
                "active_schedule_id": {"type": "keyword"},
                "schedule_title": {"type": "text"},
                "schedule_timezone": {"type": "keyword"},
                "talk_count": {"type": "integer"},
                "confirmed_at": {"type": "date"},
            }
        },
    }
    for name, body in mappings.items():
        with tracer.start_as_current_span("elasticsearch.ensure_index") as span:
            span.set_attribute("db.system", "elasticsearch")
            span.set_attribute("db.index", name)
            if not await client.indices.exists(index=name):
                await client.indices.create(index=name, mappings=body)


async def save_draft(client: AsyncElasticsearch, conference_id: str, draft: dict) -> None:
    with tracer.start_as_current_span("elasticsearch.save_schedule_draft") as span:
        span.set_attribute("db.system", "elasticsearch")
        span.set_attribute("db.index", DRAFTS_INDEX)
        await client.index(index=DRAFTS_INDEX, id=draft["draft_id"], document={
            "conference_id": conference_id,
            **draft,
        }, refresh="wait_for")


async def get_draft(client: AsyncElasticsearch, draft_id: str, conference_id: str) -> dict | None:
    with tracer.start_as_current_span("elasticsearch.get_schedule_draft") as span:
        span.set_attribute("db.system", "elasticsearch")
        span.set_attribute("db.index", DRAFTS_INDEX)
        try:
            result = await client.get(index=DRAFTS_INDEX, id=draft_id)
        except NotFoundError:
            return None
        source = result["_source"]
        if source.get("conference_id") != conference_id:
            return None
        return source


async def publish_schedule(
    client: AsyncElasticsearch, conference_id: str, schedule_id: str, schedule: dict
) -> None:
    actions = []
    for talk in schedule["talks"]:
        actions.append(
            {"index": {"_index": TALKS_INDEX, "_id": f"{schedule_id}:{talk['talk_id']}"}}
        )
        actions.append({
            "conference_id": conference_id,
            "schedule_id": schedule_id,
            **talk,
        })

    with tracer.start_as_current_span("elasticsearch.publish_schedule") as span:
        span.set_attribute("db.system", "elasticsearch")
        span.set_attribute("db.index", TALKS_INDEX)
        span.set_attribute("schedule.talk_count", len(schedule["talks"]))
        if actions:
            result = await client.bulk(operations=actions, refresh="wait_for")
            if result.get("errors"):
                raise RuntimeError("Elasticsearch rejected one or more talk documents")
        await client.index(
            index=CONFERENCES_INDEX,
            id=conference_id,
            document={
                "conference_id": conference_id,
                "active_schedule_id": schedule_id,
                "schedule_title": schedule["title"],
                "schedule_timezone": schedule["timezone"],
                "talk_count": len(schedule["talks"]),
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
            refresh="wait_for",
        )
