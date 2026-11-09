"""Deterministic schedule adapters: bytes in, draft talks out, no LLM.

Each adapter is a pure function `(body, tz) -> Draft` where `tz` is the conference's IANA zone
(or None). Field mappings follow `docs/schedule-formats.md`. Times come out as timezone-aware
`datetime`s; `schedule_parser.normalize_talks` turns them into the draft's ISO strings.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

NON_TALK_RE = re.compile(
    r"^\s*(registration|check[- ]?in|badge pick[- ]?up|coffee( break)?|break|lunch|breakfast|"
    r"dinner|reception|networking|happy hour|doors open|opening of the day|closing of the day|"
    r"sponsor showcase|exhibit)\b",
    re.IGNORECASE,
)
NON_TALK_CATEGORIES = {"REGISTRATION", "BREAKS", "BREAK", "SOCIAL"}
TRACK_GROUP_RE = re.compile(r"track|category|topic|theme", re.IGNORECASE)


@dataclass
class Draft:
    talks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_non_talks: int = 0
    timezone: str | None = None

    def finish(self) -> Draft:
        if self.skipped_non_talks:
            self.warnings.append(
                f"Skipped {self.skipped_non_talks} non-talk rows (breaks, registration, etc.)"
            )
        return self


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value)
    if "<" in text:
        extractor = _TextExtractor()
        extractor.feed(text)
        text = "".join(extractor.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text or None


def is_non_talk(title: str, categories: list[str]) -> bool:
    if any(c.strip().upper() in NON_TALK_CATEGORIES for c in categories):
        return True
    return bool(NON_TALK_RE.match(title))


def localize(value: datetime | date | None, tz: ZoneInfo | None) -> datetime | None:
    """Return an aware datetime, localizing naive values with `tz`. None when impossible."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=tz) if tz else None
    if tz is None:
        return None
    return datetime.combine(value, time.min, tzinfo=tz)


def zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def split_summary(summary: str) -> tuple[str, list[str]]:
    """`Title - Name, Role, Org & Name, Org` -> (title, [names]) per the Sched convention."""
    if " - " not in summary:
        return summary.strip(), []
    title, _, tail = summary.rpartition(" - ")
    speakers = []
    for chunk in re.split(r"\s*&\s*|\s*;\s*", tail):
        name = chunk.split(",", 1)[0].strip()
        if not name:
            continue
        # Co-located event rows look like `Title - Half Day Event | ALL ACCESS PASS REQUIRED`;
        # that tail is a notice, not a person. Keep the whole summary as the title instead.
        if "|" in name or len(name.split()) > 5 or (name.isupper() and len(name) > 4):
            return summary.strip(), []
        speakers.append(name)
    return title.strip(), speakers


def clean_sched_location(location: str | None) -> str | None:
    """Drop Sched's trailing `, City, Region, Country` suffix from a room."""
    if not location:
        return None
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 4:
        parts = parts[:-3]
    return ", ".join(parts).strip() or None


# ---------------------------------------------------------------------------- iCalendar


def parse_ics(body: bytes, tz_name: str | None) -> Draft:
    from icalendar import Calendar

    draft = Draft()
    cal = Calendar.from_ical(body)
    prodid = str(cal.get("PRODID", "")).lower()
    cal_tz = str(cal.get("X-WR-TIMEZONE", "")).strip() or None
    tz = zone(tz_name) or zone(cal_tz)
    draft.timezone = tz_name or cal_tz
    split_speakers = "sched.com" in prodid or "pretalx" in prodid
    is_sched = "sched.com" in prodid
    floating = 0
    for component in cal.walk("VEVENT"):
        summary = str(component.get("SUMMARY", "")).strip()
        if not summary:
            continue
        categories_raw = component.get("CATEGORIES")
        categories: list[str] = []
        for cat in categories_raw if isinstance(categories_raw, list) else [categories_raw]:
            if cat is None:
                continue
            cats = getattr(cat, "cats", None)
            categories.extend(str(c) for c in cats) if cats else categories.append(str(cat))
        categories = [c.strip() for c in categories if c and c.strip()]
        if is_non_talk(summary, categories):
            draft.skipped_non_talks += 1
            continue
        title, speakers = split_summary(summary) if split_speakers else (summary, [])
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        start_raw = dtstart.dt if dtstart is not None else None
        end_raw = dtend.dt if dtend is not None else None
        if isinstance(start_raw, datetime) and start_raw.tzinfo is None:
            floating += 1
        start = localize(start_raw, tz)
        end = localize(end_raw, tz)
        if start and end is None and component.get("DURATION") is not None:
            end = start + component.get("DURATION").dt
        location = str(component.get("LOCATION", "")).strip() or None
        draft.talks.append(
            {
                "title": title,
                "abstract": strip_html(str(component.get("DESCRIPTION", "")) or None),
                "speakers": speakers,
                "room": clean_sched_location(location) if is_sched else location,
                "track": categories,
                "start_time": start,
                "end_time": end,
            }
        )
    if floating and tz:
        draft.warnings.append(f"{floating} sessions had floating times; localized to {tz.key}")
    return draft.finish()


