from pathlib import Path

import pytest

from app import schedule_fetch
from app.schedule_adapters import (
    clean_sched_location,
    is_non_talk,
    looks_like_lf_events,
    parse_lf_events_html,
    split_summary,
)
from app.schedule_fetch import UnsafeUrlError, normalize_url, resolve_public_address
from app.schedule_parser import (
    find_structured_link,
    html_to_text,
    normalize_talks,
    parse_bytes,
    rewrite_url,
    sniff_format,
)

FIXTURES = Path(__file__).parent / "fixtures" / "schedules"


def parse(name: str, tz: str | None = None) -> dict:
    return parse_bytes(
        conference_id="conf",
        body=(FIXTURES / name).read_bytes(),
        content_type=None,
        filename=name,
        tz_name=tz,
        source_url=None,
    )


# ---------------------------------------------------------------- Sched / iCalendar


def test_sched_ics_splits_title_and_speakers_and_skips_breaks() -> None:
    draft = parse("sched-kubecon-na-2025.ics")
    assert draft["source_format"] == "ics"
    assert draft["timezone"] == "UTC"
    titles = {t["title"] for t in draft["talks"]}
    assert "Registration + Badge Pick-Up" not in titles
    assert not any("Coffee Break" in t for t in titles)
    assert any("Skipped 2 non-talk rows" in w for w in draft["warnings"])
    salesforce = next(t for t in draft["talks"] if t["title"].startswith("1000 Clusters"))
    assert salesforce["title"] == (
        "1000 Clusters, 1 Brain: Salesforce’s Approach To Self-Healing Using AIOps"
    )
    assert salesforce["speakers"] == ["Vikram Venkataraman", "Srikanth Rajan"]
    assert salesforce["room"] == "Building B | Level 5 | Thomas Murphy Ballroom 1"
    assert salesforce["track"] == ["AI + ML"]
    assert salesforce["start_time"] == "2025-11-11T17:00:00+00:00"
    assert salesforce["end_time"] == "2025-11-11T17:30:00+00:00"
    assert "&nbsp;" not in (salesforce["abstract"] or "")


def test_split_summary_keeps_dashes_and_ampersands_inside_titles() -> None:
    title, speakers = split_summary("Kubernetes - Past, Present & Future - Flynn, Buoyant")
    assert title == "Kubernetes - Past, Present & Future"
    assert speakers == ["Flynn"]
    assert split_summary("Lightning Talk With No Speaker") == ("Lightning Talk With No Speaker", [])


def test_clean_sched_location_strips_city_suffix() -> None:
    assert clean_sched_location("Building B | Level 5 | Ballroom 1, Atlanta, GA, USA") == (
        "Building B | Level 5 | Ballroom 1"
    )
    assert clean_sched_location("Room 12b") == "Room 12b"


def test_pretalx_ics_resolves_tzid_without_conference_timezone() -> None:
    draft = parse("pretalx-pyconde-2025.ics")
    assert len(draft["talks"]) == 4
    talk = next(t for t in draft["talks"] if t["title"] == "Reasonable AI")
    assert talk["speakers"] == ["Kristian Kersting"]
    assert talk["start_time"] == "2025-04-23T10:30:00+02:00"
    assert talk["track"] == []


# ---------------------------------------------------------------- Sessionize


def test_sessionize_all_resolves_ids_and_skips_service_sessions() -> None:
    draft = parse("sessionize-kotlinconf-2026-all.json")
    assert draft["source_format"] == "sessionize"
    titles = [t["title"] for t in draft["talks"]]
    assert "Registration" not in titles
    assert "Coffee Break" not in titles
    workshop = next(t for t in draft["talks"] if t["title"].startswith("Building Shared UI"))
    assert workshop["speakers"] == ["Márton Braun", "Victor Kropp"]
    assert workshop["room"] == "Room 12b"
    assert workshop["start_time"] == "2026-05-20T07:00:00+00:00"


