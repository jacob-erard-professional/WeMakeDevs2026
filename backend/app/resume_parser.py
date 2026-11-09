"""Résumé text extraction and structured profile parsing.

Two stages, both stateless:

1. `extract_resume_text` turns an uploaded PDF/DOCX/TXT into plain text. Raw files are never
   persisted; only this text is.
2. `parse_resume` turns that text into a `ResumeProfile` (headline, skills, interests, ...) that
   fills the attendee's empty profile fields so Elasticsearch matching has more to work with.
   A LinkedIn "Save to PDF" export is recognised and parsed deterministically; everything else
   (and the LinkedIn export too, for the free-text fields) goes through OpenAI structured
   outputs. Without `OPENAI_API_KEY`, or when the call fails, the result is an empty profile
   and the caller still stores the raw text.

LinkedIn profile *pages* are never fetched: that violates LinkedIn's terms, the pages sit behind
an auth wall and the requests get blocked. A `linkedin_url` is stored as a link only.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("conference_api.resume")

MAX_RESUME_CHARS = 50_000
# Enough for any realistic résumé; keeps prompt cost bounded on pathological uploads.
MAX_LLM_INPUT_CHARS = 30_000
MAX_SKILLS = 30
MAX_INTERESTS = 15
MAX_KEYWORD_CHARS = 60
MAX_HEADLINE_CHARS = 300
MAX_SENTENCE_CHARS = 2_000

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnsupportedResumeType(ValueError):
    """The upload is not TXT, PDF or DOCX."""


class ResumeProfile(BaseModel):
    """Profile fields distilled from a résumé. Every field may be empty."""

    headline: str = ""
    skills: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    working_on: str = ""
    can_help_with: str = ""
    summary: str = ""

    def is_empty(self) -> bool:
        return not any(
            (
                self.headline,
                self.skills,
                self.interests,
                self.working_on,
                self.can_help_with,
                self.summary,
            )
        )


# --- Text extraction ---------------------------------------------------------------------------


def normalize_whitespace(text: str) -> str:
    """Collapse runs of blanks, trim line ends and squash blank-line runs; keep line structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return collapsed.strip()[:MAX_RESUME_CHARS]


def extract_resume_text(content: bytes, content_type: str | None, filename: str | None) -> str:
    """Extract text only; raw résumé files are deliberately never persisted."""
    suffix = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if content_type == "text/plain" or suffix == "txt":
        return normalize_whitespace(content.decode("utf-8", errors="replace"))
    if content_type == "application/pdf" or suffix == "pdf":
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(content)).pages
        return normalize_whitespace("\n".join(page.extract_text() or "" for page in pages))
    if content_type == DOCX_CONTENT_TYPE or suffix == "docx":
        from docx import Document

        document = Document(io.BytesIO(content))
        chunks = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                chunks.append(" | ".join(cell for cell in cells if cell))
        return normalize_whitespace("\n".join(chunks))
    raise UnsupportedResumeType("Resume upload must be TXT, PDF, or DOCX")


# --- Contact-detail scrubbing ------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S*[^\s.,;:)]|\b[\w-]+\.(?:com|io|dev|org|net|ai|me|co)(?:/\S*[^\s.,;:)])?",
    re.IGNORECASE,
)
# Phone numbers: 7+ digits with optional separators, optional country code / parentheses.
_PHONE_RE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().-]{6,}\d(?![\w/])")
_WS_PUNCT_RE = re.compile(r"\s+([,;:.])")


def strip_contact_details(text: str) -> str:
    """Remove emails, URLs and phone numbers so they never land in matchable profile fields."""
    cleaned = _EMAIL_RE.sub("", text)
    cleaned = _URL_RE.sub("", cleaned)
    cleaned = _PHONE_RE.sub("", cleaned)
    cleaned = _WS_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)|\[\s*\]", "", cleaned)
    return re.sub(r" {2,}", " ", cleaned).strip(" ,;:|-")


