"""Vector matching: index mappings, profile text, resume extraction and query builders.

Everything here is pure (no network) so the query shapes can be unit tested. People and talks
share one embedding model, so a profile can query talks and a talk can query people.
"""

from __future__ import annotations

import io
from typing import Any

JINA = ".jina-embeddings-v5-text-small"
_SEMANTIC = {"type": "semantic_text", "inference_id": JINA}
_ID = {"type": "keyword"}
_DATE = {"type": "date"}
_TEXT = {"type": "text"}
_BOOL = {"type": "boolean"}

# Only these fields of another attendee ever leave Elasticsearch through a search.
SAFE_SOURCE: dict[str, list[str]] = {"includes": ["attendee_id", "name"]}
TALK_SOURCE = [
    "talk_id",
    "title",
    "abstract",
    "speakers",
    "room",
    "track",
    "start_time",
    "end_time",
]
ARCHIVE_SOURCE = ["title", "conference", "year", "url", "video_url"]

# Q1 retriever weights; renormalized to sum to 1 when a retriever is skipped.
Q1_WEIGHTS = {"profile": 0.6, "resume_text": 0.25, "interests": 0.15}

# Serverless rejects number_of_shards / number_of_replicas / refresh_interval: never set them.
ATTENDEES_INDEX: dict[str, Any] = {
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
            "bio": _TEXT,
            "interests": {"type": "keyword", "normalizer": "lower"},
            "profile": _SEMANTIC,
            "resume_text": _SEMANTIC,
            "resume_public": _BOOL,
            # Contact details are disclosed only through /accept-connection; never searched.
            "email": {"type": "keyword", "index": False},
            "linkedin_url": {"type": "keyword", "index": False},
            "discovery_opt_in": _BOOL,
            "blockout_times": {"properties": {"start_time": _DATE, "end_time": _DATE}},
            "access_token_sha256": {"type": "keyword", "index": False, "doc_values": False},
            "updated_at": _DATE,
        },
    },
}

TALKS_INDEX: dict[str, Any] = {
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
}

# --- Document shaping ---------------------------------------------------------------------------


def split_interests(value: Any) -> list[str]:
    """Interests arrive as a list or as the frontend's comma-separated string."""
    if value is None:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    seen: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text.lower() not in {s.lower() for s in seen}:
            seen.append(text)
    return seen


def profile_text(bio: str = "", interests: list[str] | None = None) -> str:
    """Build the `profile` semantic field server-side: bio plus interests."""
    parts = [bio, f"Interests: {', '.join(interests)}" if interests else ""]
    return ". ".join(x.strip().rstrip(".") for x in parts if x and x.strip())