def test_sessionize_floating_times_require_a_conference_timezone() -> None:
    without = parse("sessionize-aiengineer-2025-all-floating.json")
    assert without["talks"] == []
    assert any("no conference timezone" in w for w in without["warnings"])

    with_tz = parse("sessionize-aiengineer-2025-all-floating.json", "America/Los_Angeles")
    assert len(with_tz["talks"]) == 4
    assert all(t["start_time"].endswith("-07:00") for t in with_tz["talks"])
    assert any("floating times" in w for w in with_tz["warnings"])


# ---------------------------------------------------------------- pretalx / frab


def test_pretalx_json_uses_offsets_and_time_zone_name() -> None:
    draft = parse("pretalx-pyconde-2025-schedule.json")
    assert draft["source_format"] == "frab_json"
    assert draft["timezone"] == "Europe/Berlin"
    assert len(draft["talks"]) == 6
    keynote = next(t for t in draft["talks"] if t["title"] == "Reasonable AI")
    assert keynote["track"] == ["Keynote"]
    assert keynote["room"] == "Zeiss Plenary (Spectrum)"
    assert keynote["end_time"] == "2025-04-23T11:15:00+02:00"


def test_frab_xml_derives_end_from_duration_and_unescapes_abstract() -> None:
    draft = parse("frab-fosdem-2025-schedule.xml")
    assert draft["source_format"] == "frab_xml"
    assert draft["timezone"] == "Europe/Brussels"
    welcome = next(t for t in draft["talks"] if t["title"] == "Welcome to FOSDEM 2025")
    assert welcome["start_time"] == "2025-02-01T09:30:00+01:00"
    assert welcome["end_time"] == "2025-02-01T09:50:00+01:00"
    assert welcome["speakers"] == ["FOSDEM Staff", 'Richard "RichiH" Hartmann']
    assert "<p>" not in welcome["abstract"]
    assert welcome["track"] == ["Keynotes"]


