"""Conference attendee and organizer API. Elasticsearch is the durable data store."""

from __future__ import annotations

import base64
import hashlib
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
from elasticsearch import Elasticsearch, NotFoundError
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
from pydantic import BaseModel, Field, HttpUrl
from starlette.concurrency import run_in_threadpool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("conference_api")

T = TypeVar("T")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")
ORGANIZER_API_KEY = os.getenv("ORGANIZER_API_KEY", "")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Even on purpose: bulk payloads are [action, document] pairs and a batch must never split one.
BULK_BATCH_SIZE = 500
es = (
    Elasticsearch(ES_URL, api_key=ES_API_KEY, request_timeout=5)
    if ES_API_KEY
    else Elasticsearch(ES_URL, request_timeout=5)
)


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


# --- Elasticsearch mappings --------------------------------------------------------------------

_ID = {"type": "keyword"}
_DATE = {"type": "date"}
_TEXT = {"type": "text"}
_BOOL = {"type": "boolean"}
_KEYWORD_SUBFIELD = {"type": "keyword", "ignore_above": 512}

# Serverless rejects number_of_shards / number_of_replicas / refresh_interval: settings stay empty.
# `talks` is NOT here: it is an alias over the shared, strictly mapped `talks-jina` index
# (see docs/elasticsearch-connection.md). Organizer talks are written into it with that schema.
INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    "attendees": {
        "dynamic": True,
        "properties": {
            "conference_id": _ID,
            "attendee_id": _ID,
            "name": {"type": "text", "fields": {"keyword": _KEYWORD_SUBFIELD}},
            "bio": _TEXT,
            "email": _ID,
            "linkedin_url": _ID,
            "blockout_times": {"properties": {"start_time": _DATE, "end_time": _DATE}},
            "discovery_opt_in": _BOOL,
            "resume_text": {"type": "text", "index": False},
            "resume_asset": {"type": "object", "enabled": False},
            "access_token": {"type": "keyword", "index": False, "doc_values": False},
            "updated_at": _DATE,
        },
    },
    "connections": {
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
}


def ensure_indices() -> None:
    """Create each index with its explicit mapping if it does not exist yet (idempotent)."""
    for index, mapping in INDEX_MAPPINGS.items():
        with tracer.start_as_current_span("ensure_index") as span:
            span.set_attribute("db.system", "elasticsearch")
            span.set_attribute("db.elasticsearch.index", index)
            if es.indices.exists(index=index):
                continue
            es.indices.create(index=index, mappings=mapping)
            logger.info("es_index_created index=%s", index)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await run_in_threadpool(ensure_indices)
    except Exception:  # noqa: BLE001 - startup must survive an unreachable data store
        logger.exception("es_index_setup_failed; continuing so /health stays reachable")
    yield