def extract_resume_text(content: bytes, content_type: str) -> str:
    """Plain text from an uploaded PDF, DOCX or TXT resume. Only the text is stored."""
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        from docx import Document

        document = Document(io.BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()
    return content.decode("utf-8", errors="replace").strip()


# --- Query builders -----------------------------------------------------------------------------


def eligible(conference_id: str, me: str) -> dict[str, Any]:
    """Same conference, opted in to discovery, not the requester."""
    return {
        "filter": [
            {"term": {"conference_id": conference_id}},
            {"term": {"discovery_opt_in": True}},
        ],
        "must_not": [{"term": {"attendee_id": me}}],
    }


def semantic(field: str, text: str, conference_id: str, me: str) -> dict[str, Any]:
    return {
        "bool": {
            "must": [{"semantic": {"field": field, "query": text}}],
            **eligible(conference_id, me),
        }
    }


def similar_people_query(
    conference_id: str,
    me: str,
    profile: str,
    interests: list[str],
    resume_text: str = "",
    size: int = 10,
) -> dict[str, Any] | None:
    """Q1: profile meaning (0.6) + resume meaning (0.25) + shared interests (0.15).

    `linear` with minmax, not RRF: RRF only sees ranks, so two people who each share one
    interest tie regardless of how close their profiles are. Weights of skipped retrievers are
    redistributed proportionally. Returns None when nothing about the person can be matched on.
    """
    weighted: list[dict[str, Any]] = []
    if profile:
        weighted.append(
            {
                "retriever": {
                    "standard": {"query": semantic("profile", profile, conference_id, me)}
                },
                "weight": Q1_WEIGHTS["profile"],
            }
        )
    if resume_text:
        weighted.append(
            {
                "retriever": {
                    "standard": {"query": semantic("resume_text", resume_text, conference_id, me)}
                },
                "weight": Q1_WEIGHTS["resume_text"],
            }
        )
    if interests:
        weighted.append(
            {
                "retriever": {
                    "standard": {
                        "query": {
                            "bool": {
                                "should": [{"terms": {"interests": interests}}],
                                "minimum_should_match": 1,
                                **eligible(conference_id, me),
                            }
                        }
                    }
                },
                "weight": Q1_WEIGHTS["interests"],
            }
        )
    if not weighted:
        return None
    body: dict[str, Any] = {
        "index": "attendees",
        "size": size,
        "source": SAFE_SOURCE,
        "highlight": {"fields": {"profile": {"type": "semantic", "number_of_fragments": 1}}},
    }
    if len(weighted) == 1:
        body["query"] = weighted[0]["retriever"]["standard"]["query"]
        return body
    total = sum(r["weight"] for r in weighted)
    for r in weighted:
        r["weight"] = round(r["weight"] / total, 4)
    body["retriever"] = {
        "linear": {"rank_window_size": 50, "normalizer": "minmax", "retrievers": weighted}
    }
    return body


def recommend_talks_query(
    conference_id: str,
    profile: str,
    blockouts: list[tuple[str, str]],
    size: int = 20,
) -> dict[str, Any]:
    """Q3: the attendee's profile queries the schedule; blockouts are excluded in Elasticsearch.

    `blockouts` are (start_iso, end_iso) pairs. A talk overlaps when it starts before the blockout
    ends and ends after it starts. With an empty profile, fall back to schedule order.
    """
    bool_query: dict[str, Any] = {
        "filter": [{"term": {"conference_id": conference_id}}, {"term": {"confirmed": True}}],
        "must_not": [
            {
                "bool": {
                    "filter": [
                        {"range": {"start_time": {"lt": end}}},
                        {"range": {"end_time": {"gt": start}}},
                    ]
                }
            }
            for start, end in blockouts
        ],
    }
    body: dict[str, Any] = {"index": "talks", "size": size, "source": TALK_SOURCE}
    if profile.strip():
        bool_query["must"] = [{"semantic": {"field": "semantic_content", "query": profile}}]
    else:
        body["sort"] = [{"start_time": "asc"}]
    body["query"] = {"bool": bool_query}
    return body


def talk_audience_query(conference_id: str, talk: dict[str, Any], size: int = 10) -> dict[str, Any]:
    """Q4: opted-in attendees whose profile matches this talk (organizers and speakers)."""
    return {
        "index": "attendees",
        "size": size,
        "source": SAFE_SOURCE,
        "query": {
            "bool": {
                "must": [
                    {
                        "semantic": {
                            "field": "profile",
                            "query": f"{talk.get('title', '')}. {talk.get('abstract', '')}",
                        }
                    }
                ],
                "filter": [
                    {"term": {"conference_id": conference_id}},
                    {"term": {"discovery_opt_in": True}},
                ],
            }
        },
    }


def similar_past_talks_query(talk: dict[str, Any], size: int = 5) -> dict[str, Any]:
    """Q5: past recordings like this talk, from the read-only archive."""
    return {
        "index": "talks-archive",
        "size": size,
        "source": ARCHIVE_SOURCE,
        "query": {
            "semantic": {
                "field": "semantic_content",
                "query": f"{talk.get('title', '')}. {talk.get('abstract', '')}",
            }
        },
    }


# --- Result shaping -----------------------------------------------------------------------------


def person_hit(hit: dict[str, Any], highlight_field: str = "profile") -> dict[str, Any]:
    """Safe projection of an attendee hit plus the highlight fragment that explains the match."""
    source = hit.get("_source", {})
    fragments = hit.get("highlight", {}).get(highlight_field) or []
    return {
        "attendee_id": source.get("attendee_id"),
        "name": source.get("name"),
        "score": hit.get("_score"),
        "why": fragments[0] if fragments else None,
    }
