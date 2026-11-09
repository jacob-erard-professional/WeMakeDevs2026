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
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import qrcode
from elasticsearch import ApiError, Elasticsearch, NotFoundError
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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
from starlette.datastructures import UploadFile as FormUploadFile

from app.resume_parser import (
    MAX_RESUME_CHARS,
    ResumeProfile,
    UnsupportedResumeType,
    extract_resume_text,
    is_linkedin_pdf_text,
    merge_resume_profile,
    parse_resume,
)
from app.schedule_parser import parse_schedule
from app.schedule_recommendations import best_schedules

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("conference_api")

T = TypeVar("T")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")
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


# --- Elasticsearch indices -------------------------------------------------------------------

JINA = ".jina-embeddings-v5-text-small"
_ID = {"type": "keyword"}
_DATE = {"type": "date"}
_TEXT = {"type": "text"}
_BOOL = {"type": "boolean"}
_SEMANTIC = {"type": "semantic_text", "inference_id": JINA}

# Index bodies from backend/docs/vector-matching.md. Serverless rejects shard/replica/refresh
# settings, so only the analysis block is passed. `talks-archive` is read-only and not ours.
INDEX_BODIES: dict[str, dict[str, Any]] = {
    "conferences": {
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "conference_id": _ID,
                "name": _TEXT,
                "organizer_token_sha256": {"type": "keyword", "index": False, "doc_values": False},
                "created_at": _DATE,
            },
        },
    },
    "talks": {
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "conference_id": _ID,
                "talk_id": _ID,
                "title": _TEXT,
                "abstract": _TEXT,
                "speakers": _ID,
                "room": _ID,
                "track": _ID,
                "start_time": _DATE,
                "end_time": _DATE,
                "confirmed": _BOOL,
                "semantic_content": _SEMANTIC,
            },
        },
    },
    "attendees": {
        "settings": {
            "analysis": {
                "normalizer": {"lower": {"type": "custom", "filter": ["lowercase", "asciifolding"]}}
            }
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "conference_id": _ID,
                "attendee_id": _ID,
                "name": _TEXT,
                "headline": _TEXT,
                "bio": _TEXT,
                "interests": {"type": "keyword", "normalizer": "lower"},
                "skills": {"type": "keyword", "normalizer": "lower"},
                "working_on": _TEXT,
                "profile": _SEMANTIC,
                "looking_for": _SEMANTIC,
                "can_help_with": _SEMANTIC,
                "resume_text": _SEMANTIC,
                "discovery_opt_in": _BOOL,
                "blockout_times": {"properties": {"start_time": _DATE, "end_time": _DATE}},
                "email": {"type": "keyword", "index": False},
                "linkedin_url": {"type": "keyword", "index": False},
                "access_token_sha256": {"type": "keyword", "index": False, "doc_values": False},
                "updated_at": _DATE,
            },
        },
    },
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
SAFE_ATTENDEE_SOURCE = {"includes": ["attendee_id", "name", "headline"]}
TALK_SOURCE = ["talk_id", "title", "room", "start_time", "end_time"]
SCHEDULE_CANDIDATE_LIMIT = 100
SCHEDULE_OPTION_COUNT = 3

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


app = FastAPI(title="Conference API", version="0.1.0", lifespan=lifespan)
# Browser origins allowed to call the API (e.g. Expo web on localhost); empty disables CORS.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Organizer-Token"],
        allow_credentials=False,
    )
FastAPIInstrumentor.instrument_app(app)


# --- Models ------------------------------------------------------------------------------------


class Blockout(BaseModel):
    start_time: datetime
    end_time: datetime


class SaveUserData(BaseModel):
    conference_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    headline: str = Field(default="", max_length=300)
    email: str | None = Field(default=None, max_length=320)
    linkedin_url: HttpUrl | None = None
    bio: str = Field(default="", max_length=10_000)
    interests: list[str] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=50)
    working_on: str = Field(default="", max_length=2_000)
    looking_for: str = Field(default="", max_length=2_000)
    can_help_with: str = Field(default="", max_length=2_000)
    blockout_times: list[Blockout] = Field(default_factory=list, max_length=100)
    discovery_opt_in: bool = False
    resume_text: str | None = Field(default=None, max_length=50_000)


