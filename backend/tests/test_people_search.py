import asyncio

import pytest
from fastapi import HTTPException

from app import main


def test_people_note_only_queries_discoverable_attendees_in_the_conference(monkeypatch):
    calls = []

    def search(**options):
        calls.append(options)
        return {"hits": {"hits": []}}

    monkeypatch.setattr(main.es, "search", search)
    profile = {
        "conference_id": "conference-one",
        "attendee_id": "attendee-one",
        "looking_for": "Data platforms",
    }
    assert asyncio.run(main.recommended_people(profile, "Kubernetes")) == {
        "similar": [],
        "matches": [],
    }
    assert profile["looking_for"] == "Data platforms"

    [call] = calls
    retrievers = call["retriever"]["linear"]["retrievers"]
    queries = [item["retriever"]["standard"]["query"]["bool"] for item in retrievers]
    assert {query["must"][0]["semantic"]["field"] for query in queries} == {
        "can_help_with",
        "profile",
    }
    for query in queries:
        assert query["must"][0]["semantic"]["query"] == "Kubernetes"
        assert {"term": {"conference_id": "conference-one"}} in query["filter"]
        assert {"term": {"discovery_opt_in": True}} in query["filter"]
        assert query["must_not"] == [{"term": {"attendee_id": "attendee-one"}}]
    assert call["source"] == main.SAFE_ATTENDEE_SOURCE


def test_people_note_requires_a_token_for_the_requested_conference():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            main.search_people_recommendations(
                "conference-one",
                main.PeopleSearch(note="Kubernetes"),
                ("conference-two", "attendee-one"),
            )
        )
    assert exc.value.status_code == 401
