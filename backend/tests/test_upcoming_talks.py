"""GET /talks/upcoming with a stubbed Elasticsearch client. No network."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app import main
from app.main import upcoming_talks


def talk(conference_id: str, start: str, title: str) -> dict[str, Any]:
    return {
        "_source": {
            "talk_id": f"{conference_id}-{start}",
            "title": title,
            "start_time": start,
            "end_time": start.replace("T10", "T11"),
            "room": "Hall A",
            "conference_id": conference_id,
            # Must never leak even if the index happened to hold it.
            "semantic_content": "private",
        }
    }


class FakeES:
    def __init__(self) -> None:
        self.hits = [
            talk("c-live", "2026-12-01T10:00:00+00:00", "Keynote"),
            talk("c-smoke", "2026-12-01T10:05:00+00:00", "Smoke talk"),
            talk("c-missing", "2026-12-01T10:10:00+00:00", "Orphan"),
            talk("c-live", "2026-12-02T10:00:00+00:00", "Day two"),
            talk("c-other", "2026-12-03T10:00:00+00:00", "Third"),
        ]
        self.names = {
            "c-live": "Cloud Native Hackathon",
            "c-smoke": "smoke-test (delete me)",
            "c-other": "KubeCon",
        }
        self.search_kwargs: dict[str, Any] = {}

    def options(self, **_: Any) -> FakeES:
        return self

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_kwargs = kwargs
        return {"hits": {"hits": self.hits}}

    def mget(self, *, index: str, ids: list[str], source_includes: list[str]) -> dict[str, Any]:
        assert index == "conferences" and source_includes == ["name"]
        return {
            "docs": [
                {"_id": cid, "found": cid in self.names, "_source": {"name": self.names.get(cid)}}
                for cid in ids
            ]
        }


@pytest.fixture
def fake_es(monkeypatch: pytest.MonkeyPatch) -> FakeES:
    fake = FakeES()
    monkeypatch.setattr(main, "es", fake)
    return fake


def test_upcoming_filters_test_and_unknown_conferences(fake_es: FakeES) -> None:
    result = asyncio.run(upcoming_talks(limit=6))
    titles = [t["title"] for t in result["talks"]]
    assert titles == ["Keynote", "Day two", "Third"]
    assert result["talks"][0]["conference_name"] == "Cloud Native Hackathon"
    assert set(result["talks"][0]) == {
        "talk_id",
        "title",
        "start_time",
        "end_time",
        "room",
        "conference_id",
        "conference_name",
    }
    filters = fake_es.search_kwargs["query"]["bool"]["filter"]
    assert {"term": {"confirmed": True}} in filters
    assert {"range": {"start_time": {"gte": "now"}}} in filters
    assert fake_es.search_kwargs["sort"] == [{"start_time": {"order": "asc"}}]


def test_upcoming_respects_limit_after_filtering(fake_es: FakeES) -> None:
    result = asyncio.run(upcoming_talks(limit=2))
    assert [t["title"] for t in result["talks"]] == ["Keynote", "Day two"]


def test_upcoming_is_empty_without_talks(fake_es: FakeES) -> None:
    fake_es.hits = []
    assert asyncio.run(upcoming_talks(limit=6)) == {"talks": []}