def profile_text(p: Mapping[str, Any]) -> str:
    """Backend-built text behind the `profile` semantic field (spec: vector-matching.md).

    Takes the attendee fields after résumé-derived values filled the empty ones, so the
    embedding benefits from the parsed headline, skills and working_on too.
    """
    interests, skills = p.get("interests") or [], p.get("skills") or []
    parts = [
        p.get("headline") or "",
        p.get("bio") or "",
        f"Working on: {p['working_on']}" if p.get("working_on") else "",
        f"Interests: {', '.join(interests)}" if interests else "",
        f"Skills: {', '.join(skills)}" if skills else "",
    ]
    return ". ".join(x for x in parts if x)


async def read_resume_upload(upload: FormUploadFile) -> str:
    """Size-check and extract text from an uploaded résumé; the raw bytes go no further."""
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Resume exceeds 10 MiB")
    try:
        text = await run_in_threadpool(
            extract_resume_text, content, upload.content_type, upload.filename
        )
    except UnsupportedResumeType as exc:
        raise HTTPException(415, str(exc)) from None
    except Exception as exc:
        logger.info("resume_text_extraction_failed type=%s", type(exc).__name__)
        raise HTTPException(422, "The resume could not be read") from exc
    return text[:MAX_RESUME_CHARS]


async def parse_resume_traced(text: str) -> ResumeProfile:
    """LLM + LinkedIn parse off the event loop, in a span that carries counts only."""
    with tracer.start_as_current_span("parse_resume") as span:
        span.set_attribute("resume.chars", len(text))
        span.set_attribute("resume.is_linkedin_pdf", is_linkedin_pdf_text(text))
        span.set_attribute("resume.llm_configured", bool(os.getenv("OPENAI_API_KEY")))
        profile = await run_in_threadpool(parse_resume, text)
        span.set_attribute("resume.skills_count", len(profile.skills))
        span.set_attribute("resume.interests_count", len(profile.interests))
        span.set_attribute("resume.has_headline", bool(profile.headline))
        span.set_attribute("resume.profile_empty", profile.is_empty())
    return profile


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


class CreateConference(BaseModel):
    name: str = Field(min_length=1, max_length=160)


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
                lambda: es.get(
                    index="attendees",
                    id=f"{conference_id}:{attendee_id}",
                    source_includes=["access_token_sha256"],
                )
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


async def verify_organizer(conference_id: str, organizer_token: str | None) -> None:
    """Authorize only the browser session that created this conference."""
    if not organizer_token:
        raise HTTPException(401, "Organizer token required")
    conference = await es_call(
        "read_organizer_claim",
        lambda: es.get(
            index="conferences",
            id=conference_id,
            source_includes=["organizer_token_sha256"],
        )["_source"],
    )
    presented = hashlib.sha256(organizer_token.encode()).hexdigest()
    if not hmac.compare_digest(conference.get("organizer_token_sha256", ""), presented):
        raise HTTPException(401, "Organizer token required")


def eligible_attendees(conference_id: str, attendee_id: str) -> dict[str, Any]:
    """The mandatory privacy filter shared by every people recommendation."""
    return {
        "filter": [
            {"term": {"conference_id": conference_id}},
            {"term": {"discovery_opt_in": True}},
        ],
        "must_not": [{"term": {"attendee_id": attendee_id}}],
    }


def semantic_candidate(
    field: str, text: str, conference_id: str, attendee_id: str
) -> dict[str, Any]:
    return {
        "bool": {
            "must": [{"semantic": {"field": field, "query": text}}],
            **eligible_attendees(conference_id, attendee_id),
        }
    }


def _hits_with_reason(hits: list[dict[str, Any]], highlight_field: str) -> list[dict[str, Any]]:
    """Project only public identity plus the allowed semantic explanation."""
    results: list[dict[str, Any]] = []
    for hit in hits:
        source = hit["_source"]
        result = {
            "attendee_id": source["attendee_id"],
            "name": source["name"],
            "headline": source.get("headline", ""),
        }
        fragments = hit.get("highlight", {}).get(highlight_field, [])
        if fragments:
            result["why"] = fragments[0]
        results.append(result)
    return results


