import asyncio

import pytest
from fastapi import HTTPException

from app import main


def test_text_search_fuses_keyword_and_semantic_with_the_same_filters():
    body = main.archive_search_body("eBPF security", "Security", "kubecon", 2024, 2)

    rrf = body["retriever"]["rrf"]
    keyword, semantic = (r["standard"]["query"]["bool"] for r in rrf["retrievers"])
    assert "multi_match" in keyword["must"][0]
    assert semantic["must"][0] == {
        "semantic": {"field": "semantic_content", "query": "eBPF security"}
    }
    expected = [
        {"term": {"tracks": "Security"}},
        {"term": {"source": "kubecon"}},
        {"term": {"year": 2024}},
    ]
    assert keyword["filter"] == semantic["filter"] == expected
    assert body["from"] == 20 and body["size"] == 20
    assert body["from"] + body["size"] <= rrf["rank_window_size"]
    assert "query" not in body


def test_empty_query_browses_newest_first_without_semantic_search():
    body = main.archive_search_body("", None, None, None, 1)

    assert body["query"] == {"bool": {"filter": []}}
    assert body["sort"][0] == {"year": "desc"}
    assert "retriever" not in body


def test_text_search_rejects_pages_past_the_rank_window(monkeypatch):
    monkeypatch.setattr(main.es, "search", lambda **_: pytest.fail("should not query"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.search_archive_talks(q="kubernetes", page=6))
    assert error.value.status_code == 422


def test_search_response_shape(monkeypatch):
    def search(**options):
        assert options["index"] == "talks-archive"
        assert options["_source"] == main.ARCHIVE_SOURCE_FIELDS
        return {
            "hits": {"total": {"value": 450}, "hits": [{"_source": {"id": "t1", "title": "A"}}]},
            "aggregations": {
                "tracks": {"buckets": [{"key": "Security", "doc_count": 12}]},
                "sources": {"buckets": []},
                "years": {"buckets": [{"key": 2024, "doc_count": 7}]},
            },
        }

    monkeypatch.setattr(main.es, "options", lambda **_: main.es)
    monkeypatch.setattr(main.es, "search", search)
    result = asyncio.run(
        main.search_archive_talks(q="security", track=None, source=None, year=None, page=5)
    )
    # 450 matches, but a text search can only page through the top 100.
    assert result["has_more"] is False
    assert result["talks"] == [{"id": "t1", "title": "A"}]
    assert result["facets"]["tracks"] == [{"value": "Security", "count": 12}]
    assert result["facets"]["years"] == [{"value": 2024, "count": 7}]