# ---------------------------------------------------------------------------- Sessionize


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_sessionize_all(data: dict[str, Any], tz_name: str | None) -> Draft:
    draft = Draft(timezone=tz_name)
    tz = zone(tz_name)
    speakers = {s["id"]: s.get("fullName") or s.get("name") for s in data.get("speakers", [])}
    rooms = {r["id"]: r.get("name") for r in data.get("rooms", [])}
    categories = data.get("categories") or []
    track_groups = [c for c in categories if TRACK_GROUP_RE.search(str(c.get("title", "")))]
    items: dict[Any, str] = {}
    for group in track_groups or categories:
        for item in group.get("items", []):
            items[item["id"]] = item.get("name")
    unscheduled = 0
    floating = 0
    for session in data.get("sessions", []):
        title = (session.get("title") or "").strip()
        if not title:
            continue
        if session.get("isServiceSession") or is_non_talk(title, []):
            draft.skipped_non_talks += 1
            continue
        start = _iso(session.get("startsAt"))
        end = _iso(session.get("endsAt"))
        if start is None:
            unscheduled += 1
            continue
        if start.tzinfo is None:
            floating += 1
        draft.talks.append(
            {
                "title": title,
                "abstract": strip_html(session.get("description")),
                "speakers": [speakers[s] for s in session.get("speakers", []) if speakers.get(s)],
                "room": rooms.get(session.get("roomId")),
                "track": [items[i] for i in session.get("categoryItems", []) if items.get(i)],
                "start_time": localize(start, tz),
                "end_time": localize(end, tz),
            }
        )
    if unscheduled:
        draft.warnings.append(f"Skipped {unscheduled} sessions that have no scheduled time yet")
    if floating and tz:
        draft.warnings.append(f"{floating} sessions had floating times; localized to {tz.key}")
    return draft.finish()


# ---------------------------------------------------------------------------- frab JSON


def _duration(value: str | None) -> timedelta | None:
    if not value:
        return None
    try:
        hours, minutes = value.split(":")[:2]
        return timedelta(hours=int(hours), minutes=int(minutes))
    except ValueError:
        return None


def _frab_title(title: str | None, subtitle: str | None) -> str:
    title = (title or "").strip()
    subtitle = (subtitle or "").strip()
    return f"{title}: {subtitle}" if subtitle else title


def parse_frab_json(data: dict[str, Any], tz_name: str | None) -> Draft:
    conference = data["schedule"]["conference"]
    source_tz = conference.get("time_zone_name")
    draft = Draft(timezone=tz_name or source_tz)
    tz = zone(tz_name) or zone(source_tz)
    for day in conference.get("days", []):
        for room_name, talks in (day.get("rooms") or {}).items():
            for talk in talks:
                title = _frab_title(talk.get("title"), talk.get("subtitle"))
                if not title:
                    continue
                start = _iso(talk.get("date"))
                if start is None and talk.get("start") and day.get("date"):
                    start = datetime.fromisoformat(f"{day['date']}T{talk['start']}")
                start = localize(start, tz)
                end = localize(_iso(talk.get("end")), tz)
                if end is None and start is not None:
                    duration = _duration(talk.get("duration"))
                    end = start + duration if duration else None
                persons = talk.get("persons") or []
                draft.talks.append(
                    {
                        "title": title,
                        "abstract": strip_html(talk.get("abstract") or talk.get("description")),
                        "speakers": [
                            p.get("public_name") or p.get("name")
                            for p in persons
                            if p.get("public_name") or p.get("name")
                        ],
                        "room": talk.get("room") or room_name,
                        "track": [talk["track"]] if talk.get("track") else [],
                        "start_time": start,
                        "end_time": end,
                    }
                )
    return draft.finish()


# ---------------------------------------------------------------------------- frab XML


def parse_frab_xml(body: bytes, tz_name: str | None) -> Draft:
    from defusedxml import ElementTree

    root = ElementTree.fromstring(body)
    if root.tag != "schedule":
        raise ValueError("Not a frab schedule.xml document")
    source_tz = root.findtext("conference/time_zone_name")
    draft = Draft(timezone=tz_name or source_tz)
    tz = zone(tz_name) or zone(source_tz)
    for day in root.iter("day"):
        for room in day.findall("room"):
            for event in room.findall("event"):
                title = _frab_title(event.findtext("title"), event.findtext("subtitle"))
                if not title:
                    continue
                start = _iso(event.findtext("date"))
                if start is None and event.findtext("start") and day.get("date"):
                    start = datetime.fromisoformat(f"{day.get('date')}T{event.findtext('start')}")
                start = localize(start, tz)
                duration = _duration(event.findtext("duration"))
                end = start + duration if start and duration else None
                if is_non_talk(title, []):
                    draft.skipped_non_talks += 1
                    continue
                track = (event.findtext("track") or "").strip()
                draft.talks.append(
                    {
                        "title": title,
                        "abstract": strip_html(
                            event.findtext("abstract") or event.findtext("description")
                        ),
                        "speakers": [
                            (p.text or "").strip()
                            for p in event.findall("persons/person")
                            if (p.text or "").strip()
                        ],
                        "room": event.findtext("room") or room.get("name"),
                        "track": [track] if track else [],
                        "start_time": start,
                        "end_time": end,
                    }
                )
    return draft.finish()


def parse_json_any(body: bytes, tz_name: str | None) -> Draft:
    data = json.loads(body)
    if isinstance(data, dict) and isinstance(data.get("schedule"), dict):
        return parse_frab_json(data, tz_name)
    if isinstance(data, dict) and "sessions" in data and "speakers" in data:
        return parse_sessionize_all(data, tz_name)
    raise ValueError("Unrecognized JSON schedule; use a Sessionize view/All or pretalx export")
