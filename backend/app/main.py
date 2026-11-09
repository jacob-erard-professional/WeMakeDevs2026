"""Conference attendee and organizer API. Elasticsearch is the durable data store."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import qrcode
from elasticsearch import ApiError, Elasticsearch, NotFoundError
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, HttpUrl, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as FormUploadFile

from app.matching import (
    ATTENDEES_INDEX,
    TALKS_INDEX,
    extract_resume_text,
    person_hit,
    profile_text,
    recommend_talks_query,
    similar_past_talks_query,
    similar_people_query,
    split_interests,
    talk_audience_query,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("conference_api")

T = TypeVar("T")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")
ORGANIZER_API_KEY = os.getenv("ORGANIZER_API_KEY", "")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Even on purpose: bulk payloads are [action, document] pairs and a batch must never split one.
BULK_BATCH_SIZE = 500
# semantic_text embeds on write: attendee and schedule writes take seconds, not milliseconds.
SEMANTIC_WRITE_TIMEOUT = 60
es = (
    Elasticsearch(ES_URL, api_key=ES_API_KEY, request_timeout=10)
    if ES_API_KEY
    else Elasticsearch(ES_URL, request_timeout=10)
)
es_writer = es.options(request_timeout=SEMANTIC_WRITE_TIMEOUT)


# --- OpenTelemetry -----------------------------------------------------------------------------


def configure_telemetry() -> None:
    """Install OTLP exporters from the standard OTEL_* env vars. No endpoint means no-op."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        logger.info("otel_disabled reason=OTEL_EXPORTER_OTLP_ENDPOINT_unset")
        return
    # Resource.create() reads OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES; the exporters read
    # OTEL_EXPORTER_OTLP_ENDPOINT / _HEADERS / _PROTOCOL.
    resource = Resource.create()
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
    )
    logger.info("otel_enabled service=%s", os.getenv("OTEL_SERVICE_NAME", "unknown_service"))


configure_telemetry()
tracer = trace.get_tracer("conference_api")


# --- Elasticsearch indices -------------------------------------------------------------------

_ID = {"type": "keyword"}
_DATE = {"type": "date"}
_TEXT = {"type": "text"}
_BOOL = {"type": "boolean"}

# `talks` and `attendees` (strict, semantic_text) live in app.matching next to their queries.
# Serverless rejects shard/replica/refresh settings, so only the analysis block is passed.
# `talks-archive` is read-only and not ours.
INDEX_BODIES: dict[str, dict[str, Any]] = {
    "talks": TALKS_INDEX,
    "attendees": ATTENDEES_INDEX,
    "connections": {
        "mappings": {
            "dynamic": True,
            "properties": {
                "conference_id": _ID,
                "connection_id": _ID,
                "requester_id": _ID,
                "recipient_id": _ID,
                "status": _ID,
                "message": _TEXT,
                "share_email": _BOOL,
                "share_linkedin": _BOOL,
                "share_resume": _BOOL,
                "created_at": _DATE,
                "updated_at": _DATE,
            },
        },
    },
}
TALK_FIELDS = set(INDEX_BODIES["talks"]["mappings"]["properties"])
ATTENDEE_FIELDS = set(INDEX_BODIES["attendees"]["mappings"]["properties"])

_indices_ready = False
INDEX_RETRY_MAX_SECONDS = 60.0


def ensure_indices() -> None:
    """Create each index with its explicit body if it does not exist yet (idempotent).

    Raises on any failure; `_indices_ready` flips to True only when every index is confirmed.
    """
    global _indices_ready
    if _indices_ready:
        return
    for index, body in INDEX_BODIES.items():
        with tracer.start_as_current_span("ensure_index") as span:
            span.set_attribute("db.system", "elasticsearch")
            span.set_attribute("db.elasticsearch.index", index)
            if es.indices.exists(index=index):
                continue
            try:
                es.indices.create(index=index, **body)
            except ApiError as exc:
                if exc.error != "resource_already_exists_exception":  # lost a create race
                    raise
            logger.info("es_index_created index=%s", index)
    _indices_ready = True


