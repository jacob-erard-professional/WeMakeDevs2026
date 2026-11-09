"""Conference attendee and organizer API. Elasticsearch is the durable data store."""

from __future__ import annotations

import base64
import io
import logging
import os
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import qrcode
from elasticsearch import Elasticsearch, NotFoundError
from opentelemetry import trace
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("conference_api")
tracer = trace.get_tracer("conference_api")
app = FastAPI(title="Conference API", version="0.1.0")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")
ORGANIZER_API_KEY = os.getenv("ORGANIZER_API_KEY", "")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
es = Elasticsearch(ES_URL, api_key=ES_API_KEY, request_timeout=5) if ES_API_KEY else Elasticsearch(ES_URL, request_timeout=5)


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
            logger.info("es_operation=%s outcome=success duration_ms=%d", operation, int((datetime.now(UTC)-started).total_seconds()*1000))
            return result
        except Exception:
            logger.exception("es_operation=%s outcome=error", operation)
            raise HTTPException(503, "Conference data store unavailable") from None


@app.middleware("http")
async def request_log(request: Request, call_next: Any) -> JSONResponse:
    started = datetime.now(UTC)
    response = await call_next(request)
    logger.info("http_method=%s route=%s status=%d duration_ms=%d", request.method, request.url.path, response.status_code, int((datetime.now(UTC)-started).total_seconds()*1000))
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
    talks = es_call("recommend_talks", lambda: es.search(index="talks", query={"bool": {"filter": [{"term": {"conference_id": payload.conference_id}}]}}, size=100)["hits"]["hits"])
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
async def upload_schedule(conference_id: str, source_url: HttpUrl | None = None, file: UploadFile | None = File(default=None), _: None = Depends(require_organizer)) -> dict[str, Any]:
    if bool(source_url) == bool(file):
        raise HTTPException(422, "Provide exactly one of source_url or file")
    if file:
        if file.content_type not in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(415, "Supported uploads: PDF, PNG, JPEG, WEBP")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds 10 MiB")
    # Parser boundary: implement parser client here. Do not fetch arbitrary URLs in this service.
    logger.info("schedule_parse_requested conference_id=%s source_type=%s", conference_id, "url" if source_url else "file")
    raise HTTPException(501, "Schedule parser is not configured; implement backend.app.schedule_parser.parse_schedule")


@app.post("/confirm-schedule")
def confirm_schedule(payload: ConfirmSchedule, _: None = Depends(require_organizer)) -> dict[str, Any]:
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
        normalized.append(talk | {"conference_id": payload.conference_id, "talk_id": str(uuid4()), "start_time": start.astimezone(UTC).isoformat(), "end_time": end.astimezone(UTC).isoformat(), "confirmed": True})
    actions = []
    for talk in normalized:
        actions.extend([{"index": {"_index": "talks", "_id": f"{payload.conference_id}:{talk['talk_id']}"}}, talk])
    for i in range(0, len(actions), 500):
        batch = actions[i:i+500]
        if batch and "index" not in batch[-1]:
            batch = batch[:-1]
        es_call("confirm_schedule", lambda batch=batch: es.bulk(operations=batch, refresh="wait_for"))
    join_url = f"{os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')}/join/{payload.conference_id}"
    qr = qrcode.make(join_url)
    buffer = io.BytesIO(); qr.save(buffer, format="PNG")
    return {"conference_id": payload.conference_id, "talk_count": len(normalized), "join_url": join_url, "qr_code_data_url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}