def test_frab_xml_rejects_entity_expansion() -> None:
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE schedule [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>
<schedule><conference><title>&b;</title></conference></schedule>"""
    with pytest.raises(Exception):
        parse_bytes(
            conference_id="c",
            body=evil,
            content_type=None,
            filename="x.xml",
            tz_name=None,
            source_url=None,
        )


# ---------------------------------------------------------------- Linux Foundation events HTML


def test_lf_events_html_is_parsed_deterministically() -> None:
    body = (FIXTURES / "lf-events-kubecon-na-2026-schedule.html").read_bytes()
    assert sniff_format(body, None) == "html"
    assert looks_like_lf_events(body)
    assert not looks_like_lf_events(
        (FIXTURES / "html-devopsdays-chicago-2025-program.html").read_bytes()
    )

    draft = parse("lf-events-kubecon-na-2026-schedule.html", "America/Denver")
    assert draft["source_format"] == "lf_events_html"
    assert draft["timezone"] == "America/Denver"
    assert len(draft["talks"]) == 35
    assert any("Skipped 8 non-talk rows" in w for w in draft["warnings"])
    titles = {t["title"] for t in draft["talks"]}
    assert "Registration + Badge Pick-Up" not in titles
    assert "Coat + Bag Check" not in titles
    assert "☕ Coffee Break" not in titles
    assert "Solutions Showcase" not in titles

    demo = next(t for t in draft["talks"] if t["title"].startswith("Demo Theater: Agentic AI"))
    assert demo["speakers"] == ["Yodar Shafrir"]
    assert demo["room"] == (
        "Salt Palace | Level 1 | Solutions Showcase | Hall 1 | Alpine Overlook Zone | Demo Theater"
    )
    assert demo["track"] == ["Sponsor Demo Theater"]
    assert demo["start_time"] == "2026-11-10T10:50:00-07:00"
    assert demo["end_time"] == "2026-11-10T11:10:00-07:00"
    assert demo["abstract"].startswith("Autonomous workloads need autonomous infrastructure.")
    assert "<p>" not in demo["abstract"]

    panel = next(t for t in draft["talks"] if t["title"] == "Welcome + Opening Remarks")
    assert panel["speakers"][:3] == ["Jonathan Bryce", "Chris Aniszczyk", "Robert Nishihara"]
    assert len(panel["speakers"]) == 6

    intro = next(t for t in draft["talks"] if t["title"] == "Project Lightning Talk Opening/ Intro")
    assert intro["speakers"] == ["Robert Sirchia"]
    assert intro["abstract"] is None
    assert intro["start_time"] == "2026-11-09T09:30:00-07:00"

    colocated = next(t for t in draft["talks"] if t["title"].startswith("ArgoCon Hosted by CNCF"))
    assert colocated["speakers"] == []
    assert colocated["track"] == ["CNCF-hosted Co-located Events"]


def test_lf_events_html_without_timezone_drops_floating_times() -> None:
    draft = parse("lf-events-kubecon-na-2026-schedule.html")
    assert draft["source_format"] == "lf_events_html"
    assert draft["talks"] == []
    assert any("no conference timezone" in w for w in draft["warnings"])


def test_lf_events_html_skips_untimed_sessions_and_dedupes_ids() -> None:
    session = """
    <div class="sess-wrap"><a class="sess-link" href="/s/?id={id}" data-session-id="{id}">
      <div class="sess"><div class="sess__title">{title}</div>
      <span class="sess__room">Room 1</span></div></a>
      <div class="sess__seo" hidden><div class="sess__seotime">{times}</div></div></div>"""
    times = (
        '<time datetime="2026-11-10T09:00:00">x</time><time datetime="2026-11-10T09:30:00">y</time>'
    )
    body = (
        "<html><body>"
        + session.format(id=1, title="Kept", times=times)
        + session.format(id=1, title="Kept again", times=times)
        + session.format(id=2, title="Not scheduled", times="")
        + "</body></html>"
    ).encode()
    draft = parse_lf_events_html(body, "America/Denver")
    assert [t["title"] for t in draft.talks] == ["Kept"]
    assert any("Skipped 1 sessions that have no scheduled time" in w for w in draft.warnings)


def test_non_talk_regex_ignores_leading_emoji() -> None:
    assert is_non_talk("☕ Coffee Break", [])
    assert is_non_talk("Coat + Bag Check", [])
    assert not is_non_talk("Breaking up Is Hard, but the Future Is with Helm 4", [])
    assert not is_non_talk("Coat of Arms: Designing Kubernetes Operators", [])


# ---------------------------------------------------------------- detection and normalize


def test_sniff_format_ignores_content_type_when_bytes_are_clear() -> None:
    assert sniff_format(b"\xef\xbb\xbfBEGIN:VCALENDAR\r\n", "text/html") == "ics"
    assert sniff_format(b'{"sessions": []}', "text/javascript") == "json"
    assert sniff_format(b"<?xml version='1.0'?><schedule/>", "application/octet-stream") == "xml"
    assert sniff_format(b"%PDF-1.7", None) == "pdf"
    assert sniff_format(b"\x89PNG\r\n", None) == "image/png"
    assert sniff_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ", None) == "image/webp"
    assert sniff_format(b"document.write('x')", "text/javascript") == "sessionize_embed"
    assert sniff_format(b"<!doctype html><html>", None) == "html"
    assert sniff_format(b"garbage", "application/octet-stream") == "unknown"


def test_rewrite_url_points_known_hosts_at_their_exports() -> None:
    assert rewrite_url("https://kccncna2025.sched.com/list/descriptions/") == (
        "https://kccncna2025.sched.com/all.ics"
    )
    assert rewrite_url("webcal://kccncna2025.sched.com/all.ics") == (
        "https://kccncna2025.sched.com/all.ics"
    )
    assert rewrite_url("https://sessionize.com/api/v2/2r0suvtg/view/GridSmart") == (
        "https://sessionize.com/api/v2/2r0suvtg/view/All"
    )
    assert rewrite_url("https://pretalx.com/pyconde-pydata-2025/schedule/") == (
        "https://pretalx.com/pyconde-pydata-2025/schedule/export/schedule.json"
    )
    assert rewrite_url("https://example.org/agenda?x=1") == "https://example.org/agenda?x=1"


def test_find_structured_link_in_html() -> None:
    page = '<script src="https://sessionize.com/api/v2/abc123/view/Sessions?under=true"></script>'
    assert find_structured_link(page, "https://conf.example") == (
        "https://sessionize.com/api/v2/abc123/view/All"
    )
    assert find_structured_link('<a href="/all.ics">ics</a>', "https://x.sched.com/") == (
        "https://x.sched.com/all.ics"
    )
    assert find_structured_link("<p>nothing</p>", None) is None


def test_normalize_drops_invalid_and_duplicate_talks() -> None:
    warnings: list[str] = []
    talks = normalize_talks(
        [
            {"title": "A", "start_time": "2026-01-01T10:00:00Z", "end_time": "2026-01-01T11:00Z"},
            {"title": "a", "start_time": "2026-01-01T10:00:00Z", "end_time": "2026-01-01T11:00Z"},
            {"title": "B", "start_time": "2026-01-01T10:00:00Z", "end_time": "2026-01-01T09:00Z"},
            {"title": "C", "start_time": "2026-01-01T10:00:00", "end_time": "2026-01-01T11:00:00"},
            {"title": "", "start_time": "2026-01-01T10:00:00Z", "end_time": "2026-01-01T11:00Z"},
        ],
        warnings,
        None,
    )
    assert [t["title"] for t in talks] == ["A"]
    assert len(warnings) == 3


def test_html_to_text_keeps_rows_and_drops_scripts() -> None:
    text = html_to_text((FIXTURES / "html-devopsdays-chicago-2025-program.html").read_bytes())
    assert "All times are in US Central Time" in text
    assert "<script" not in text and "function" not in text.lower()[:200]
    assert "Reid Savage" in text


def test_html_to_text_collapses_template_indentation() -> None:
    body = (
        b"<html><body>\n\t\t\t<div>\n\t\t\t\t<p>Title</p>\n\t\t\t\t\t<p>Room</p>\n"
        b"\t\t\t</div></body></html>"
    )
    assert html_to_text(body) == "Title\n\nRoom"
    table = b"<table><tr><td>\n\t\t9:00</td><td>\t\tTalk</td></tr></table>"
    assert html_to_text(table) == "9:00\tTalk"


# ---------------------------------------------------------------- SSRF policy


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/all.ics",
        "https://user:pw@example.com/all.ics",
        "https://example.com:8443/all.ics",
        "https://localhost/all.ics",
        "https://127.0.0.1/all.ics",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/all.ics",
        "https://10.0.0.5/all.ics",
        "https://[::ffff:10.0.0.5]/all.ics",
        "ftp://example.com/all.ics",
    ],
)
def test_unsafe_urls_are_rejected_before_any_connection(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        normalized = normalize_url(url)
        resolve_public_address(normalized.split("/")[2].strip("[]"))


def test_normalize_url_rewrites_webcal() -> None:
    assert normalize_url("webcal://x.sched.com/all.ics") == "https://x.sched.com/all.ics"


def test_private_dns_answer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        schedule_fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.1.2.3", 443))],
    )
    with pytest.raises(UnsafeUrlError):
        resolve_public_address("rebind.example")


def test_public_dns_answer_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        schedule_fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    assert resolve_public_address("example.com") == "93.184.216.34"


def test_split_summary_does_not_turn_colocated_notices_into_speakers() -> None:
    assert split_summary(
        "CiliumCon Hosted by CNCF - Half Day Event | ALL ACCESS PASS REQUIRED"
    ) == (
        "CiliumCon Hosted by CNCF - Half Day Event | ALL ACCESS PASS REQUIRED",
        [],
    )
