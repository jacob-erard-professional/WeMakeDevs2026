"""/confirm-schedule publish path with a stubbed Elasticsearch client. No network."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pytest
from fastapi import HTTPException

from app import main
from app.main import ConfirmSchedule, confirm_schedule

CONFERENCE = "conference-test"
TOKEN = "organizer-secret"


class FakeES:
    """Records every write; `bulk_errors` makes each bulk response report item errors."""

    def __init__(self, *, bulk_errors: bool = False) -> None:
        self.bulk_errors = bulk_errors
        self.bulk_calls: list[list[dict[str, Any]]] = []
        self.deletes: list[dict[str, Any]] = []
        self.status_writes: list[dict[str, Any]] = []
        self.conference: dict[str, Any] = {
            "conference_id": CONFERENCE,
            "name": "Test Conf",
            "organizer_token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        }

    def options(self, **_: Any) -> FakeES:
        return self

    def get(self, *, index: str, id: str, source_includes: list[str]) -> dict[str, Any]:
        assert index == "conferences" and id == CONFERENCE
        return {"_source": {k: v for k, v in self.conference.items() if k in source_includes}}

    def update(self, *, index: str, id: str, doc: dict[str, Any]) -> dict[str, Any]:
        assert index == "conferences" and id == CONFERENCE
        self.conference.update(doc)
        self.status_writes.append(dict(doc))
        return {"result": "updated"}

    def bulk(self, *, operations: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        self.bulk_calls.append(operations)
        items = [
            {
                "index": {
                    "_id": action["index"]["_id"],
                    **({"error": {"type": "boom"}} if self.bulk_errors else {}),
                }
            }
            for action in operations[::2]
        ]
        return {"errors": self.bulk_errors, "items": items}

    def delete_by_query(self, **kwargs: Any) -> dict[str, Any]:
        self.deletes.append(kwargs)
        return {"deleted": 3}


def talks(count: int) -> list[dict[str, Any]]:
    return [
        {
            "title": f"Talk {i}",
            "start_time": f"2026-11-09T{9 + i // 60:02d}:{i % 60:02d}:00Z",
            "end_time": f"2026-11-09T{10 + i // 60:02d}:{i % 60:02d}:00Z",
            "room": f"Room {i}",
        }
        for i in range(count)
    ]


@pytest.fixture
def fake_es(monkeypatch: pytest.MonkeyPatch):
    def install(**kwargs: Any) -> FakeES:
        fake = FakeES(**kwargs)
        monkeypatch.setattr(main, "es", fake)
        monkeypatch.setattr(main, "_indices_ready", True)
        main._schedule_locks.clear()
        return fake

    return install


def confirm_and_drain(count: int) -> dict[str, Any]:
    """Call the handler and wait for any background job it scheduled."""

    async def run() -> dict[str, Any]:
        response = await confirm_schedule(
            ConfirmSchedule(conference_id=CONFERENCE, talks=talks(count)),
            x_organizer_token=TOKEN,
        )
        snapshot = dict(response)
        await asyncio.gather(*main._schedule_jobs)
        return snapshot

    return asyncio.run(run())


def test_small_schedule_indexes_inline_and_is_ready(fake_es) -> None:
    fake = fake_es()

    response = confirm_and_drain(3)

    assert response["conference_id"] == CONFERENCE
    assert response["talk_count"] == 3
    assert response["status"] == "ready"
    assert response["join_url"].endswith(f"/join/{CONFERENCE}")
    assert response["qr_code_data_url"].startswith("data:image/png;base64,")
    assert len(fake.bulk_calls) == 1 and len(fake.bulk_calls[0]) == 6
    assert len(fake.deletes) == 1
    assert fake.conference["schedule_status"] == "ready"
    assert fake.conference["schedule_indexed_count"] == 3


def test_large_schedule_returns_indexing_then_transitions_to_ready(fake_es) -> None:
    fake = fake_es()
    count = main.SYNC_TALK_LIMIT + 1

    async def run() -> tuple[dict[str, Any], str | None, int]:
        response = await confirm_schedule(
            ConfirmSchedule(conference_id=CONFERENCE, talks=talks(count)),
            x_organizer_token=TOKEN,
        )
        status_at_return = fake.conference.get("schedule_status")
        bulks_at_return = len(fake.bulk_calls)
        await asyncio.gather(*main._schedule_jobs)
        return response, status_at_return, bulks_at_return

    response, status_at_return, bulks_at_return = asyncio.run(run())

    assert response["status"] == "indexing"
    assert response["talk_count"] == count
    assert status_at_return == "indexing"
    assert bulks_at_return == 0  # the response did not wait on the bulk write
    assert fake.conference["schedule_status"] == "ready"
    assert fake.conference["schedule_indexed_count"] == count
    assert fake.conference["schedule_talk_count"] == count
    assert fake.conference["schedule_error"] is None
    assert len(fake.deletes) == 1
    assert fake.deletes[0]["query"]["bool"]["filter"] == [{"term": {"conference_id": CONFERENCE}}]
    assert len(fake.deletes[0]["query"]["bool"]["must_not"][0]["terms"]["talk_id"]) == count


def test_bulk_error_in_background_keeps_old_talks_and_marks_failed(fake_es) -> None:
    fake = fake_es(bulk_errors=True)

    response = confirm_and_drain(main.SYNC_TALK_LIMIT + 1)

    assert response["status"] == "indexing"
    assert fake.deletes == []  # stale delete never ran, so the old schedule survives
    assert fake.conference["schedule_status"] == "failed"
    assert "ScheduleIndexError" in fake.conference["schedule_error"]
    assert not main._schedule_jobs


def test_bulk_error_inline_returns_502_and_keeps_old_talks(fake_es) -> None:
    fake = fake_es(bulk_errors=True)

    with pytest.raises(HTTPException) as excinfo:
        confirm_and_drain(2)

    assert excinfo.value.status_code == 502
    assert fake.deletes == []


def test_invalid_talk_times_422_before_any_write(fake_es) -> None:
    fake = fake_es()
    bad = [{"title": "x", "start_time": "2026-11-09T10:00:00Z", "end_time": "2026-11-09T09:00:00Z"}]

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            confirm_schedule(
                ConfirmSchedule(conference_id=CONFERENCE, talks=bad), x_organizer_token=TOKEN
            )
        )

    assert excinfo.value.status_code == 422
    assert fake.status_writes == [] and fake.bulk_calls == []


def test_wrong_organizer_token_401(fake_es) -> None:
    fake_es()

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            confirm_schedule(
                ConfirmSchedule(conference_id=CONFERENCE, talks=talks(1)),
                x_organizer_token="nope",
            )
        )

    assert excinfo.value.status_code == 401


def test_stale_indexing_is_reported_as_failed() -> None:
    from datetime import UTC, datetime, timedelta

    from app.main import STALE_SCHEDULE_ERROR, effective_schedule_status

    fresh = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    assert effective_schedule_status(
        {"schedule_status": "indexing", "schedule_updated_at": fresh}, False
    ) == ("indexing", None)
    assert effective_schedule_status(
        {"schedule_status": "indexing", "schedule_updated_at": stale}, False
    ) == ("failed", STALE_SCHEDULE_ERROR)
    assert effective_schedule_status({"schedule_status": "indexing"}, False)[0] == "failed"
    assert effective_schedule_status({"schedule_status": "ready"}, True) == ("ready", None)
    assert effective_schedule_status({}, True) == ("ready", None)
    assert effective_schedule_status({}, False) == ("none", None)
