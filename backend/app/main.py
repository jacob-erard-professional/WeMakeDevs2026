"""Conference attendee and organizer API. Elasticsearch is the durable data store."""

from __future__ import annotations

import base64
import io
import ipaddress
import logging
import mimetypes
import os
import secrets
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid4, uuid5

from bs4 import BeautifulSoup
from elasticsearch import Elasticsearch, NotFoundError
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
import httpx
from openai import AsyncOpenAI
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field, HttpUrl
import qrcode

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("conference_api")
tracer = trace.get_tracer("conference_api")
meter = metrics.get_meter("conference_api")
http_requests = meter.create_counter("http.server.request.count", unit="{request}")
http_duration = meter.create_histogram("http.server.request.duration", unit="ms")
elasticsearch_operations = meter.create_counter("elasticsearch.operation.count", unit="{operation}")
elasticsearch_duration = meter.create_histogram("elasticsearch.operation.duration", unit="ms")
extraction_calls = meter.create_counter("schedule.extraction.count", unit="{call}")
extraction_duration = meter.create_histogram("schedule.extraction.duration", unit="ms")
app = FastAPI(title="Conference API", version="0.1.0")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")
ORGANIZER_API_KEY = os.getenv("ORGANIZER_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_MEDIA = {
    "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png", "image/jpeg", "image/webp",
}
es = Elasticsearch(ES_URL, api_key=ES_API_KEY, request_timeout=5) if ES_API_KEY else Elasticsearch(ES_URL, request_timeout=5)
openai_client = (
    AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0)
    if os.getenv("OPENAI_API_KEY")
    else None
)


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


class Talk(BaseModel):
    talk_id: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    abstract: str = Field(default="", max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    speaker_names: list[str] = Field(default_factory=list, max_length=50)
    start_time: datetime
    end_time: datetime
    room: str | None = Field(default=None, max_length=200)


class ExtractedSchedule(BaseModel):
    title: str = Field(default="Conference schedule", max_length=300)
    timezone: str = Field(default="UTC", max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    talks: list[Talk] = Field(min_length=1, max_length=1000)


class ConfirmSchedule(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    draft_id: str | None = Field(default=None, max_length=128)
    talks: list[Talk] | None = Field(default=None, min_length=1, max_length=1000)


def attendee_claim(authorization: str | None = Header(default=None)) -> tuple[str, str] | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        conference_id, attendee_id, token = authorization[7:].split(":", 2)
        doc = es.get(index="attendees", id=f"{conference_id}:{attendee_id}")
        if not secrets.compare_digest(doc["_source"].get("access_token", ""), token):
            raise ValueError
        return conference_id, attendee_id
    except (ValueError, NotFoundError, Exception) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(401, "Invalid attendee token") from exc


def require_organizer(x_organizer_key: str | None = Header(default=None)) -> None:
    if not ORGANIZER_API_KEY:
        raise HTTPException(503, "Organizer authorization is not configured")
    if not x_organizer_key or not secrets.compare_digest(x_organizer_key, ORGANIZER_API_KEY):
        raise HTTPException(401, "Organizer authorization required")


def es_call(operation: str, fn: Any) -> Any:
    with tracer.start_as_current_span(operation):
        started = datetime.now(UTC)
        try:
            result = fn()
            duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
            elasticsearch_operations.add(1, {"operation": operation, "outcome": "success"})
            elasticsearch_duration.record(duration_ms, {"operation": operation})
            logger.info("es_operation=%s outcome=success duration_ms=%d", operation, int(duration_ms))
            return result
        except Exception:
            duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
            elasticsearch_operations.add(1, {"operation": operation, "outcome": "error"})
            elasticsearch_duration.record(duration_ms, {"operation": operation})
            logger.exception("es_operation=%s outcome=error", operation)
            raise HTTPException(503, "Conference data store unavailable") from None


def ensure_indices() -> None:
    mappings = {
        "schedule_drafts": {
            "properties": {
                "conference_id": {"type": "keyword"},
                "draft_id": {"type": "keyword"},
                "status": {"type": "keyword"},
                "expires_at": {"type": "date"},
                "schedule": {"type": "object", "enabled": True},
            }
        },
        "conferences": {
            "properties": {
                "conference_id": {"type": "keyword"},
                "active_schedule_id": {"type": "keyword"},
                "updated_at": {"type": "date"},
            }
        },
        "talks": {
            "properties": {
                "conference_id": {"type": "keyword"},
                "schedule_id": {"type": "keyword"},
                "talk_id": {"type": "keyword"},
                "title": {"type": "text"},
                "abstract": {"type": "text"},
                "tags": {"type": "keyword"},
                "speaker_names": {"type": "keyword"},
                "start_time": {"type": "date"},
                "end_time": {"type": "date"},
                "room": {"type": "keyword"},
                "confirmed": {"type": "boolean"},
            }
        },
    }
    for index, mapping in mappings.items():
        es_call("ensure_" + index, lambda index=index, mapping=mapping: es.indices.create(index=index, mappings=mapping, ignore=400))


@app.on_event("startup")
def startup() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": os.getenv("OTEL_SERVICE_NAME", "wemakedevs-backend")}
            )
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(
            MeterProvider(resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "wemakedevs-backend")}), metric_readers=[metric_reader])
        )
    if os.getenv("ENSURE_ES_INDICES", "true").lower() == "true":
        ensure_indices()


