"""OpenAI-backed schedule parser used by the organizer preview endpoint.

The parser is intentionally stateless: it returns a reviewable draft and never writes to the
live `talks` index.  Confirmation remains an explicit organizer action.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

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


def parse_schedule(
    *,
    conference_id: str,
    source_url: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Extract a JSON schedule draft from an organizer-provided URL or document.

    URL retrieval is delegated to the model/provider rather than being fetched by this API,
    which prevents this service becoming an SSRF proxy.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    # Import lazily so health checks still work while a fresh image is installing dependencies.
    from openai import OpenAI

    instructions = (
        "Extract the conference schedule into the requested JSON. This is a draft for human "
        "review, not a publication. Include only sessions with a title and timezone-aware "
        "ISO-8601 start_time and end_time. Put ambiguity or missing details in warnings. "
        f"Conference id: {conference_id}."
    )
    content_parts: list[dict[str, Any]] = [{"type": "input_text", "text": instructions}]
    if source_url:
        content_parts.append(
            {
                "type": "input_text",
                "text": (
                    f"The organizer supplied this schedule URL. Read and parse it: {source_url}"
                ),
            }
        )
    elif content is not None:
        encoded = base64.b64encode(content).decode("ascii")
        if content_type and content_type.startswith("image/"):
            content_parts.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{content_type};base64,{encoded}",
                }
            )
        else:
            content_parts.append(
                {
                    "type": "input_file",
                    "filename": filename or "schedule",
                    "file_data": (
                        f"data:{content_type or 'application/octet-stream'};base64,{encoded}"
                    ),
                }
            )
    else:  # defensive: the FastAPI endpoint validates this invariant first
        raise ValueError("A schedule URL or file is required")
    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_SCHEDULE_MODEL", "gpt-4.1-mini"),
        input=[{"role": "user", "content": content_parts}],
        text={
            "format": {
                "type": "json_schema",
                "name": "schedule",
                "strict": True,
                "schema": SCHEDULE_SCHEMA,
            }
        },
        timeout=45,
    )
    result = json.loads(response.output_text)
    if not isinstance(result.get("talks"), list) or not isinstance(result.get("warnings"), list):
        raise ValueError("Parser returned an invalid schedule draft")
    return result