def _clean_sentence(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return strip_contact_details(" ".join(value.split()))[:limit].strip()


def clean_keywords(values: Iterable[Any], limit: int) -> list[str]:
    """Lowercase, strip contact details, dedupe (order preserved) and cap the list."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        keyword = strip_contact_details(" ".join(value.split())).lower()[:MAX_KEYWORD_CHARS]
        keyword = keyword.strip(" ,;:.")
        if keyword and keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
        if len(result) >= limit:
            break
    return result


def sanitize_profile(raw: Mapping[str, Any]) -> ResumeProfile:
    """Normalise any model/deterministic output into a bounded, contact-free profile."""
    return ResumeProfile(
        headline=_clean_sentence(raw.get("headline"), MAX_HEADLINE_CHARS),
        skills=clean_keywords(raw.get("skills") or [], MAX_SKILLS),
        interests=clean_keywords(raw.get("interests") or [], MAX_INTERESTS),
        working_on=_clean_sentence(raw.get("working_on"), MAX_SENTENCE_CHARS),
        can_help_with=_clean_sentence(raw.get("can_help_with"), MAX_SENTENCE_CHARS),
        summary=_clean_sentence(raw.get("summary"), MAX_SENTENCE_CHARS),
    )


# --- LinkedIn "Save to PDF" export -------------------------------------------------------------

_LINKEDIN_SIDEBAR_HEADERS = {
    "Contact",
    "Top Skills",
    "Languages",
    "Certifications",
    "Honors-Awards",
    "Honors and Awards",
    "Publications",
    "Patents",
}
_LINKEDIN_MAIN_HEADERS = {"Summary", "Experience", "Education"}
_LINKEDIN_HEADERS = _LINKEDIN_SIDEBAR_HEADERS | _LINKEDIN_MAIN_HEADERS
_LINKEDIN_DATE_RE = re.compile(r"^(?:\w+ )?\d{4} ?- ?(?:(?:\w+ )?\d{4}|Present)\b", re.IGNORECASE)
_LINKEDIN_PAGE_RE = re.compile(r"^Page \d+ of \d+$", re.IGNORECASE)


def is_linkedin_pdf_text(text: str) -> bool:
    """Heuristic for the PDF LinkedIn generates from profile -> More -> Save to PDF."""
    if "linkedin.com/in/" not in text.lower():
        return False
    headers = {line.strip() for line in text.split("\n")} & _LINKEDIN_HEADERS
    return len(headers) >= 3


def _linkedin_sections(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Split export lines into header -> body, plus the name block (name/headline/location).

    pypdf emits the sidebar (Contact, Top Skills, Languages, ...) first; the name block is glued
    to the end of the last sidebar section, right before Summary/Experience. The sidebar list
    items are recognisable (contact lines, or at most three Top Skills), so the name block is
    whatever remains of that section once its list items are dropped.
    """
    sections: dict[str, list[str]] = {}
    current = ""
    last_sidebar = ""
    for line in lines:
        if _LINKEDIN_PAGE_RE.match(line):
            continue
        if line in _LINKEDIN_HEADERS:
            current = line
            if line in _LINKEDIN_SIDEBAR_HEADERS and not sections.keys() & _LINKEDIN_MAIN_HEADERS:
                last_sidebar = line
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    body = sections.get(last_sidebar, [])
    if last_sidebar == "Top Skills":
        sections["Top Skills"], name_block = body[:3], body[3:]
    elif last_sidebar == "Contact":
        name_block = [line for line in body if not _is_contact_line(line)]
    elif last_sidebar:
        name_block = body[-3:]
    else:
        name_block = sections.get("", [])
    return sections, name_block


def _is_contact_line(line: str) -> bool:
    return bool(
        _EMAIL_RE.search(line)
        or _URL_RE.search(line)
        or _PHONE_RE.search(line)
        or line.endswith(("(LinkedIn)", "(Mobile)", "(Personal)", "(Work)"))
    )


def _looks_like_location(line: str) -> bool:
    return "," in line or line.endswith(" Area") or line.lower() == "remote"


def parse_linkedin_profile(text: str) -> ResumeProfile:
    """Deterministic parse of the LinkedIn export: Top Skills, headline and current role."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    sections, name_block = _linkedin_sections(lines)

    headline = ""
    if len(name_block) >= 2:
        middle = name_block[1:]
        if len(middle) > 1 and _looks_like_location(middle[-1]):
            middle = middle[:-1]
        headline = " ".join(middle)

    working_on = ""
    experience = sections.get("Experience", [])
    for index, line in enumerate(experience):
        if _LINKEDIN_DATE_RE.match(line) and "present" in line.lower() and index >= 2:
            company, title = experience[index - 2], experience[index - 1]
            working_on = f"{title} at {company}."
            break

    return sanitize_profile(
        {
            "headline": headline,
            "skills": sections.get("Top Skills", []),
            "working_on": working_on,
            "summary": " ".join(sections.get("Summary", [])),
        }
    )


# --- OpenAI structured output ------------------------------------------------------------------

RESUME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {
            "type": "string",
            "description": "One line, like a LinkedIn headline: role and focus, max 120 chars.",
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete technologies, tools, languages, methods. Lowercase. Max 30.",
        },
        "interests": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Topics this person cares about professionally. Lowercase. Max 15.",
        },
        "working_on": {
            "type": "string",
            "description": "One sentence: what they are currently building or responsible for.",
        },
        "can_help_with": {
            "type": "string",
            "description": "One sentence: what they could help a fellow conference attendee with.",
        },
        "summary": {
            "type": "string",
            "description": "Two or three sentences summarising their professional background.",
        },
    },
    "required": ["headline", "skills", "interests", "working_on", "can_help_with", "summary"],
}

_INSTRUCTIONS = (
    "You turn a résumé or professional profile into structured fields for a conference "
    "networking app so the attendee gets matched with relevant talks and people. "
    "Return the requested JSON. Keep skills and interests as short lowercase keywords. "
    "Write working_on and can_help_with as one sentence each, in the third person, without "
    "the person's name and without gendered pronouns (use 'they' or no pronoun). "
    "Never output contact details in any field: no email addresses, "
    "phone numbers, postal addresses, or URLs of any kind. Do not invent information that "
    "is not supported by the text; leave a field empty if the text gives nothing for it."
)


def _call_openai(text: str) -> dict[str, Any]:
    """Blocking OpenAI call; the caller runs it off the event loop."""
    # Import lazily so health checks still work while a fresh image is installing dependencies.
    from openai import OpenAI

    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_RESUME_MODEL", "gpt-5.4-mini"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _INSTRUCTIONS},
                    {"type": "input_text", "text": f"Résumé text:\n\n{text}"},
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "resume_profile",
                "strict": True,
                "schema": RESUME_SCHEMA,
            }
        },
        timeout=30,
    )
    result = json.loads(response.output_text)
    if not isinstance(result, dict):
        raise ValueError("Resume parser returned a non-object")
    return result


def llm_profile(text: str) -> ResumeProfile | None:
    """Structured-output parse; `None` when OpenAI is not configured or the call fails."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return sanitize_profile(_call_openai(text[:MAX_LLM_INPUT_CHARS]))
    except Exception as exc:  # the save must still succeed with raw text
        # Only the exception type: messages can echo request content.
        logger.warning("resume_llm_parse_failed error=%s", type(exc).__name__)
        return None


def parse_resume(text: str) -> ResumeProfile:
    """Deterministic LinkedIn fields first, then the model fills whatever is still empty."""
    text = normalize_whitespace(text)
    if not text:
        return ResumeProfile()
    deterministic = parse_linkedin_profile(text) if is_linkedin_pdf_text(text) else ResumeProfile()
    model = llm_profile(text)
    if model is None:
        return deterministic
    merged = merge_resume_profile(deterministic.model_dump(), model)
    return sanitize_profile(merged)


# --- Merging into the attendee document --------------------------------------------------------

_SCALAR_FIELDS = ("headline", "working_on", "can_help_with")
_LIST_FIELDS = ("skills", "interests")


def merge_resume_profile(typed: Mapping[str, Any], parsed: ResumeProfile) -> dict[str, Any]:
    """Fill empty attendee fields from the résumé; what the attendee typed always wins.

    Scalars are only set when the typed value is empty. Skills and interests are unioned,
    typed values first, deduped case-insensitively.
    """
    merged = dict(typed)
    for field in _SCALAR_FIELDS:
        if not (merged.get(field) or "").strip():
            value = getattr(parsed, field)
            if value:
                merged[field] = value
    for field in _LIST_FIELDS:
        existing = [item for item in merged.get(field) or [] if isinstance(item, str)]
        seen = {item.strip().lower() for item in existing}
        for item in getattr(parsed, field):
            if item.lower() not in seen:
                seen.add(item.lower())
                existing.append(item)
        merged[field] = existing
    return merged
