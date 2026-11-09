"""Schedule importer used by the organizer preview endpoint.

`parse_schedule` turns an organizer-supplied URL or upload into a reviewable draft. It is
stateless and never writes to the live `talks` index; confirmation is a separate organizer action.

Pipeline (see `docs/schedule-formats.md`):

    url ──► rewrite (Sched → /all.ics, Sessionize → view/All, webcal → https)
        ──► safe_fetch (SSRF-guarded, see `schedule_fetch`) ─┐
    upload ──────────────────────────────────────────────────┴─► detect(body) ─► adapter
    deterministic adapters: ics │ sessionize │ pretalx/frab JSON │ frab XML   (no LLM)
    LLM fallback (OPENAI_SCHEDULE_MODEL): html text │ docx text │ pdf │ image
        ──► normalize (tz, end > start, dedupe) ──► {talks, warnings, source_format, timezone}

URL retrieval happens on this server, so the SSRF policy lives in `schedule_fetch`. The model
is never handed a URL to fetch.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from app import schedule_adapters as adapters
from app.schedule_fetch import Fetched, safe_fetch

DEFAULT_SCHEDULE_MODEL = "gpt-5.4-mini"
MAX_LLM_TEXT_CHARS = 120_000

SCHEDULE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "talks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "abstract": {"type": ["string", "null"]},
                    "speakers": {"type": "array", "items": {"type": "string"}},
                    "room": {"type": ["string", "null"]},
                    "track": {"type": "array", "items": {"type": "string"}},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                },
                "required": [
                    "title",
                    "abstract",
                    "speakers",
                    "room",
                    "track",
                    "start_time",
                    "end_time",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["talks", "warnings"],
}

ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/calendar",
    "application/json",
    "application/xml",
    "text/xml",
    "text/html",
    "text/plain",
    "application/octet-stream",
}

SESSIONIZE_API_RE = re.compile(r"sessionize\.com/api/v2/([A-Za-z0-9]+)/view/", re.IGNORECASE)
PRETALX_EXPORT_RE = re.compile(r"/schedule/export/schedule\.(json|xml|ics)$")


class ScheduleParseError(ValueError):
    """A user-facing reason the draft could not be produced."""


# ---------------------------------------------------------------------------- detection


def rewrite_url(url: str) -> str:
    """Point known hosts at their structured export before fetching."""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme.lower() in {"webcal", "https", "http"} else parts.scheme
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if host.endswith(".sched.com"):
        return urlunsplit((scheme, host, "/all.ics", "", ""))
    match = SESSIONIZE_API_RE.search(url)
    if host.endswith("sessionize.com") and match:
        return urlunsplit((scheme, host, f"/api/v2/{match.group(1)}/view/All", "", ""))
    if host == "pretalx.com" and not PRETALX_EXPORT_RE.search(path):
        slug = path.strip("/").split("/")[0]
        if slug and slug != "api":
            return urlunsplit((scheme, host, f"/{slug}/schedule/export/schedule.json", "", ""))
    return urlunsplit((scheme, host, path, parts.query, ""))


def sniff_format(body: bytes, content_type: str | None = None) -> str:
    """Classify bytes by magic/structure; Content-Type is only a tiebreaker for text."""
    head = body[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    lower = head.lower()
    if head.startswith(b"BEGIN:VCALENDAR"):
        return "ics"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"PK\x03\x04") and b"word/" in body[:65536]:
        return "docx"
    if head.startswith(b"document.write("):
        return "sessionize_embed"
    if head.startswith((b"{", b"[")):
        return "json"
    if lower.startswith(b"<?xml") or lower.startswith(b"<schedule"):
        return "xml"
    if b"<html" in lower or b"<!doctype html" in lower or b"<body" in lower:
        return "html"
    if content_type == "text/html":
        return "html"
    if content_type in {"application/xml", "text/xml"}:
        return "xml"
    if content_type == "text/plain":
        return "text"
    return "unknown"


def find_structured_link(html_body: str, base_url: str | None) -> str | None:
    """An HTML page may point at a structured export; follow at most one such hop."""
    match = SESSIONIZE_API_RE.search(html_body)
    if match:
        return f"https://sessionize.com/api/v2/{match.group(1)}/view/All"
    for pattern in (
        r"""href=["']([^"']*/all\.ics)["']""",
        r"""href=["']([^"']*/schedule/export/schedule\.json)["']""",
        r"""<link[^>]+type=["']text/calendar["'][^>]+href=["']([^"']+)["']""",
    ):
        found = re.search(pattern, html_body, re.IGNORECASE)
        if found:
            link = found.group(1)
            if link.startswith("//"):
                return "https:" + link
            if link.startswith("/") and base_url:
                parts = urlsplit(base_url)
                return urlunsplit((parts.scheme, parts.netloc, link, "", ""))
            return link
    return None


# ---------------------------------------------------------------------------- normalize


def _aware(value: Any, tz: ZoneInfo | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz) if tz else None
    return parsed


def normalize_talks(
    talks: list[dict[str, Any]], warnings: list[str], tz_name: str | None
) -> list[dict[str, Any]]:
    """Make every talk match the draft contract; drop the ones that cannot be made valid."""
    tz = adapters.zone(tz_name)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    dropped_time = 0
    dropped_order = 0
    duplicates = 0
    for talk in talks:
        title = str(talk.get("title") or "").strip()
        if not title:
            continue
        start = _aware(talk.get("start_time"), tz)
        end = _aware(talk.get("end_time"), tz)
        if start is None or end is None:
            dropped_time += 1
            continue
        if end <= start:
            dropped_order += 1
            continue
        room = str(talk.get("room") or "").strip() or None
        key = (title.lower(), start.isoformat(), (room or "").lower())
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        speakers = [str(s).strip() for s in talk.get("speakers") or [] if str(s).strip()]
        tracks = [str(t).strip() for t in talk.get("track") or [] if str(t).strip()]
        abstract = adapters.strip_html(talk.get("abstract")) if talk.get("abstract") else None
        out.append(
            {
                "title": title,
                "abstract": abstract,
                "speakers": speakers,
                "room": room,
                "track": tracks,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }
        )
    if dropped_time:
        reason = (
            "no conference timezone was given, so floating times could not be resolved"
            if tz is None
            else "their times were missing or unparseable"
        )
        warnings.append(f"Dropped {dropped_time} sessions because {reason}")
    if dropped_order:
        warnings.append(f"Dropped {dropped_order} sessions whose end time was not after the start")
    if duplicates:
        warnings.append(f"Removed {duplicates} duplicate sessions (same title, start and room)")
    return out


# ---------------------------------------------------------------------------- LLM fallback


class _VisibleText(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "svg", "head"}
    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br", "section", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(body: bytes) -> str:
    parser = _VisibleText()
    parser.feed(body.decode("utf-8", errors="replace"))
    text = "".join(parser.parts)
    text = re.sub(r"[ \xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def docx_to_text(body: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(body))
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            lines.append("\t".join(cell.text.strip() for cell in row.cells))
    return "\n".join(lines)


def _llm_instructions(conference_id: str, tz_name: str | None, source_url: str | None) -> str:
    tz_line = (
        f"The conference timezone is {tz_name}. Times in the source are local to that zone unless "
        "an offset is stated; emit ISO-8601 with the correct offset for that zone and date."
        if tz_name
        else "No conference timezone is known. Only emit a time if the source states its zone; "
        "otherwise add a warning saying the timezone is missing instead of guessing."
    )
    return (
        "Extract the conference schedule into the requested JSON. This is a draft for human "
        "review, not a publication. Include only real sessions (talks, workshops, keynotes, "
        "panels, lightning talks) with a title and timezone-aware ISO-8601 start_time and "
        "end_time. Do not include breaks, lunch, registration, sponsor or networking slots; "
        "mention how many you skipped in warnings. Speaker and title may share one string in "
        "either order; separate them. Dates often appear only in a day header above the rows. "
        "Never invent abstracts or speakers. Put ambiguity in warnings. "
        f"{tz_line} Conference id: {conference_id}."
        + (f" Source URL (for context only): {source_url}" if source_url else "")
    )


def llm_extract(
    *,
    conference_id: str,
    fmt: str,
    body: bytes,
    content_type: str | None,
    filename: str | None,
    tz_name: str | None,
    source_url: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    parts: list[dict[str, Any]] = [
        {"type": "input_text", "text": _llm_instructions(conference_id, tz_name, source_url)}
    ]
    if fmt.startswith("image/"):
        encoded = base64.b64encode(body).decode("ascii")
        parts.append({"type": "input_image", "image_url": f"data:{fmt};base64,{encoded}"})
    elif fmt == "pdf":
        encoded = base64.b64encode(body).decode("ascii")
        parts.append(
            {
                "type": "input_file",
                "filename": filename or "schedule.pdf",
                "file_data": f"data:application/pdf;base64,{encoded}",
            }
        )
    else:
        if fmt == "docx":
            text = docx_to_text(body)
        elif fmt == "html":
            text = html_to_text(body)
        else:
            text = body.decode("utf-8", errors="replace")
        if len(text) > MAX_LLM_TEXT_CHARS:
            text = text[:MAX_LLM_TEXT_CHARS]
            warnings.append(
                f"The source was truncated to {MAX_LLM_TEXT_CHARS} characters before extraction; "
                "later sessions may be missing"
            )
        if not text.strip():
            raise ScheduleParseError("The source contains no readable text")
        parts.append({"type": "input_text", "text": f"Schedule content:\n\n{text}"})
    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_SCHEDULE_MODEL", DEFAULT_SCHEDULE_MODEL),
        input=[{"role": "user", "content": parts}],
        text={
            "format": {
                "type": "json_schema",
                "name": "schedule",
                "strict": True,
                "schema": SCHEDULE_SCHEMA,
            }
        },
        timeout=90,
    )
    result = json.loads(response.output_text)
    if not isinstance(result.get("talks"), list) or not isinstance(result.get("warnings"), list):
        raise ValueError("Parser returned an invalid schedule draft")
    return result


# ---------------------------------------------------------------------------- entry point


def parse_bytes(
    *,
    conference_id: str,
    body: bytes,
    content_type: str | None,
    filename: str | None,
    tz_name: str | None,
    source_url: str | None,
) -> dict[str, Any]:
    fmt = sniff_format(body, content_type)
    warnings: list[str] = []
    talks: list[dict[str, Any]]
    resolved_tz = tz_name
    if fmt == "sessionize_embed":
        raise ScheduleParseError(
            "This Sessionize endpoint serves an embed widget; use a JSON endpoint "
            "(sessionize.com/api/v2/<id>/view/All)"
        )
    if fmt == "unknown":
        raise ScheduleParseError(
            "Unrecognized schedule format; supported: ics, Sessionize JSON, pretalx/frab JSON "
            "or XML, HTML, PDF, DOCX, PNG, JPEG, WEBP"
        )
    if fmt in {"ics", "json", "xml"}:
        if fmt == "ics":
            draft = adapters.parse_ics(body, tz_name)
        elif fmt == "json":
            draft = adapters.parse_json_any(body, tz_name)
            fmt = (
                "frab_json"
                if '"schedule"' in body[:4096].decode("utf-8", "replace")
                else ("sessionize")
            )
        else:
            draft = adapters.parse_frab_xml(body, tz_name)
            fmt = "frab_xml"
        warnings.extend(draft.warnings)
        resolved_tz = draft.timezone or tz_name
        talks = draft.talks
    else:
        result = llm_extract(
            conference_id=conference_id,
            fmt=fmt,
            body=body,
            content_type=content_type,
            filename=filename,
            tz_name=tz_name,
            source_url=source_url,
            warnings=warnings,
        )
        warnings.extend(str(w) for w in result["warnings"])
        talks = result["talks"]
        fmt = f"llm_{fmt.replace('image/', 'image_')}"
    normalized = normalize_talks(talks, warnings, resolved_tz)
    if resolved_tz:
        warnings.insert(0, f"Times resolved using timezone {resolved_tz}")
    elif normalized:
        warnings.insert(0, "No conference timezone was given; times are shown as the source states")
    return {
        "talks": normalized,
        "warnings": warnings,
        "source_format": fmt,
        "timezone": resolved_tz,
    }


def parse_schedule(
    *,
    conference_id: str,
    source_url: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    filename: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Produce a schedule draft from an organizer-provided URL or document.

    URLs are fetched here under the SSRF policy in `schedule_fetch`, then handled exactly like
    an upload. `timezone` is the conference's IANA zone used for floating times.
    """
    if source_url:
        target = rewrite_url(source_url)
        fetched: Fetched = safe_fetch(target)
        body, ctype, final_url = fetched.body, fetched.content_type, fetched.url
        if sniff_format(body, ctype) == "html":
            link = find_structured_link(body[:1_000_000].decode("utf-8", "replace"), final_url)
            if link:
                hop = safe_fetch(rewrite_url(link))
                if sniff_format(hop.body, hop.content_type) in {"ics", "json", "xml"}:
                    body, ctype, final_url = hop.body, hop.content_type, hop.url
        result = parse_bytes(
            conference_id=conference_id,
            body=body,
            content_type=ctype,
            filename=None,
            tz_name=timezone,
            source_url=final_url,
        )
        result["source_url"] = final_url
        return result
    if content is None:
        raise ValueError("A schedule URL or file is required")
    return parse_bytes(
        conference_id=conference_id,
        body=content,
        content_type=content_type,
        filename=filename,
        tz_name=timezone,
        source_url=None,
    )
