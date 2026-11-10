import asyncio

from app import main


def test_published_events_exclude_seed_and_indexing_schedules(monkeypatch):
    buckets = [
        {
            "key": key,
            "doc_count": 71,
            "first_start": {"value_as_string": "2026-11-09T16:00:00Z"},
            "last_end": {"value_as_string": "2026-11-10T23:00:00Z"},
        }
        for key in ["imported", "old", "demo", "cnh-slc-2026", "indexing"]
    ]
    monkeypatch.setattr(
        main.es, "search", lambda **_: {"aggregations": {"events": {"buckets": buckets}}}
    )

    def metadata(**options):
        assert options["source_includes"] == ["name", "schedule_status"]
        return {
            "docs": [
                {
                    "_id": "imported",
                    "_source": {"name": "Imported Event", "schedule_status": "ready"},
                },
                {"_id": "old", "_source": {"name": "Older Event"}},
                {"_id": "demo", "_source": {"name": "Cloud Native Hackathon SLC 2026"}},
                {
                    "_id": "cnh-slc-2026",
                    "_source": {"name": "Cloud Native Hackathon @ KubeCon NA 2026"},
                },
                {
                    "_id": "indexing",
                    "_source": {"name": "Pending Event", "schedule_status": "indexing"},
                },
            ]
        }

    monkeypatch.setattr(main.es, "mget", metadata)
    events = asyncio.run(main.list_catalog_events("published"))["events"]
    assert [event["id"] for event in events] == ["imported", "old"]
    assert events[0]["talk_count"] == 71


def test_catalog_search_filters_both_retrievers_and_pages(monkeypatch):
    async def published():
        return [{"id": "real-event", "name": "Real Event"}]

    monkeypatch.setattr(main, "published_catalog_events", published)

    def search(**options):
        assert options["index"] == "talks"
        assert options["from_"] == 20
        assert options["source"] == main.PUBLISHED_TALK_SOURCE
        rrf = options["retriever"]["rrf"]
        assert len(rrf["retrievers"]) == 2
        for retriever in rrf["retrievers"]:
            assert retriever["standard"]["query"]["bool"]["filter"] == [
                {"term": {"confirmed": True}},
                {"terms": {"conference_id": ["real-event"]}},
            ]
        return {
            "hits": {
                "hits": [
                    {
                        "_id": str(index),
                        "_source": {"conference_id": "real-event", "title": "A real talk"},
                    }
                    for index in range(21)
                ]
            }
        }

    monkeypatch.setattr(main.es, "search", search)
    result = asyncio.run(
        main.search_catalog_talks(main.CatalogSearch(query="Kubernetes", offset=20))
    )
    assert len(result["talks"]) == 20
    assert result["talks"][0]["conference"] == "Real Event"
    assert result["next_offset"] == 40
    assert asyncio.run(main.search_catalog_talks(main.CatalogSearch(event_id="unpublished"))) == {
        "talks": [],
        "next_offset": None,
    }


def test_historical_search_uses_read_only_archive(monkeypatch):
    def search(**options):
        assert options["index"] == "talks-archive"
        assert options["query"] == {"bool": {"filter": [{"term": {"conference_id": "past-event"}}]}}
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "archive-id",
                        "_source": {
                            "title": "Past talk",
                            "conference": "Past Event",
                            "tracks": ["Platform"],
                            "video_url": "https://example.org/video",
                        },
                    }
                ]
            }
        }

    monkeypatch.setattr(main.es, "search", search)
    result = asyncio.run(
        main.search_catalog_talks(
            main.CatalogSearch(source="archive", event_id="past-event"),
        )
    )
    assert result["talks"][0]["tracks"] == ["Platform"]
    assert result["talks"][0]["video_url"] == "https://example.org/video"
