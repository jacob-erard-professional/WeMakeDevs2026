import base64
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import qrcode
from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import ValidationError

from .config import Settings, get_settings
from .elasticsearch import (
    DRAFTS_INDEX,
    create_client,
    ensure_indices,
    get_draft,
    publish_schedule,
    save_draft,
)
from .observability import configure_observability, error_counter, logger, request_counter, tracer
from .schedule_parser import parse_schedule
from .schemas import ConfirmScheduleRequest, Schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_observability(settings.otel_service_name)
    client = create_client(settings)
    app.state.settings = settings
    app.state.elasticsearch = client
    try:
        await ensure_indices(client)
        yield
    finally:
        await client.close()


app = FastAPI(title="WeMakeDevs Conference API", version="0.1.0", lifespan=lifespan)


async def organizer_auth(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    expected = settings.organizer_api_key
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="valid organizer bearer token required")


def get_es(request: Request) -> AsyncElasticsearch:
    return request.app.state.elasticsearch


def request_telemetry(operation: str, outcome: str) -> None:
    attributes = {"operation": operation, "outcome": outcome}
    request_counter.add(1, attributes)
    if outcome == "error":
        error_counter.add(1, attributes)


@app.exception_handler(ValidationError)
async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors(include_input=False)})


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, str]:
    try:
        await request.app.state.elasticsearch.ping()
    except Exception as exc:
        logger.warning(
            "health check failed: dependency=elasticsearch error_type=%s", type(exc).__name__
        )
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable") from exc
    return {"status": "ok"}


@app.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload-schedule", status_code=201, dependencies=[Depends(organizer_auth)])
async def upload_schedule(
    request: Request,
    conference_id: str = Form(min_length=1, max_length=200),
    source_url: str | None = Form(default=None, max_length=2000),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
    client: AsyncElasticsearch = Depends(get_es),
) -> dict:
    operation = "upload_schedule"
    with tracer.start_as_current_span("http.upload_schedule") as span:
        span.set_attribute("conference.id", conference_id)
        try:
            if bool(source_url) == bool(file):
                raise HTTPException(
                    status_code=400,
                    detail="provide exactly one of source_url or file",
                )
            content = None
            content_type = None
            if file:
                content = await file.read(settings.schedule_max_upload_bytes + 1)
                if len(content) > settings.schedule_max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="schedule file exceeds the upload size limit",
                    )
                content_type = (
                    (file.content_type or "application/octet-stream")
                    .split(";", maxsplit=1)[0]
                    .lower()
                )
            try:
                schedule = await parse_schedule(
                    settings, content=content, content_type=content_type, source_url=source_url
                )
            except (ValueError, ValidationError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except Exception as exc:
                logger.warning("schedule extraction failed: error_type=%s", type(exc).__name__)
                raise HTTPException(status_code=502, detail="schedule extraction failed") from exc

            now = datetime.now(timezone.utc)
            draft_id = str(uuid4())
            expires_at = now + timedelta(hours=settings.schedule_draft_ttl_hours)
            draft = {
                "draft_id": draft_id,
                "schedule": schedule.model_dump(mode="json"),
                "status": "review",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            try:
                await save_draft(client, conference_id, draft)
            except Exception as exc:
                logger.exception(
                    "schedule draft persistence failed: error_type=%s", type(exc).__name__
                )
                raise HTTPException(
                    status_code=503, detail="could not save schedule draft"
                ) from exc
            span.set_attribute("schedule.draft_id", draft_id)
            span.set_attribute("schedule.talk_count", len(schedule.talks))
            request_telemetry(operation, "success")
            return {
                "draft_id": draft_id,
                "conference_id": conference_id,
                "status": "review",
                "expires_at": expires_at.isoformat(),
                **schedule.model_dump(mode="json"),
            }
        except HTTPException:
            request_telemetry(operation, "error")
            raise
        except Exception:
            request_telemetry(operation, "error")
            raise


@app.post("/confirm-schedule", dependencies=[Depends(organizer_auth)])
async def confirm_schedule(
    payload: ConfirmScheduleRequest,
    settings: Settings = Depends(get_settings),
    client: AsyncElasticsearch = Depends(get_es),
) -> dict:
    operation = "confirm_schedule"
    with tracer.start_as_current_span("http.confirm_schedule") as span:
        span.set_attribute("conference.id", payload.conference_id)
        span.set_attribute("schedule.draft_id", payload.draft_id)
        try:
            try:
                draft = await get_draft(client, payload.draft_id, payload.conference_id)
            except Exception as exc:
                logger.exception(
                    "schedule draft lookup failed: error_type=%s", type(exc).__name__
                )
                raise HTTPException(
                    status_code=503, detail="could not load schedule draft"
                ) from exc
            if not draft:
                raise HTTPException(status_code=404, detail="schedule draft not found")
            expires_at = datetime.fromisoformat(draft["expires_at"].replace("Z", "+00:00"))
            if expires_at <= datetime.now(timezone.utc):
                raise HTTPException(status_code=410, detail="schedule draft has expired")
            schedule = (
                Schedule.model_validate(draft["schedule"])
                if draft.get("status") == "confirmed"
                else payload.schedule or Schedule.model_validate(draft["schedule"])
            )
            schedule_id = payload.draft_id
            join_url = f"{settings.public_base_url.rstrip('/')}/join/{payload.conference_id}"
            if draft.get("status") != "confirmed":
                try:
                    await publish_schedule(
                        client,
                        payload.conference_id,
                        schedule_id,
                        schedule.model_dump(mode="json"),
                    )
                    with tracer.start_as_current_span(
                        "elasticsearch.confirm_schedule_draft"
                    ) as es_span:
                        es_span.set_attribute("db.system", "elasticsearch")
                        es_span.set_attribute("db.index", DRAFTS_INDEX)
                        await client.update(
                            index=DRAFTS_INDEX,
                            id=payload.draft_id,
                            doc={
                                "status": "confirmed",
                                "schedule": schedule.model_dump(mode="json"),
                                "schedule_id": schedule_id,
                            },
                            refresh="wait_for",
                        )
                except Exception as exc:
                    logger.exception(
                        "schedule publication failed: error_type=%s", type(exc).__name__
                    )
                    raise HTTPException(
                        status_code=503, detail="schedule could not be published"
                    ) from exc
            span.set_attribute("schedule.talk_count", len(schedule.talks))
            with tracer.start_as_current_span("schedule.generate_join_qr") as qr_span:
                qr_span.set_attribute("conference.id", payload.conference_id)
                qr = qrcode.make(join_url)
                image = BytesIO()
                qr.save(image, format="PNG")
            request_telemetry(operation, "success")
            return {
                "conference_id": payload.conference_id,
                "schedule_id": schedule_id,
                "status": "confirmed",
                "talk_count": len(schedule.talks),
                "join_url": join_url,
                "qr_code_data_uri": (
                    "data:image/png;base64," + base64.b64encode(image.getvalue()).decode("ascii")
                ),
            }
        except HTTPException:
            request_telemetry(operation, "error")
            raise
        except Exception:
            request_telemetry(operation, "error")
            raise


FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz")