async def ranked_talks(profile: dict[str, Any], size: int = 20) -> list[dict[str, Any]]:
    """Semantic schedule search with time conflicts removed by Elasticsearch."""
    profile_query = " ".join(
        part for part in (profile.get("profile", ""), profile.get("looking_for", "")) if part
    ).strip()
    must_not = [
        {
            "bool": {
                "filter": [
                    {"range": {"start_time": {"lt": blockout["end_time"]}}},
                    {"range": {"end_time": {"gt": blockout["start_time"]}}},
                ]
            }
        }
        for blockout in profile.get("blockout_times", [])
    ]
    query: dict[str, Any] = {
        "bool": {
            "filter": [
                {"term": {"conference_id": profile["conference_id"]}},
                {"term": {"confirmed": True}},
            ],
            "must_not": must_not,
        }
    }
    search: dict[str, Any] = {"index": "talks", "query": query, "source": TALK_SOURCE, "size": size}
    if profile_query:
        query["bool"]["must"] = [
            {"semantic": {"field": "semantic_content", "query": profile_query}}
        ]
    else:
        search["sort"] = [{"start_time": {"order": "asc"}}]
    hits = await es_call("recommend_talks", lambda: es.search(**search)["hits"]["hits"])
    # A missing score only occurs for the no-profile chronological fallback.  Equal
    # relevance then lets the schedule builder maximize how many talks fit.
    return [hit["_source"] | {"relevance": float(hit.get("_score") or 1.0)} for hit in hits]


async def recommended_talks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return await ranked_talks(profile)