def validate_public_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(422, "Schedule URL is invalid") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port not in (None, 443):
        raise HTTPException(422, "Schedule URL must be a public HTTPS URL")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise HTTPException(422, "Schedule URL must resolve to a public host") from exc


async def read_schedule_source(source_url: str | None, file: UploadFile | None) -> tuple[str, bytes, str]:
    if bool(source_url) == bool(file):
        raise HTTPException(422, "Provide exactly one of source_url or file")
    if source_url:
        validate_public_url(source_url)
        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream("GET", source_url) as response:
                    network_stream = response.extensions.get("network_stream")
                    peer = network_stream.get_extra_info("server_addr") if network_stream else None
                    if peer and not ipaddress.ip_address(peer[0]).is_global:
                        raise HTTPException(422, "Schedule URL must resolve to a public host")
                    if response.status_code >= 300:
                        raise HTTPException(422, "Schedule URL could not be fetched (redirects are not followed)")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type == "application/octet-stream":
                        content_type = mimetypes.guess_type(urlparse(source_url).path)[0] or content_type
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, "Upload exceeds 10 MiB")
                    content = bytes(chunks)
            filename = "schedule"
        except httpx.HTTPError as exc:
            raise HTTPException(422, "Schedule URL could not be fetched") from exc
    else:
        content_type = (file.content_type or "").lower()
        filename = file.filename or "schedule"
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 10 MiB")
    if not content:
        raise HTTPException(422, "Schedule source is empty")
    if content_type not in SUPPORTED_MEDIA and content_type not in {"text/html", "text/plain"}:
        raise HTTPException(415, "Supported formats: PDF, DOCX, PNG, JPEG, WEBP, HTML, or plain text")
    return filename, content, content_type


def schedule_input(filename: str, content: bytes, content_type: str) -> dict[str, Any]:
    encoded = base64.b64encode(content).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded}"
    if content_type.startswith("image/"):
        return {"type": "input_image", "image_url": data_url}
    if content_type in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        extension = ".pdf" if content_type == "application/pdf" else ".docx"
        safe_filename = os.path.basename(filename).replace("\x00", "")[:100]
        if not safe_filename.lower().endswith(extension):
            safe_filename = f"schedule{extension}"
        return {"type": "input_file", "filename": safe_filename, "file_data": data_url}
    text = content.decode("utf-8", errors="replace")
    if content_type == "text/html":
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return {"type": "input_text", "text": text[:100_000]}


def validate_schedule(schedule: ExtractedSchedule) -> ExtractedSchedule:
    identifiers: set[str] = set()
    for talk in schedule.talks:
        if talk.start_time.tzinfo is None or talk.end_time.tzinfo is None or talk.end_time <= talk.start_time:
            raise HTTPException(422, "Every talk needs timezone-aware times and end_time after start_time")
        if talk.talk_id and talk.talk_id in identifiers:
            raise HTTPException(422, "Talk identifiers must be unique")
        if talk.talk_id:
            identifiers.add(talk.talk_id)
    return schedule


