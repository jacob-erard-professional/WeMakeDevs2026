"""Pure tests for the matching query builders and document shaping (no network)."""

from app.matching import (
    ATTENDEES_INDEX,
    PHYSICAL_INDEX,
    SAFE_SOURCE,
    TALKS_INDEX,
    extract_resume_text,
    mapping_mismatches,
    person_hit,
    profile_text,
    recommend_talks_query,
    similar_past_talks_query,
    similar_people_query,
    split_interests,
    talk_audience_query,
)

CID, ME = "conf-1", "me"


def test_mappings_are_strict_and_hide_the_token():
    for index in (ATTENDEES_INDEX, TALKS_INDEX):
        assert index["mappings"]["dynamic"] == "strict"
        assert "number_of_shards" not in str(index.get("settings", {}))
    props = ATTENDEES_INDEX["mappings"]["properties"]
    assert props["access_token_sha256"] == {"type": "keyword", "index": False, "doc_values": False}
    assert "access_token" not in props and "resume_asset" not in props
    assert props["resume_text"]["type"] == "semantic_text"
    assert props["resume_public"] == {"type": "boolean"}


def test_split_interests_accepts_list_or_comma_string():
    assert split_interests("eBPF, kubernetes,, ebpf ") == ["eBPF", "kubernetes"]
    assert split_interests(["a", " b "]) == ["a", "b"]
    assert split_interests(None) == []


def test_profile_text_joins_only_filled_parts():
    assert profile_text() == ""
    assert profile_text(bio="SRE", interests=["otel", "k8s"]) == "SRE. Interests: otel, k8s"
    assert profile_text(bio="", interests=["otel"]) == "Interests: otel"


def test_similar_people_is_linear_minmax_weighted_with_safe_source_and_highlight():
    body = similar_people_query(CID, ME, "SRE", ["k8s"], resume_text="cv")
    assert body["index"] == "attendees"
    assert body["source"] == SAFE_SOURCE
    linear = body["retriever"]["linear"]
    assert linear["normalizer"] == "minmax"
    assert [r["weight"] for r in linear["retrievers"]] == [0.6, 0.25, 0.15]
    queries = [r["retriever"]["standard"]["query"]["bool"] for r in linear["retrievers"]]
    assert queries[0]["must"][0]["semantic"] == {"field": "profile", "query": "SRE"}
    assert queries[1]["must"][0]["semantic"] == {"field": "resume_text", "query": "cv"}
    assert queries[2]["should"] == [{"terms": {"interests": ["k8s"]}}]
    assert {"term": {"attendee_id": ME}} in queries[2]["must_not"]
    assert {"term": {"discovery_opt_in": True}} in queries[2]["filter"]
    assert list(body["highlight"]["fields"]) == ["profile"]


def test_similar_people_renormalizes_weights_and_skips_empty_inputs():
    no_resume = similar_people_query(CID, ME, "SRE", ["k8s"])
    weights = [r["weight"] for r in no_resume["retriever"]["linear"]["retrievers"]]
    assert weights == [0.8, 0.2]
    only_profile = similar_people_query(CID, ME, "SRE", [])
    assert "retriever" not in only_profile
    assert only_profile["query"]["bool"]["must"][0]["semantic"]["field"] == "profile"
    assert similar_people_query(CID, ME, "", []) is None


def test_recommend_talks_excludes_blockouts_in_es_and_falls_back_to_schedule_order():
    blockouts = [("2026-11-09T19:45:00+00:00", "2026-11-09T20:15:00+00:00")]
    body = recommend_talks_query(CID, "SRE", blockouts)
    q = body["query"]["bool"]
    assert q["must"] == [{"semantic": {"field": "semantic_content", "query": "SRE"}}]
    assert q["must_not"][0]["bool"]["filter"] == [
        {"range": {"start_time": {"lt": blockouts[0][1]}}},
        {"range": {"end_time": {"gt": blockouts[0][0]}}},
    ]
    assert {"term": {"confirmed": True}} in q["filter"]
    assert "semantic_content" not in body["source"]
    assert set(body["source"]) <= set(TALKS_INDEX["mappings"]["properties"])
    empty = recommend_talks_query(CID, "", [])
    assert "must" not in empty["query"]["bool"]
    assert empty["sort"] == [{"start_time": "asc"}]


def test_audience_and_archive_queries_never_touch_private_fields():
    talk = {"title": "eBPF", "abstract": "security"}
    audience = talk_audience_query(CID, talk)
    assert audience["source"] == SAFE_SOURCE
    assert audience["query"]["bool"]["must"][0]["semantic"]["query"] == "eBPF. security"
    assert "highlight" not in audience
    archive = similar_past_talks_query(talk)
    assert archive["index"] == "talks-archive"
    assert archive["query"]["semantic"]["field"] == "semantic_content"


def test_person_hit_projects_safe_fields_and_why():
    hit = {
        "_score": 0.7,
        "_source": {"attendee_id": "a", "name": "Ana", "bio": "leak"},
        "highlight": {"profile": ["SRE at a fintech"]},
    }
    assert person_hit(hit) == {
        "attendee_id": "a",
        "name": "Ana",
        "score": 0.7,
        "why": "SRE at a fintech",
    }


def test_extract_resume_text_plain():
    assert extract_resume_text(b" hello\n", "text/plain") == "hello"


def test_physical_index_names_are_versioned_per_alias():
    assert PHYSICAL_INDEX == {
        "attendees": "attendees-v1",
        "talks": "talks-v1",
        "connections": "connections-v1",
    }


def _live(props):
    return {"dynamic": "strict", "properties": props}


def test_mapping_mismatches_accepts_identical_and_tolerates_live_extras_in_semantic_fields():
    live = {
        "dynamic": "strict",
        "properties": {
            k: (v | {"model_settings": {"task_type": "text_embedding"}})
            if v.get("type") == "semantic_text"
            else v
            for k, v in ATTENDEES_INDEX["mappings"]["properties"].items()
        },
    }
    assert mapping_mismatches(ATTENDEES_INDEX["mappings"], live) == []


def test_mapping_mismatches_reports_missing_type_inference_and_unexpected_fields():
    expected = _live(
        {
            "name": {"type": "text"},
            "profile": {"type": "semantic_text", "inference_id": "jina"},
            "resume_text": {"type": "semantic_text", "inference_id": "jina"},
            "blockout_times": {"properties": {"start_time": {"type": "date"}}},
        }
    )
    live = _live(
        {
            "name": {"type": "keyword"},
            "profile": {"type": "semantic_text", "inference_id": "elser"},
            "headline": {"type": "text"},
            "blockout_times": {"properties": {"start_time": {"type": "text"}}},
        }
    )
    assert mapping_mismatches(expected, live) == [
        "type:name=keyword!=text",
        "inference_id:profile=elser",
        "missing:resume_text",
        "type:blockout_times.start_time=text!=date",
        "unexpected:headline",
    ]


def test_mapping_mismatches_allows_extras_when_not_strict():
    expected = {"dynamic": True, "properties": {"status": {"type": "keyword"}}}
    live = {"dynamic": "true", "properties": {"status": {"type": "keyword"}, "x": {"type": "long"}}}
    assert mapping_mismatches(expected, live) == []