def build_recommended_schedules(talks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use Elasticsearch relevance as the weights for k-best interval scheduling."""
    with tracer.start_as_current_span("build_recommended_schedules") as span:
        schedules = best_schedules(talks, count=SCHEDULE_OPTION_COUNT)
        span.set_attribute("schedule.candidate_count", len(talks))
        span.set_attribute("schedule.option_count", len(schedules))
    return schedules


async def recommended_schedules(profile: dict[str, Any]) -> list[dict[str, Any]]:
    talks = await ranked_talks(profile, size=SCHEDULE_CANDIDATE_LIMIT)
    return build_recommended_schedules(talks)


async def recommended_people(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Run the Q1 similarity and Q2 two-sided matching searches from vector-matching.md."""
    conference_id = profile["conference_id"]
    attendee_id = profile["attendee_id"]
    profile_query = profile.get("profile", "")
    similar: list[dict[str, Any]] = []
    if profile_query:
        retrievers: list[dict[str, Any]] = [
            {
                "standard": {
                    "query": semantic_candidate(
                        "profile", profile_query, conference_id, attendee_id
                    )
                }
            },
            {
                "standard": {
                    "query": semantic_candidate(
                        "resume_text", profile_query, conference_id, attendee_id
                    )
                }
            },
        ]
        interests_and_skills = list(profile.get("skills", [])) + list(profile.get("interests", []))
        if interests_and_skills:
            retrievers.append(
                {
                    "standard": {
                        "query": {
                            "bool": {
                                "should": [
                                    {"terms": {"skills": profile.get("skills", [])}},
                                    {"terms": {"interests": profile.get("interests", [])}},
                                ],
                                "minimum_should_match": 1,
                                **eligible_attendees(conference_id, attendee_id),
                            }
                        }
                    }
                }
            )
        hits = await es_call(
            "recommend_similar_attendees",
            lambda: es.search(
                index="attendees",
                size=10,
                source=SAFE_ATTENDEE_SOURCE,
                retriever={"rrf": {"rank_window_size": 50, "retrievers": retrievers}},
                highlight={"fields": {"profile": {"type": "semantic", "number_of_fragments": 1}}},
            )["hits"]["hits"],
        )
        similar = _hits_with_reason(hits, "profile")

    match_retrievers: list[dict[str, Any]] = []
    if profile.get("looking_for"):
        match_retrievers.append(
            {
                "retriever": {
                    "standard": {
                        "query": semantic_candidate(
                            "can_help_with", profile["looking_for"], conference_id, attendee_id
                        )
                    }
                },
                "weight": 0.7,
            }
        )
    if profile.get("can_help_with"):
        match_retrievers.append(
            {
                "retriever": {
                    "standard": {
                        "query": semantic_candidate(
                            "looking_for", profile["can_help_with"], conference_id, attendee_id
                        )
                    }
                },
                "weight": 0.3,
            }
        )
    matches: list[dict[str, Any]] = []
    if match_retrievers:
        hits = await es_call(
            "recommend_mutual_attendees",
            lambda: es.search(
                index="attendees",
                size=10,
                source=SAFE_ATTENDEE_SOURCE,
                retriever={
                    "linear": {
                        "rank_window_size": 50,
                        "normalizer": "minmax",
                        "retrievers": match_retrievers,
                    }
                },
                highlight={
                    "fields": {"can_help_with": {"type": "semantic", "number_of_fragments": 1}}
                },
            )["hits"]["hits"],
        )
        matches = _hits_with_reason(hits, "can_help_with")
    return {"similar": similar, "matches": matches}


# --- Routes ------------------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/conferences", status_code=201)
async def create_conference(payload: CreateConference) -> dict[str, str]:
    """Start an organizer session and return its one-time-visible management token."""
    await ensure_indices_ready()
    conference_id = f"conference-{uuid4().hex[:12]}"
    organizer_token = secrets.token_urlsafe(32)
    await es_call(
        "create_conference",
        lambda: es.index(
            index="conferences",
            id=conference_id,
            document={
                "conference_id": conference_id,
                "name": payload.name.strip(),
                "organizer_token_sha256": hashlib.sha256(organizer_token.encode()).hexdigest(),
                "created_at": datetime.now(UTC).isoformat(),
            },
            op_type="create",
            refresh="wait_for",
        ),
    )
    return {"conference_id": conference_id, "organizer_token": organizer_token}


@app.get("/join/{conference_id}")
async def join_conference(conference_id: str) -> dict[str, Any]:
    """Resolve a QR/link to its confirmed, public schedule without exposing attendee data."""
    conference = await es_call(
        "read_join_conference_metadata",
        lambda: es.get(index="conferences", id=conference_id, source_includes=["name"])["_source"],
    )
    hits = await es_call(
        "read_join_conference",
        lambda: es.search(
            index="talks",
            size=1000,
            source=["talk_id", "title", "abstract", "track", "room", "start_time", "end_time"],
            query={
                "bool": {
                    "filter": [
                        {"term": {"conference_id": conference_id}},
                        {"term": {"confirmed": True}},
                    ]
                }
            },
            sort=[{"start_time": {"order": "asc"}}],
        )["hits"]["hits"],
        **{"db.elasticsearch.index": "talks"},
    )
    if not hits:
        raise HTTPException(404, "Conference not found or has no confirmed schedule")
    return {
        "conference_id": conference_id,
        "name": conference["name"],
        "talks": [hit["_source"] for hit in hits],
    }


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
            uploaded_resume_text = await read_resume_upload(upload)
    else:
        try:
            payload = SaveUserData.model_validate(await request.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, "Request body must be valid profile JSON") from exc
    if identity and identity[0] != payload.conference_id:
        raise HTTPException(403, "Attendee token belongs to another conference")
    if payload.resume_text and payload.resume_text.lstrip().lower().startswith("data:"):
        raise HTTPException(
            422, "Upload a resume file or send extracted plain text, not base64 data"
        )
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
    # Parse only résumé text that arrived in this request; stored text was parsed when saved.
    new_resume_text = uploaded_resume_text or payload.resume_text or ""
    resume_profile = (
        await parse_resume_traced(new_resume_text) if new_resume_text.strip() else ResumeProfile()
    )
    # Typed values win; the résumé only fills empty fields (skills/interests are unioned).
    merged = merge_resume_profile(payload.model_dump(mode="json"), resume_profile)
    doc = merged | {
        "attendee_id": attendee_id,
        "profile": profile_text(merged),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if uploaded_resume_text:
        doc["resume_text"] = uploaded_resume_text
    # Strict mapping: drop empty optionals and anything the mapping does not know.
    doc = {k: v for k, v in doc.items() if k in ATTENDEE_FIELDS and v not in (None, "", [])}
    attendee_doc_id = f"{payload.conference_id}:{attendee_id}"
    previous: dict[str, Any] | None = None
    if token:
        doc["access_token_sha256"] = hashlib.sha256(token.encode()).hexdigest()
    elif identity:
        previous = await es_call(
            "read_attendee",
            lambda: es.get(
                index="attendees",
                id=attendee_doc_id,
                source_includes=["access_token_sha256", "resume_text"],
            )["_source"],
        )
        doc["access_token_sha256"] = previous["access_token_sha256"]
    # An update without a new resume must not accidentally erase the attendee's private resume.
    if "resume_text" not in doc and previous and previous.get("resume_text"):
        doc["resume_text"] = previous["resume_text"]
    await es_call(
        "save_attendee",
        lambda: es.index(index="attendees", id=attendee_doc_id, document=doc, refresh="wait_for"),
    )
    recommendation_profile = doc | {
        "conference_id": payload.conference_id,
        "attendee_id": attendee_id,
    }
    ranked = await ranked_talks(recommendation_profile, size=SCHEDULE_CANDIDATE_LIMIT)
    recommendations = ranked[:20]
    schedules = build_recommended_schedules(ranked)
    people = (
        await recommended_people(recommendation_profile)
        if payload.discovery_opt_in
        else {"similar": [], "matches": []}
    )
    result: dict[str, Any] = {
        "attendee_id": attendee_id,
        "recommendations": {
            "talks": recommendations,
            "schedules": schedules,
            "attendees": people,
        },
        # What the résumé contributed, so the form can show "We picked up: ..." for editing.
        # Derived fields only; the raw resume_text is never echoed back.
        "resume_profile": resume_profile.model_dump(),
    }
    if token:
        result["attendee_token"] = f"{payload.conference_id}:{attendee_id}:{token}"
    return result


@app.post("/parse-resume")
async def parse_resume_preview(resume: UploadFile = File(...)) -> dict[str, Any]:
    """Preview what a résumé contributes to the profile. Stores nothing; same limits as save."""
    text = await read_resume_upload(resume)
    profile = await parse_resume_traced(text) if text.strip() else ResumeProfile()
    return {"resume_profile": profile.model_dump(), "is_linkedin_pdf": is_linkedin_pdf_text(text)}


async def claimed_profile(
    conference_id: str, profile_id: str | None, identity: tuple[str, str] | None
) -> dict[str, Any]:
    """Load a profile only for its bearer token; profile IDs are not credentials."""
    if not identity or identity[0] != conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    if profile_id and profile_id != identity[1]:
        raise HTTPException(403, "A profile can only be read by its owner")
    return await es_call(
        "read_recommendation_profile",
        lambda: es.get(
            index="attendees",
            id=f"{conference_id}:{identity[1]}",
            source_includes=[
                "conference_id",
                "attendee_id",
                "profile",
                "looking_for",
                "can_help_with",
                "skills",
                "interests",
                "blockout_times",
                "discovery_opt_in",
            ],
        )["_source"],
    )


@app.get("/conferences/{conference_id}/talks/recommend")
async def get_talk_recommendations(
    conference_id: str,
    profile_id: str | None = Query(default=None),
    identity: tuple[str, str] | None = Depends(attendee_claim),
) -> dict[str, Any]:
    profile = await claimed_profile(conference_id, profile_id, identity)
    return {"talks": await recommended_talks(profile)}


@app.get("/conferences/{conference_id}/schedules")
async def get_recommended_schedules(
    conference_id: str,
    profile_id: str | None = Query(default=None),
    identity: tuple[str, str] | None = Depends(attendee_claim),
) -> dict[str, Any]:
    """Return the three best relevance-weighted, conflict-free schedule choices."""
    profile = await claimed_profile(conference_id, profile_id, identity)
    return {"schedules": await recommended_schedules(profile)}


@app.get("/conferences/{conference_id}/people/recommend")
async def get_people_recommendations(
    conference_id: str,
    profile_id: str | None = Query(default=None),
    identity: tuple[str, str] | None = Depends(attendee_claim),
) -> dict[str, Any]:
    profile = await claimed_profile(conference_id, profile_id, identity)
    if not profile.get("discovery_opt_in"):
        return {"similar": [], "matches": []}
    return await recommended_people(profile)


async def conference_talk(conference_id: str, talk_id: str) -> dict[str, Any]:
    return await es_call(
        "read_talk",
        lambda: es.get(
            index="talks",
            id=f"{conference_id}:{talk_id}",
            source_includes=["title", "abstract"],
        )["_source"],
    )


@app.get("/conferences/{conference_id}/talks/{talk_id}/attendees")
async def attendees_for_talk(
    conference_id: str,
    talk_id: str,
    x_organizer_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Organizer-only Q4: names are limited to attendees who opted into discovery."""
    await verify_organizer(conference_id, x_organizer_token)
    talk = await conference_talk(conference_id, talk_id)
    query_text = f"{talk.get('title', '')}. {talk.get('abstract', '')}".strip()
    hits = await es_call(
        "recommend_talk_attendees",
        lambda: es.search(
            index="attendees",
            size=10,
            source=SAFE_ATTENDEE_SOURCE,
            query={
                "bool": {
                    "must": [{"semantic": {"field": "profile", "query": query_text}}],
                    "filter": [
                        {"term": {"conference_id": conference_id}},
                        {"term": {"discovery_opt_in": True}},
                    ],
                }
            },
        )["hits"]["hits"],
    )
    return {"attendees": _hits_with_reason(hits, "profile")}


@app.get("/conferences/{conference_id}/talks/{talk_id}/related-archive")
async def related_archive_talks(
    conference_id: str,
    talk_id: str,
    identity: tuple[str, str] | None = Depends(attendee_claim),
) -> dict[str, Any]:
    """Q5: retrieve related recordings from the read-only past-talk archive."""
    if not identity or identity[0] != conference_id:
        raise HTTPException(401, "Valid attendee token for this conference required")
    talk = await conference_talk(conference_id, talk_id)
    query_text = f"{talk.get('title', '')}. {talk.get('abstract', '')}".strip()
    hits = await es_call(
        "recommend_archive_talks",
        lambda: es.search(
            index="talks-archive",
            size=5,
            source=["title", "conference", "year", "url", "video_url"],
            query={"semantic": {"field": "semantic_content", "query": query_text}},
        )["hits"]["hits"],
    )
    return {"talks": [hit["_source"] for hit in hits]}


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
            "read_recipient",
            lambda: es.get(
                index="attendees", id=recipient_doc_id, source_includes=["discovery_opt_in"]
            )["_source"],
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
        lambda: es.get(
            index="attendees",
            id=f"{payload.conference_id}:{identity[1]}",
            source_includes=["email", "linkedin_url", "resume_text"],
        )["_source"],
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
    x_organizer_token: str | None = Header(default=None),
) -> dict[str, Any]:
    await verify_organizer(conference_id, x_organizer_token)
    if bool(source_url) == bool(file):
        raise HTTPException(422, "Provide exactly one of source_url or file")
    content: bytes | None = None
    if file:
        if file.content_type not in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/png",
            "image/jpeg",
            "image/webp",
        }:
            raise HTTPException(415, "Supported uploads: PDF, DOCX, PNG, JPEG, WEBP")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds 10 MiB")
    with tracer.start_as_current_span("parse_schedule") as span:
        span.set_attribute("conference.id", conference_id)
        span.set_attribute("schedule.source_type", "url" if source_url else "file")
        try:
            parsed = await run_in_threadpool(
                parse_schedule,
                conference_id=conference_id,
                source_url=str(source_url) if source_url else None,
                content=content,
                content_type=file.content_type if file else None,
                filename=file.filename if file else None,
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            logger.warning(
                "schedule_parse_failed conference_id=%s error=%s", conference_id, type(exc).__name__
            )
            raise HTTPException(502, "Schedule parser could not produce a draft") from None
        span.set_attribute("schedule.talk_count", len(parsed["talks"]))
    return {"conference_id": conference_id, **parsed}


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
    payload: ConfirmSchedule, x_organizer_token: str | None = Header(default=None)
) -> dict[str, Any]:
    await verify_organizer(payload.conference_id, x_organizer_token)
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