app = FastAPI(title="Conference API", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


# --- Models ------------------------------------------------------------------------------------


class Blockout(BaseModel):
    start_time: datetime
    end_time: datetime


class SaveUserData(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    bio: str = Field(default="", max_length=10_000)
    email: str | None = Field(default=None, max_length=320)
    linkedin_url: HttpUrl | None = None
    blockout_times: list[Blockout] = Field(default_factory=list, max_length=100)
    discovery_opt_in: bool = False
    resume_text: str | None = Field(default=None, max_length=50_000)


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
    if not secrets.compare_digest(doc["_source"].get("access_token", ""), token):
        raise HTTPException(401, "Invalid attendee token")
    return conference_id, attendee_id


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
    resume_asset = None
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        try:
            payload = SaveUserData.model_validate_json(str(form.get("profile", "{}")))
        except ValueError as exc:
            raise HTTPException(
                422, "Multipart requests require a valid JSON 'profile' field"
            ) from exc
        upload = form.get("resume")
        if isinstance(upload, UploadFile):
            if upload.content_type not in {
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }:
                raise HTTPException(415, "Resume must be PDF, plain text, or DOCX")
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Resume exceeds 10 MiB")
            resume_asset = {
                "filename": upload.filename,
                "content_type": upload.content_type,
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
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
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if resume_asset:
        doc["resume_asset"] = resume_asset
    attendee_doc_id = f"{payload.conference_id}:{attendee_id}"
    if token:
        doc["access_token"] = token
    elif identity:
        old = await es_call(
            "read_attendee", lambda: es.get(index="attendees", id=attendee_doc_id)["_source"]
        )
        doc["access_token"] = old["access_token"]
    await es_call(
        "save_attendee", lambda: es.index(index="attendees", id=attendee_doc_id, document=doc)
    )
    talks = await es_call(
        "recommend_talks",
        lambda: es.search(
            index="talks",
            query={
                "bool": {
                    "filter": [
                        {"term": {"conference_id": payload.conference_id}},
                        {"term": {"source": TALK_SOURCE}},
                    ]
                }
            },
            source={"excludes": ["semantic_content"]},
            size=100,
        )["hits"]["hits"],
    )
    blockouts = [(b.start_time, b.end_time) for b in payload.blockout_times]
    recommendations = []
    for hit in talks:
        talk = hit["_source"]
        try:
            start = datetime.fromisoformat(talk["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(talk["end"].replace("Z", "+00:00"))
            if any(start < stop and begin < end for begin, stop in blockouts):
                continue
        except (KeyError, ValueError):
            pass
        recommendations.append(talk)
    users = []
    if payload.discovery_opt_in:
        found = await es_call(
            "recommend_attendees",
            lambda: es.search(
                index="attendees",
                query={
                    "bool": {
                        "filter": [
                            {"term": {"conference_id": payload.conference_id}},
                            {"term": {"discovery_opt_in": True}},
                        ],
                        "must_not": [{"term": {"attendee_id": attendee_id}}],
                    }
                },
                size=20,
            )["hits"]["hits"],
        )
        users = [
            {
                "attendee_id": h["_source"]["attendee_id"],
                "name": h["_source"]["name"],
                "bio": h["_source"]["bio"],
            }
            for h in found
        ]
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
        disclosed["resume_asset"] = own_profile.get("resume_asset")
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


TALK_SOURCE = "organizer"


def talk_identifier(conference_id: str, talk: dict[str, Any], start_utc: str) -> str:
    """Stable talk id (used as both `_id` and `id`) so re-confirming overwrites, never duplicates.

    Conference-prefixed so organizer talks can never collide with the seeded kubecon/pyvideo ids.
    """
    provided = talk.get("talk_id") or talk.get("id")
    if isinstance(provided, str) and provided.strip():
        return f"{conference_id}:{provided.strip()}"
    seed = "\n".join([conference_id, str(talk["title"]).strip(), start_utc])
    return f"{conference_id}:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:32]}"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = [value] if isinstance(value, str) else list(value) if isinstance(value, list) else []
    return [str(item).strip() for item in items if str(item).strip()]


def shared_talk_document(
    conference_id: str, talk: dict[str, Any], start: datetime, end: datetime
) -> dict[str, Any]:
    """Project an organizer talk onto the shared `talks` schema (strict mapping: nothing else)."""
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    title = str(talk["title"]).strip()
    abstract = str(talk.get("abstract") or "").strip()
    speakers = _string_list(talk.get("speakers"))
    doc: dict[str, Any] = {
        "id": talk_identifier(conference_id, talk, start_utc.isoformat()),
        "source": TALK_SOURCE,
        "conference_id": conference_id,
        "year": start_utc.year,
        "title": title,
        "start": start_utc.isoformat(),
        "end": end_utc.isoformat(),
        "duration_s": int((end_utc - start_utc).total_seconds()),
        "confirmed": True,
        "semantic_content": f"{title}\n\n{abstract}" if abstract else title,
    }
    if abstract:
        doc["abstract"] = abstract
    if talk.get("conference"):
        doc["conference"] = str(talk["conference"]).strip()
    if speakers:
        doc["speakers"] = speakers
        doc["speakers_text"] = ", ".join(speakers)
    speaker_ids = _string_list(talk.get("speaker_ids"))
    if speaker_ids:
        doc["speaker_ids"] = speaker_ids
    tracks = _string_list(talk.get("tracks")) or _string_list(talk.get("tags"))
    if tracks:
        doc["tracks"] = tracks
    for key in ("room", "url", "video_url", "language"):
        if talk.get(key):
            doc[key] = str(talk[key]).strip()
    return doc


@app.post("/confirm-schedule")
async def confirm_schedule(
    payload: ConfirmSchedule, _: None = Depends(require_organizer)
) -> dict[str, Any]:
    normalized = []
    for talk in payload.talks:
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
        normalized.append(shared_talk_document(payload.conference_id, talk, start, end))
    actions: list[dict[str, Any]] = []
    for talk in normalized:
        actions.append({"index": {"_index": "talks", "_id": talk["id"]}})
        actions.append(talk)
    for i in range(0, len(actions), BULK_BATCH_SIZE):
        batch = actions[i : i + BULK_BATCH_SIZE]
        resp = await es_call(
            "confirm_schedule",
            lambda batch=batch: es.bulk(operations=batch, refresh="wait_for"),
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