async def ensure_indices_ready() -> None:
    """Gate for every write path: a write must never create an index with dynamic mapping."""
    if _indices_ready:
        return
    try:
        await run_in_threadpool(ensure_indices)
    except Exception:
        logger.exception("es_index_setup_failed outcome=write_rejected")
        raise HTTPException(503, "Conference data store is not initialized") from None


async def retry_index_setup() -> None:
    """Background: keep retrying index creation with capped exponential backoff until it works."""
    delay = 1.0
    while not _indices_ready:
        try:
            await run_in_threadpool(ensure_indices)
        except Exception as exc:
            logger.warning("es_index_setup_retry in=%.0fs error=%s", delay, type(exc).__name__)
            await asyncio.sleep(delay)
            delay = min(delay * 2, INDEX_RETRY_MAX_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await run_in_threadpool(ensure_indices)
    except Exception:  # noqa: BLE001 - startup must survive an unreachable data store
        logger.exception("es_index_setup_failed; retrying in background so /health stays reachable")
    retry_task = asyncio.create_task(retry_index_setup())
    try:
        yield
    finally:
        retry_task.cancel()


# Behind the public nginx the API is under /api (prefix stripped); ROOT_PATH lets /docs find
# openapi.json there.
app = FastAPI(
    title="Conference API", version="0.1.0", lifespan=lifespan, root_path=os.getenv("ROOT_PATH", "")
)
FastAPIInstrumentor.instrument_app(app)


# --- Models ------------------------------------------------------------------------------------


class Blockout(BaseModel):
    start_time: datetime
    end_time: datetime


class SaveUserData(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    linkedin_url: HttpUrl | None = None
    bio: str = Field(default="", max_length=10_000)
    # A list, or the frontend's comma-separated string ("ebpf, kubernetes").
    interests: list[str] = Field(default_factory=list, max_length=50)
    blockout_times: list[Blockout] = Field(default_factory=list, max_length=100)
    discovery_opt_in: bool = False
    resume_text: str | None = Field(default=None, max_length=50_000)
    resume_public: bool = False

    @field_validator("interests", mode="before")
    @classmethod
    def _split_interests(cls, value: Any) -> list[str]:
        return split_interests(value)


class ConnectionRequest(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    recipient_id: str = Field(min_length=1, max_length=128)
    message: str | None = Field(default=None, max_length=1000)


class AcceptRequest(BaseModel):
    conference_id: str
    connection_id: str
    share_email: bool = False
    share_linkedin: bool = False
    share_resume: bool = False


class ConfirmSchedule(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    talks: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


# --- Elasticsearch access ----------------------------------------------------------------------


async def es_call(operation: str, fn: Callable[[], T], **attributes: Any) -> T:
    """Run a blocking Elasticsearch call off the event loop inside a span.

    NotFoundError -> 404, any other failure -> 503. Attributes must not contain user content.
    """
    with tracer.start_as_current_span(operation) as span:
        span.set_attribute("db.system", "elasticsearch")
        span.set_attribute("db.operation", operation)
        for key, value in attributes.items():
            span.set_attribute(key, value)
        try:
            return await run_in_threadpool(fn)
        except NotFoundError as exc:
            span.set_status(Status(StatusCode.ERROR, "not_found"))
            raise HTTPException(404, "Not found") from exc
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            logger.exception("es_operation=%s outcome=error", operation)
            raise HTTPException(503, "Conference data store unavailable") from None


async def attendee_claim(
    authorization: str | None = Header(default=None),
) -> tuple[str, str] | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        conference_id, attendee_id, token = authorization[7:].split(":", 2)
    except ValueError as exc:
        raise HTTPException(401, "Invalid attendee token") from exc
    with tracer.start_as_current_span("read_attendee_claim") as span:
        span.set_attribute("db.system", "elasticsearch")
        try:
            doc = await run_in_threadpool(
                lambda: es.get(index="attendees", id=f"{conference_id}:{attendee_id}")
            )
        except NotFoundError as exc:
            raise HTTPException(401, "Invalid attendee token") from exc
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            logger.exception("es_operation=read_attendee_claim outcome=error")
            raise HTTPException(503, "Conference data store unavailable") from None
    presented = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(doc["_source"].get("access_token_sha256", ""), presented):
        raise HTTPException(401, "Invalid attendee token")
    return conference_id, attendee_id


async def require_conference_access(
    conference_id: str,
    identity: tuple[str, str] | None = Depends(attendee_claim),
    x_organizer_key: str | None = Header(default=None),
) -> None:
    """An attendee token for this conference, or the organizer key."""
    if identity and identity[0] == conference_id:
        return
    if (
        ORGANIZER_API_KEY
        and x_organizer_key
        and secrets.compare_digest(x_organizer_key, ORGANIZER_API_KEY)
    ):
        return
    raise HTTPException(401, "Valid attendee token for this conference or organizer key required")


def require_organizer(x_organizer_key: str | None = Header(default=None)) -> None:
    if not ORGANIZER_API_KEY:
        raise HTTPException(503, "Organizer authorization is not configured")
    if not x_organizer_key or not secrets.compare_digest(x_organizer_key, ORGANIZER_API_KEY):
        raise HTTPException(401, "Organizer authorization required")


# --- Routes ------------------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/save-user-data")
async def save_user_data(
    request: Request, identity: tuple[str, str] | None = Depends(attendee_claim)
) -> dict[str, Any]:
    await ensure_indices_ready()
    uploaded_resume_text: str | None = None
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        try:
            payload = SaveUserData.model_validate_json(str(form.get("profile", "{}")))
        except ValueError as exc:
            raise HTTPException(
                422, "Multipart requests require a valid JSON 'profile' field"
            ) from exc
        upload = form.get("resume")
        # request.form() yields starlette's UploadFile, not fastapi's subclass.
        if isinstance(upload, FormUploadFile):
            # Spec: store extracted text only, never the file.
            if upload.content_type not in {
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }:
                raise HTTPException(415, "Resume must be PDF, plain text, or DOCX")
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Resume exceeds 10 MiB")
            try:
                uploaded_resume_text = await run_in_threadpool(
                    extract_resume_text, content, upload.content_type
                )
            except Exception as exc:  # noqa: BLE001 - parser libraries raise many types
                raise HTTPException(422, "Resume file could not be read") from exc
            uploaded_resume_text = uploaded_resume_text[:50_000]
    else:
        try:
            payload = SaveUserData.model_validate(await request.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, "Request body must be valid profile JSON") from exc
    if identity and identity[0] != payload.conference_id:
        raise HTTPException(403, "Attendee token belongs to another conference")
    attendee_id = identity[1] if identity else str(uuid4())
    token = None if identity else secrets.token_urlsafe(32)
    for slot in payload.blockout_times:
        if (
            slot.start_time.tzinfo is None
            or slot.end_time.tzinfo is None
            or slot.end_time <= slot.start_time
        ):
            raise HTTPException(
                422, "Blockout times must be timezone-aware and have end after start"
            )
    doc = payload.model_dump(mode="json") | {
        "attendee_id": attendee_id,
        "profile": profile_text(bio=payload.bio, interests=payload.interests),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if uploaded_resume_text:
        doc["resume_text"] = uploaded_resume_text
    # Strict mapping: drop empty optionals and anything the mapping does not know.
    doc = {k: v for k, v in doc.items() if k in ATTENDEE_FIELDS and v not in (None, "", [])}
    attendee_doc_id = f"{payload.conference_id}:{attendee_id}"
    if token:
        doc["access_token_sha256"] = hashlib.sha256(token.encode()).hexdigest()
    elif identity:
        old = await es_call(
            "read_attendee", lambda: es.get(index="attendees", id=attendee_doc_id)["_source"]
        )
        doc["access_token_sha256"] = old["access_token_sha256"]
    # wait_for: the next attendee's people matches should already see this profile.
    await es_call(
        "save_attendee",
        lambda: es_writer.index(
            index="attendees", id=attendee_doc_id, document=doc, refresh="wait_for"
        ),
    )
    blockouts = [(b.start_time.isoformat(), b.end_time.isoformat()) for b in payload.blockout_times]
    talks_query = recommend_talks_query(payload.conference_id, doc.get("profile", ""), blockouts)
    talk_hits = await es_call(
        "recommend_talks",
        lambda: es.search(**talks_query)["hits"]["hits"],
        **{"db.elasticsearch.index": "talks", "match.blockouts": len(blockouts)},
    )
    recommendations = [hit["_source"] | {"score": hit.get("_score")} for hit in talk_hits]
    users: list[dict[str, Any]] = []
    if payload.discovery_opt_in:
        users = await match_people(
            "recommend_attendees",
            similar_people_query(
                payload.conference_id,
                attendee_id,
                doc.get("profile", ""),
                payload.interests,
                doc.get("resume_text", ""),
            ),
        )
    result: dict[str, Any] = {
        "attendee_id": attendee_id,
        "recommendations": {"talks": recommendations, "attendees": users},
    }
    if token:
        result["attendee_token"] = f"{payload.conference_id}:{attendee_id}:{token}"
    return result


@app.post("/request-connection", status_code=201)
async def request_connection(
    payload: ConnectionRequest, identity: tuple[str, str] | None = Depends(attendee_claim)
) -> dict[str, str]:
    if not identity or identity[0] != payload.conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    await ensure_indices_ready()
    requester = identity[1]
    if requester == payload.recipient_id:
        raise HTTPException(400, "Cannot connect to yourself")
    recipient_doc_id = f"{payload.conference_id}:{payload.recipient_id}"
    try:
        recipient = await es_call(
            "read_recipient", lambda: es.get(index="attendees", id=recipient_doc_id)["_source"]
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, "Eligible attendee not found") from None
        raise
    if not recipient.get("discovery_opt_in"):
        raise HTTPException(404, "Eligible attendee not found")
    connection_id = str(uuid4())
    doc = {
        "conference_id": payload.conference_id,
        "connection_id": connection_id,
        "requester_id": requester,
        "recipient_id": payload.recipient_id,
        "message": payload.message,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await es_call(
        "create_connection",
        lambda: es.index(
            index="connections",
            id=f"{payload.conference_id}:{connection_id}",
            document=doc,
            op_type="create",
        ),
    )
    return {"connection_id": connection_id, "status": "pending"}


@app.post("/accept-connection")
async def accept_connection(
    payload: AcceptRequest, identity: tuple[str, str] | None = Depends(attendee_claim)
) -> dict[str, Any]:
    if not identity or identity[0] != payload.conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    await ensure_indices_ready()
    conn_doc_id = f"{payload.conference_id}:{payload.connection_id}"
    conn = await es_call(
        "read_connection", lambda: es.get(index="connections", id=conn_doc_id)["_source"]
    )
    if conn["recipient_id"] != identity[1]:
        raise HTTPException(403, "Only the recipient can accept this request")
    if conn["status"] != "pending":
        raise HTTPException(409, "Connection is not pending")
    conn.update(
        status="accepted",
        share_email=payload.share_email,
        share_linkedin=payload.share_linkedin,
        share_resume=payload.share_resume,
        updated_at=datetime.now(UTC).isoformat(),
    )
    await es_call(
        "accept_connection",
        lambda: es.index(index="connections", id=conn_doc_id, document=conn),
    )
    own_profile = await es_call(
        "read_acceptor",
        lambda: es.get(index="attendees", id=f"{payload.conference_id}:{identity[1]}")["_source"],
    )
    disclosed: dict[str, Any] = {"attendee_id": identity[1]}
    if payload.share_email:
        disclosed["email"] = own_profile.get("email")
    if payload.share_linkedin:
        disclosed["linkedin_url"] = own_profile.get("linkedin_url")
    if payload.share_resume:
        disclosed["resume_text"] = own_profile.get("resume_text")
    return {
        "connection_id": payload.connection_id,
        "status": "accepted",
        "shared_with_requester": disclosed,
    }


@app.post("/upload-schedule")
async def upload_schedule(
    conference_id: str,
    source_url: HttpUrl | None = None,
    file: UploadFile | None = File(default=None),
    _: None = Depends(require_organizer),
) -> dict[str, Any]:
    if bool(source_url) == bool(file):
        raise HTTPException(422, "Provide exactly one of source_url or file")
    if file:
        if file.content_type not in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(415, "Supported uploads: PDF, PNG, JPEG, WEBP")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds 10 MiB")
    # Parser boundary: implement parser client here. Do not fetch arbitrary URLs in this service.
    logger.info(
        "schedule_parse_requested conference_id=%s source_type=%s",
        conference_id,
        "url" if source_url else "file",
    )
    raise HTTPException(
        501,
        "Schedule parser is not configured; implement backend.app.schedule_parser.parse_schedule",
    )


async def match_people(operation: str, body: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Run an attendee match query (SAFE_SOURCE only) and shape hits with their "why" fragment.

    A None body means the requester gave nothing to match on, so there is nothing to search.
    """
    if body is None:
        return []
    hits = await es_call(
        operation,
        lambda: es.search(**body)["hits"]["hits"],
        **{"db.elasticsearch.index": "attendees"},
    )
    span = trace.get_current_span()
    span.set_attribute(f"{operation}.match.candidates", len(hits))
    if hits and hits[0].get("_score") is not None:
        span.set_attribute(f"{operation}.match.top_score", float(hits[0]["_score"]))
    return [person_hit(hit) for hit in hits]


async def read_talk(conference_id: str, talk_id: str) -> dict[str, Any]:
    return await es_call(
        "read_talk",
        lambda: es.get(index="talks", id=f"{conference_id}:{talk_id}")["_source"],
        **{"db.elasticsearch.index": "talks"},
    )


@app.get("/conferences/{conference_id}/talks/{talk_id}/audience")
async def talk_audience(
    conference_id: str, talk_id: str, _: None = Depends(require_organizer)
) -> dict[str, Any]:
    """Q4: opted-in attendees who would enjoy this talk. Organizers only; safe fields only."""
    talk = await read_talk(conference_id, talk_id)
    people = await match_people("talk_audience", talk_audience_query(conference_id, talk))
    return {"talk_id": talk_id, "count": len(people), "attendees": people}


@app.get("/conferences/{conference_id}/talks/{talk_id}/similar-past")
async def similar_past_talks(
    conference_id: str, talk_id: str, _: None = Depends(require_conference_access)
) -> dict[str, Any]:
    """Q5: past recordings like this session, from the read-only talks-archive."""
    talk = await read_talk(conference_id, talk_id)
    body = similar_past_talks_query(talk)
    hits = await es_call(
        "similar_past_talks",
        lambda: es.search(**body)["hits"]["hits"],
        **{"db.elasticsearch.index": "talks-archive"},
    )
    trace.get_current_span().set_attribute("match.candidates", len(hits))
    return {
        "talk_id": talk_id,
        "past_talks": [hit["_source"] | {"score": hit.get("_score")} for hit in hits],
    }


def _string_list(value: Any) -> list[str]:
    items = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return [str(item).strip() for item in items if str(item).strip()]


def talk_identifier(conference_id: str, talk: dict[str, Any], start_time_utc: str) -> str:
    """Stable talk id so re-confirming overwrites instead of duplicating.

    Parallel sessions share title and start (two "Lunch" at 12:00), so room, track and speakers
    take part in the hash when present.
    """
    provided = talk.get("talk_id")
    if isinstance(provided, str) and provided.strip():
        return provided.strip()
    seed = "\n".join(
        [
            conference_id,
            str(talk["title"]).strip(),
            start_time_utc,
            str(talk.get("room") or "").strip(),
            "|".join(sorted(_string_list(talk.get("track")))),
            "|".join(sorted(_string_list(talk.get("speakers")))),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def talk_document(
    conference_id: str, talk: dict[str, Any], talk_id: str, start: datetime, end: datetime
) -> dict[str, Any]:
    """Project a parsed talk onto the strict `talks` mapping; unknown keys are dropped."""
    title = str(talk["title"]).strip()
    abstract = str(talk.get("abstract") or "").strip()
    doc: dict[str, Any] = {
        "conference_id": conference_id,
        "talk_id": talk_id,
        "title": title,
        "start_time": start.astimezone(UTC).isoformat(),
        "end_time": end.astimezone(UTC).isoformat(),
        "confirmed": True,
        "semantic_content": f"{title}\n\n{abstract}" if abstract else title,
    }
    if abstract:
        doc["abstract"] = abstract
    if talk.get("room"):
        doc["room"] = str(talk["room"]).strip()
    for key in ("speakers", "track"):
        values = _string_list(talk.get(key))
        if values:
            doc[key] = values
    assert set(doc) <= TALK_FIELDS
    return doc


@app.post("/confirm-schedule")
async def confirm_schedule(
    payload: ConfirmSchedule, _: None = Depends(require_organizer)
) -> dict[str, Any]:
    await ensure_indices_ready()
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for position, talk in enumerate(payload.talks):
        required = {"title", "start_time", "end_time"}
        if not required.issubset(talk):
            raise HTTPException(422, "Each talk requires title, start_time, and end_time")
        try:
            start = datetime.fromisoformat(str(talk["start_time"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(talk["end_time"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(422, "Talk times must be ISO-8601 timestamps") from exc
        if not start.tzinfo or not end.tzinfo or end <= start:
            raise HTTPException(422, "Talk times must be timezone-aware and end after start")
        start_utc = start.astimezone(UTC).isoformat()
        talk_id = talk_identifier(payload.conference_id, talk, start_utc)
        if talk_id in seen_ids:  # still colliding inside one request: disambiguate, never drop
            talk_id = f"{talk_id}-{position}"
        seen_ids.add(talk_id)
        normalized.append(talk_document(payload.conference_id, talk, talk_id, start, end))
    actions: list[dict[str, Any]] = []
    for talk in normalized:
        doc_id = f"{payload.conference_id}:{talk['talk_id']}"
        actions.append({"index": {"_index": "talks", "_id": doc_id}})
        actions.append(talk)
    for i in range(0, len(actions), BULK_BATCH_SIZE):
        batch = actions[i : i + BULK_BATCH_SIZE]
        resp = await es_call(
            "confirm_schedule",
            lambda batch=batch: es_writer.bulk(operations=batch, refresh="wait_for"),
            **{"db.elasticsearch.index": "talks", "conference.talk_count": len(batch) // 2},
        )
        body = getattr(resp, "body", resp)
        if body.get("errors"):
            failed = [
                item for item in body.get("items", []) if "error" in next(iter(item.values()), {})
            ]
            logger.error(
                "confirm_schedule_bulk_failed conference_id=%s failed_count=%d first_error=%s",
                payload.conference_id,
                len(failed),
                next(iter(failed[0].values())).get("error") if failed else None,
            )
            raise HTTPException(502, "Some talks could not be stored")
    confirmed_ids = [talk["talk_id"] for talk in normalized]
    removed = await es_call(
        "remove_stale_talks",
        lambda: es.delete_by_query(
            index="talks",
            query={
                "bool": {
                    "filter": [{"term": {"conference_id": payload.conference_id}}],
                    "must_not": [{"terms": {"talk_id": confirmed_ids}}],
                }
            },
            refresh=True,
            conflicts="proceed",
        ),
        **{"db.elasticsearch.index": "talks", "conference.talk_count": len(confirmed_ids)},
    )
    logger.info(
        "confirm_schedule_stale_removed conference_id=%s deleted=%s",
        payload.conference_id,
        getattr(removed, "body", removed).get("deleted"),
    )
    join_url = (
        f"{os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')}/join/{payload.conference_id}"
    )
    qr = qrcode.make(join_url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    return {
        "conference_id": payload.conference_id,
        "talk_count": len(normalized),
        "join_url": join_url,
        "qr_code_data_url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(),
    }
