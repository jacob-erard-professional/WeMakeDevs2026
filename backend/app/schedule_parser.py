import asyncio
import base64
import ipaddress
import io
import json
import socket
from urllib.parse import urlparse

import httpx
from docx import Document
from pypdf import PdfReader

from .config import Settings
from .observability import tracer
from .schemas import Schedule

MAX_REMOTE_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

EXTRACTION_PROMPT = """Extract the conference schedule from the supplied content. Return only JSON with this shape:
{"title":"Conference Schedule","timezone":"America/Denver","warnings":[],"talks":[{"talk_id":"stable short id","title":"...","abstract":"...","tags":[],"speaker_names":[],"start_time":"ISO-8601 with timezone offset","end_time":"ISO-8601 with timezone offset","room":"..."}]}
Use the schedule's stated timezone. If none is stated, use UTC and add a warning that timezone was assumed. Never invent missing times: omit entries that lack a usable start or end time. Preserve all provided talk details. The organizer will review this draft."""


async def parse_schedule(
    settings: Settings,
    *,
    content: bytes | None = None,
    content_type: str | None = None,
    source_url: str | None = None,
) -> Schedule:
    with tracer.start_as_current_span("schedule.parse") as span:
        if source_url:
            content, content_type = await fetch_public_schedule(
                source_url, settings.schedule_max_upload_bytes
            )
            span.set_attribute("schedule.parser", "url")
        elif content_type in IMAGE_TYPES:
            span.set_attribute("schedule.parser", "openrouter_vision")
        else:
            span.set_attribute("schedule.parser", "openrouter_text")
        if content is None or content_type is None:
            raise ValueError("provide a schedule URL or file")
        if len(content) > settings.schedule_max_upload_bytes:
            raise ValueError("schedule source exceeds the configured size limit")

        if content_type == "application/pdf":
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
            )
            if not text.strip():
                raise ValueError("PDF contains no extractable text; upload a page image instead")
            parsed = await ask_openrouter(settings, text)
        elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            document = Document(io.BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            if not text.strip():
                raise ValueError("document contains no readable schedule text")
            parsed = await ask_openrouter(settings, text)
        elif content_type in IMAGE_TYPES:
            data_url = f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
            parsed = await ask_openrouter(settings, data_url, image=True)
        elif content_type in {"text/html", "text/plain"}:
            text = content.decode("utf-8", errors="replace")[:100_000]
            if content_type == "text/html":
                from bs4 import BeautifulSoup

                text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
            parsed = await ask_openrouter(settings, text)
        else:
            raise ValueError("supported inputs are PDF, DOCX, PNG, JPEG, WEBP, HTML, or plain text")

        span.set_attribute("schedule.talk_count", len(parsed.get("talks", [])))
        return Schedule.model_validate(parsed)


async def ask_openrouter(settings: Settings, content: str, *, image: bool = False) -> dict:
    user_content: object
    if image:
        user_content = [
            {"type": "text", "text": "Extract the schedule shown in this image."},
            {"type": "image_url", "image_url": {"url": content}},
        ]
    else:
        user_content = f"Extract the schedule from this content:\n\n{content[:100_000]}"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    payload = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    with tracer.start_as_current_span("openrouter.schedule_extraction") as span:
        span.set_attribute("gen_ai.system", "openrouter")
        span.set_attribute("gen_ai.request.model", settings.openrouter_model)
        span.set_attribute("schedule.input_type", "image" if image else "text")
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=5)) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        message = result["choices"][0]["message"]["content"]
        if not message:
            raise ValueError("schedule parser returned an empty result")
        return json.loads(message)


async def fetch_public_schedule(url: str, max_bytes: int) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise ValueError("schedule URLs must use HTTPS and cannot include credentials")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("schedule URL host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("schedule URL must resolve only to public IP addresses")
    max_bytes = min(max_bytes, MAX_REMOTE_BYTES)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15, connect=5), follow_redirects=False, max_redirects=0
    ) as client:
        async with client.stream(
            "GET", url, headers={"Accept": "text/html,application/pdf,image/*,text/plain"}
        ) as response:
            response.raise_for_status()
            if int(response.headers.get("content-length", "0")) > max_bytes:
                raise ValueError("schedule URL response exceeds the size limit")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError("schedule URL response exceeds the size limit")
            content_type = (
                response.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
            )
            return bytes(body), content_type