@app.middleware("http")
async def request_log(request: Request, call_next: Any) -> JSONResponse:
    started = datetime.now(UTC)
    response = await call_next(request)
    duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
    attributes = {"http.request.method": request.method, "http.route": request.url.path, "http.response.status_code": response.status_code}
    http_requests.add(1, attributes)
    http_duration.record(duration_ms, attributes)
    logger.info("http_method=%s route=%s status=%d duration_ms=%d", request.method, request.url.path, response.status_code, int(duration_ms))
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/save-user-data")
async def save_user_data(request: Request, identity: tuple[str, str] | None = Depends(attendee_claim)) -> dict[str, Any]:
    resume_asset = None
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        try:
            import json

            payload = SaveUserData.model_validate_json(str(form.get("profile", "{}")))
        except ValueError as exc:
            raise HTTPException(422, "Multipart requests require a valid JSON 'profile' field") from exc
        upload = form.get("resume")
        if isinstance(upload, UploadFile):
            if upload.content_type not in {"application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
                raise HTTPException(415, "Resume must be PDF, plain text, or DOCX")
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Resume exceeds 10 MiB")
            resume_asset = {"filename": upload.filename, "content_type": upload.content_type, "content_base64": base64.b64encode(content).decode("ascii")}
    else:
        try:
            payload = SaveUserData.model_validate(await request.json())
        except ValueError as exc:
            raise HTTPException(422, "Request body must be valid profile JSON") from exc
    if identity and identity[0] != payload.conference_id:
        raise HTTPException(403, "Attendee token belongs to another conference")
    attendee_id = identity[1] if identity else str(uuid4())
    token = None if identity else secrets.token_urlsafe(32)
    for slot in payload.blockout_times:
        if slot.start_time.tzinfo is None or slot.end_time.tzinfo is None or slot.end_time <= slot.start_time:
            raise HTTPException(422, "Blockout times must be timezone-aware and have end after start")
    doc = payload.model_dump(mode="json") | {"attendee_id": attendee_id, "updated_at": datetime.now(UTC).isoformat()}
    if resume_asset:
        doc["resume_asset"] = resume_asset
    if token:
        doc["access_token"] = token
    elif identity:
        old = es_call("read_attendee", lambda: es.get(index="attendees", id=f"{payload.conference_id}:{attendee_id}")["_source"])
        doc["access_token"] = old["access_token"]
    es_call("save_attendee", lambda: es.index(index="attendees", id=f"{payload.conference_id}:{attendee_id}", document=doc))
    conference = es_call("read_active_schedule", lambda: es.get(index="conferences", id=payload.conference_id, ignore=404))
    active_schedule = conference.get("_source", {}).get("active_schedule_id") if conference.get("found") else None
    talks = es_call("recommend_talks", lambda: es.search(index="talks", query={"bool": {"filter": [{"term": {"conference_id": payload.conference_id}}, {"term": {"schedule_id": active_schedule}}]}} if active_schedule else {"match_none": {}}, size=100)["hits"]["hits"])
    blockouts = [(b.start_time, b.end_time) for b in payload.blockout_times]
    recommendations = []
    for hit in talks:
        talk = hit["_source"]
        try:
            start, end = datetime.fromisoformat(talk["start_time"].replace("Z", "+00:00")), datetime.fromisoformat(talk["end_time"].replace("Z", "+00:00"))
            if any(start < stop and begin < end for begin, stop in blockouts):
                continue
        except (KeyError, ValueError):
            pass
        recommendations.append(talk)
    users = []
    if payload.discovery_opt_in:
        found = es_call("recommend_attendees", lambda: es.search(index="attendees", query={"bool": {"filter": [{"term": {"conference_id": payload.conference_id}}, {"term": {"discovery_opt_in": True}}], "must_not": [{"term": {"attendee_id": attendee_id}}]}}, size=20)["hits"]["hits"])
        users = [{"attendee_id": h["_source"]["attendee_id"], "name": h["_source"]["name"], "bio": h["_source"]["bio"]} for h in found]
    result = {"attendee_id": attendee_id, "recommendations": {"talks": recommendations, "attendees": users}}
    if token:
        result["attendee_token"] = f"{payload.conference_id}:{attendee_id}:{token}"
    return result


@app.post("/request-connection", status_code=201)
def request_connection(payload: ConnectionRequest, identity: tuple[str, str] = Depends(attendee_claim)) -> dict[str, str]:
    if not identity or identity[0] != payload.conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    requester = identity[1]
    if requester == payload.recipient_id:
        raise HTTPException(400, "Cannot connect to yourself")
    recipient_id = f"{payload.conference_id}:{payload.recipient_id}"
    recipient = es_call("read_recipient", lambda: es.get(index="attendees", id=recipient_id)["_source"])
    if not recipient.get("discovery_opt_in"):
        raise HTTPException(404, "Eligible attendee not found")
    connection_id = str(uuid4())
    doc = {"conference_id": payload.conference_id, "connection_id": connection_id, "requester_id": requester, "recipient_id": payload.recipient_id, "message": payload.message, "status": "pending", "created_at": datetime.now(UTC).isoformat()}
    es_call("create_connection", lambda: es.index(index="connections", id=f"{payload.conference_id}:{connection_id}", document=doc, op_type="create"))
    return {"connection_id": connection_id, "status": "pending"}


@app.post("/accept-connection")
def accept_connection(payload: AcceptRequest, identity: tuple[str, str] = Depends(attendee_claim)) -> dict[str, Any]:
    if not identity or identity[0] != payload.conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    conn_id = f"{payload.conference_id}:{payload.connection_id}"
    conn = es_call("read_connection", lambda: es.get(index="connections", id=conn_id)["_source"])
    if conn["recipient_id"] != identity[1]:
        raise HTTPException(403, "Only the recipient can accept this request")
    if conn["status"] != "pending":
        raise HTTPException(409, "Connection is not pending")
    conn.update(status="accepted", share_email=payload.share_email, share_linkedin=payload.share_linkedin, share_resume=payload.share_resume, updated_at=datetime.now(UTC).isoformat())
    es_call("accept_connection", lambda: es.index(index="connections", id=conn_id, document=conn))
    own_profile = es_call("read_acceptor", lambda: es.get(index="attendees", id=f"{payload.conference_id}:{identity[1]}")["_source"])
    disclosed = {"attendee_id": identity[1]}
    if payload.share_email: disclosed["email"] = own_profile.get("email")
    if payload.share_linkedin: disclosed["linkedin_url"] = own_profile.get("linkedin_url")
    if payload.share_resume:
        disclosed["resume_text"] = own_profile.get("resume_text")
        disclosed["resume_asset"] = own_profile.get("resume_asset")
    return {"connection_id": payload.connection_id, "status": "accepted", "shared_with_requester": disclosed}


@app.post("/upload-schedule")
async def upload_schedule(
    conference_id: str = Form(min_length=1, max_length=128),
    source_url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    _: None = Depends(require_organizer),
) -> dict[str, Any]:
    if not openai_client:
        raise HTTPException(503, "OpenAI extraction is not configured")
    filename, content, content_type = await read_schedule_source(source_url, file)
    started = datetime.now(UTC)
    extraction_outcome = "error"
    extraction_attributes = {"provider": "openai", "model": OPENAI_MODEL}
    with tracer.start_as_current_span("openai.schedule_extraction") as span:
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.request.model", OPENAI_MODEL)
        span.set_attribute("schedule.source_type", "url" if source_url else "file")
        span.set_attribute("schedule.input_bytes", len(content))
        try:
            response = await openai_client.responses.parse(
                model=OPENAI_MODEL,
                store=False,
                input=[
                    {"role": "system", "content": "Extract only schedule facts present in the source. Do not invent sessions, dates, times, speakers, or rooms. Include uncertainty in warnings. Preserve the source timezone when clear; otherwise use UTC and warn."},
                    {"role": "user", "content": [schedule_input(filename, content, content_type)]},
                ],
                text_format=ExtractedSchedule,
            )
            if not response.output_parsed:
                raise HTTPException(422, "OpenAI could not extract a valid schedule")
            schedule = validate_schedule(response.output_parsed)
            extraction_outcome = "success"
            if response.usage:
                span.set_attribute("llm.usage.input_tokens", response.usage.input_tokens)
                span.set_attribute("llm.usage.output_tokens", response.usage.output_tokens)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("schedule_extraction_failed model=%s", OPENAI_MODEL)
            raise HTTPException(502, "Schedule extraction failed") from exc
        finally:
            extraction_calls.add(1, extraction_attributes | {"outcome": extraction_outcome})
            extraction_duration.record(
                (datetime.now(UTC) - started).total_seconds() * 1000,
                extraction_attributes,
            )
    draft_id = str(uuid4())
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    document = {"conference_id": conference_id, "draft_id": draft_id, "status": "review", "schedule": schedule.model_dump(mode="json"), "created_at": datetime.now(UTC).isoformat(), "expires_at": expires_at.isoformat()}
    es_call("save_schedule_draft", lambda: es.index(index="schedule_drafts", id=f"{conference_id}:{draft_id}", document=document, refresh="wait_for"))
    logger.info("schedule_extraction_complete conference_id=%s talk_count=%d duration_ms=%d", conference_id, len(schedule.talks), int((datetime.now(UTC)-started).total_seconds()*1000))
    return {"draft_id": draft_id, "conference_id": conference_id, "expires_at": expires_at.isoformat(), "schedule": schedule.model_dump(mode="json")}


@app.post("/confirm-schedule")
def confirm_schedule(payload: ConfirmSchedule, _: None = Depends(require_organizer)) -> dict[str, Any]:
    draft_id = None
    draft = None
    if payload.draft_id:
        draft_id = f"{payload.conference_id}:{payload.draft_id}"
        try:
            draft = es_call("read_schedule_draft", lambda: es.get(index="schedule_drafts", id=draft_id)["_source"])
        except HTTPException as exc:
            raise HTTPException(404, "Schedule draft not found") from exc
        if draft.get("conference_id") != payload.conference_id:
            raise HTTPException(404, "Schedule draft not found")
        if draft.get("status") == "confirmed" and not payload.talks:
            return draft["confirmation"]
        if datetime.fromisoformat(draft["expires_at"]) <= datetime.now(UTC):
            raise HTTPException(410, "Schedule draft expired; upload it again")
        schedule = ExtractedSchedule(talks=payload.talks) if payload.talks else ExtractedSchedule.model_validate(draft["schedule"])
    elif payload.talks:
        schedule = ExtractedSchedule(talks=payload.talks)
    else:
        raise HTTPException(422, "Provide draft_id or reviewed talks")
    schedule = validate_schedule(schedule)
    schedule_id = payload.draft_id or str(uuid4())
    normalized = []
    for index, talk in enumerate(schedule.talks):
        item = talk.model_dump(mode="json")
        normalized.append(
            item
            | {
                "conference_id": payload.conference_id,
                "schedule_id": schedule_id,
                "talk_id": item.get("talk_id") or str(uuid5(NAMESPACE_URL, f"{schedule_id}:{index}")),
                "start_time": talk.start_time.astimezone(UTC).isoformat(),
                "end_time": talk.end_time.astimezone(UTC).isoformat(),
                "confirmed": True,
            }
        )
    actions = []
    for talk in normalized:
        actions.extend([{"index": {"_index": "talks", "_id": f"{payload.conference_id}:{schedule_id}:{talk['talk_id']}"}}, talk])
    for i in range(0, len(actions), 500):
        batch = actions[i:i+500]
        if batch and "index" not in batch[-1]:
            batch = batch[:-1]
        result = es_call(
            "confirm_schedule",
            lambda batch=batch: es.bulk(operations=batch, refresh="wait_for"),
        )
        if result.get("errors"):
            logger.error("schedule_index_partial_failure conference_id=%s", payload.conference_id)
            raise HTTPException(503, "Schedule could not be fully saved; retry confirmation")
    join_url = f"{os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')}/join/{payload.conference_id}"
    qr = qrcode.make(join_url)
    buffer = io.BytesIO(); qr.save(buffer, format="PNG")
    result = {"conference_id": payload.conference_id, "schedule_id": schedule_id, "talk_count": len(normalized), "join_url": join_url, "qr_code_data_url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}
    es_call("publish_schedule", lambda: es.index(index="conferences", id=payload.conference_id, document={"conference_id": payload.conference_id, "active_schedule_id": schedule_id, "updated_at": datetime.now(UTC).isoformat()}, refresh="wait_for"))
    if draft_id:
        es_call("mark_schedule_draft_confirmed", lambda: es.update(index="schedule_drafts", id=draft_id, doc={"status": "confirmed", "confirmation": result}, refresh="wait_for"))
    return result

