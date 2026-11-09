# Conference schedule formats

This is a reference for the schedule importer (`POST /upload-schedule` → draft → `POST /confirm-schedule`). It covers what real public schedules look like and how each one maps onto our talk shape. Everything here was checked against live sources on 2026-11-09. Trimmed real samples are in `backend/tests/fixtures/schedules/` (see its `README.md`).

**Target shape** (`SCHEDULE_SCHEMA` in `app/schedule_parser.py`): `title` (required), `abstract`, `speakers: [name]`, `room`, `track: [str]`, `start_time`/`end_time` (timezone-aware ISO-8601, required). `/confirm-schedule` normalizes the times to UTC and derives `talk_id` from title, start, room, track and speakers.

## Summary

| Source | How common for tech conferences | How to get it | Deterministic? | Timezone |
|---|---|---|---|---|
| Sched | Very common for large foundation and corporate events: every Linux Foundation/CNCF event (KubeCon, OSS Summit, co-located days) | `https://<event>.sched.com/all.ics` | Yes (ics) | UTC `Z` |
| Sessionize | The most common CFP+schedule tool for community and dev conferences (KotlinConf, AI Engineer, NDC, DevFests, many DevOpsDays/Cloud Native Days) | `https://sessionize.com/api/v2/<id>/view/All` | Yes (JSON) | UTC `Z` **or floating**, depending on an organizer setting |
| pretalx (incl. self-hosted) | Common in Python and open-source communities (PyCon DE, EuroPython, FOSDEM's CFP, CCC/c3voc events) | `https://<host>/<slug>/schedule/export/schedule.json` | Yes (frab JSON) | Offsets on every time plus `time_zone_name` |
| frab/Pentabarf XML | FOSDEM, CCC, and anything that exports `schedule.xml` (pretalx does too) | `https://fosdem.org/<year>/schedule/xml` | Yes (XML) | Offsets on `date` plus `time_zone_name` |
| Luma | Common for meetups and hackathons. It describes one event, not a multi-session agenda | `https://luma.com/<slug>` | No agenda, only free text | Event has an IANA `timezone` |
| Eventbrite / Meetup | Ticketing/RSVP. Usually no agenda | event page | No (LLM on description, if any) | Event-level only |
| Plain HTML agenda | Very common for small and mid-size conferences (Hugo/Jekyll/WordPress sites) | the page | LLM | Usually prose ("All times in US Central") or none |
| PDF program | Common for academic and regional events | upload | LLM (PDF input) | Rarely stated |
| Image / screenshot | What organizers have when nothing else exists | upload | LLM (vision) | Almost never |

"How common" is a qualitative read from the sources sampled here and the tools' public customer lists. It is not a measured market share.

---

## 1. Sched (KubeCon / CNCF / Linux Foundation)

**How to get it.**
- `https://<event>.sched.com/all.ics` returns the whole public schedule as `text/calendar`, with no key and no login. For example, `https://kccncna2025.sched.com/all.ics` is 685 KB with 542 events, and is byte-identical to `talks-playground/data/kubecon-ics/kccncna2025.ics`.
- HTML: `https://<event>.sched.com/` and `/list/descriptions/` (2.6 MB). Times are local, labelled with `<h3> 8:00am <span class='tz'>EST</span>`, under day headers like `<b>Monday</b>, November 10` that carry no year. Each session is `<span class='event'><a href='event/<short>/<slug>' id='<uid>'><span class="session-title">…</span> <span class="vs">room</span></a>`. The page has a schema.org `Event` JSON-LD block for the conference as a whole, with dates only.
- **API: not usable.** `https://<event>.sched.com/api/...` returns `ERR: Authorization failed.` without the organizer's API key, and `robots.txt` disallows `/api`, `/grid/*`, `/*?*` and `/print`. `/all.ics` is not disallowed.
- **Don't trust HEAD.** A `HEAD` request to `/all.ics` returned `text/html`, while the `GET` returned `text/calendar`. Sniff the body instead.

**Example** (`fixtures/schedules/sched-kubecon-na-2025.ics`, CRLF, lines **not** folded even when longer than 75 octets):
```
PRODID:-//Sched.com KubeCon + CloudNativeCon North America 2025//EN
X-WR-TIMEZONE:UTC
BEGIN:VEVENT
DTSTART:20251111T170000Z
DTEND:20251111T173000Z
SUMMARY:1000 Clusters\, 1 Brain: Salesforce’s Approach To Self-Healing Using AIOps - Vikram Venkataraman\, AWS & Srikanth Rajan\, Salesforce
DESCRIPTION:…
CATEGORIES:AI + ML
LOCATION:Building B | Level 5 | Thomas Murphy Ballroom 1\, Atlanta\, GA\, USA
UID:db04febfddddb5504ed19b9f0667fb52
URL:http://kccncna2025.sched.com/event/db04febfddddb5504ed19b9f0667fb52
END:VEVENT
```

**Mapping.**
| Ours | Sched ics |
|---|---|
| title | `SUMMARY` up to the **last** ` - ` (`rsplit(" - ", 1)`). Titles themselves contain ` - ` and `&`. If there is no ` - `, the whole summary is the title. |
| speakers | `SUMMARY` after the last ` - `, split on ` & ` (and `;`), then take the text before the first `,` (the rest is role and company). Single-name speakers like `Flynn, Buoyant` work the same way. |
| abstract | `DESCRIPTION`, unescaped. It contains `&nbsp;` and other HTML entities, so run `html.unescape`. |
| room | `LOCATION`. It includes the city suffix (`…, Atlanta, GA, USA`). Strip the trailing `, <city>, <region>, <country>` if you want a clean room name. |
| track | `[CATEGORIES]`, upper-case (`AI + ML`), sometimes with emoji (`🚨 CONTRIBFEST`). Title-case it for display. |
| start/end | `DTSTART`/`DTEND`, always UTC `Z`. |

**Gotchas.** Non-talks are mixed in: `REGISTRATION`, `BREAKS` (`Coffee Break ☕`, `Lunch 🍲`), and `SPONSOR-HOSTED CO-LOCATED EVENT` rows titled `… | SEPARATE REGISTRATION REQUIRED` that span a whole day. The previous parser (`talks-playground/scripts/build_talks.py`) dropped `REGISTRATION`/`BREAKS` and any abstract shorter than 40 characters. A better default is to keep them in the draft but flag them in `warnings` so the organizer can deselect them, because "Lunch" is useful on an attendee's timeline even though we shouldn't embed it for recommendations. There is also `Project Lightning Talk: Lunch Break | ATTENDEES ON OWN`, a break dressed up as a talk.

**Deterministic.** If a user pastes any `*.sched.com` URL, rewrite it to `https://<host>/all.ics` and use the ics adapter. Do not scrape the HTML.

## 2. Sessionize

**How to get it.** `https://sessionize.com/api/v2/<endpointId>/view/<View>` is public, needs no key, and only works if the organizer has created an API endpoint. The **id is per endpoint, not per event, and the endpoint has a fixed output format.** For example, ApacheCon EU's id `goe3u7ll` serves `text/javascript` (a `document.write` embed widget) on *every* view, including `view/All`. Only JSON endpoints are useful to us: check that `Content-Type` is `application/json`. To find ids, look for `sessionize.com/api/v2/<id>/view/…` in the conference site's HTML, scripts, or repo config. `view/xml` returned 404 on a JSON endpoint.

| View | Shape |
|---|---|
| `All` | `{sessions[], speakers[], questions[], categories[], rooms[]}`. Normalized: sessions reference speakers, rooms and category items by id. **Use this.** |
| `Sessions` | `[{groupId, groupName, sessions[]}]`. Denormalized: `speakers: [{id, name}]`, `categories: [{name, categoryItems:[{name}]}]`, `room` (a string). |
| `Speakers` | `[{id, fullName, bio, tagLine, profilePicture, sessions:[{id,name}], links, …}]` |
| `GridSmart` | `[{date, rooms:[{id, name, sessions[]}], timeSlots:[{slotStart, rooms:[{session}]}]}]`. The same sessions as `Sessions`, nested by day and room. It is about 2.4× larger. |

**Example** (`fixtures/schedules/sessionize-kotlinconf-2026-all.json`, trimmed):
```json
{"sessions": [{"id": "1151012", "title": "Building Shared UI With Compose Multiplatform. Part 1.",
   "description": "…", "startsAt": "2026-05-20T07:00:00Z", "endsAt": "2026-05-20T08:30:00Z",
   "isServiceSession": false, "isPlenumSession": false,
   "speakers": ["5307510b-…", "e21ee3c3-…"], "categoryItems": [447460, 389139], "roomId": 80293, "status": "Accepted"}],
 "speakers": [{"id": "94fc2fde-…", "fullName": "Alejandro Serrano Mena", "tagLine": "Researcher @ …, JetBrains", "sessions": [1151104], "bio": "…"}],
 "categories": [{"id": 108055, "title": "Session format", "items": [{"id": 447460, "name": "Workshop"}]},
                {"id": 108056, "title": "Level", "items": [{"id": 389139, "name": "Intermediate"}]},
                {"id": 108057, "title": "Category", "items": []}],
 "rooms": [{"id": 80293, "name": "Room 12b", "sort": 10}]}
```

**Mapping.** `title` ← `title`; `abstract` ← `description` (nullable); `speakers` ← each `speakers[]` id looked up as `speakers[].fullName`; `room` ← `rooms[id==roomId].name` (`roomId` can be null); `track` ← names of `categoryItems` looked up across `categories[].items`; `start/end` ← `startsAt`/`endsAt`.

**Gotchas.**
- **Times may be floating.** KotlinConf returns `2026-05-20T07:00:00Z`, but AI Engineer World's Fair returns `2025-06-03T09:00:00` with no offset, and nothing in the payload says which zone that is (the venue was San Francisco). This depends on the endpoint's "Use UTC timezone for schedule" setting. A naive time **must** be localized with the conference timezone (see §6), never treated as UTC.
- Category groups are organizer-defined. "Session format" and "Level" are not tracks. Use groups whose title matches `track|category|topic|theme` when any exist, otherwise use all items. `categories` can be `[]` entirely (AI Engineer).
- `isServiceSession: true` marks breaks and registration. These have no speakers and **GUID ids, while talks have numeric-string ids**. Treat them like Sched's `BREAKS`.
- Type mismatch: `session.id` is a string (`"1151104"`), but `speaker.sessions[]` holds ints (`1151104`). `isPlenumSession: true` marks keynotes and other all-rooms sessions.
- Unscheduled sessions (null `startsAt`) can appear before the schedule is published. Skip them and add a warning.

**Deterministic.** Yes.

## 3. pretalx

**How to get it.** This works the same on pretalx.com and on self-hosted instances (`pretalx.fosdem.org`, `program.europython.eu`, …). For event `<slug>`:
- `GET /api/events/<slug>/` returns `{name: {en: …}, slug, date_from, date_to, timezone: "Europe/Berlin", custom_domain, …}`. This is the cheapest way to confirm a host is pretalx and to get the event timezone.
- `GET /<slug>/schedule/export/schedule.json` returns frab-compatible JSON (`$schema: https://c3voc.de/schedule/schema.json`). **Use this.**
- `GET /<slug>/schedule/export/schedule.xml` returns frab XML (§4), and `/schedule/export/schedule.ics` returns an ics with `VTIMEZONE` and `DTSTART;TZID=Europe/Berlin:…`, RFC-folded lines, `SUMMARY:Title - Speaker`, and **no `CATEGORIES`**, so the track is lost.
- REST: `/api/events/<slug>/submissions/` is paginated, references speakers and tracks by id, and uses i18n dicts like `name: {"en": …}`. `/api/events/<slug>/talks/` now returns **404** on current pretalx. Don't build on the REST API; the export is a single request with names inline.

**Example** (`fixtures/schedules/pretalx-pyconde-2025-schedule.json`, trimmed):
```json
{"$schema": "https://c3voc.de/schedule/schema.json", "generator": {"name": "pretalx", "version": "2026.3.0.dev0"},
 "schedule": {"conference": {"acronym": "pyconde-pydata-2025", "time_zone_name": "Europe/Berlin",
   "rooms": [{"name": "Zeiss Plenary (Spectrum)", …}], "tracks": [{"name": "Keynote", …}],
   "days": [{"index": 1, "date": "2025-04-23", "rooms": {"Zeiss Plenary (Spectrum)": [
     {"guid": "32ce63ca-…", "code": "3MNGN8", "date": "2025-04-23T10:30:00+02:00", "start": "10:30",
      "end": "2025-04-23T11:15:00+02:00", "duration": "00:45", "room": "Zeiss Plenary (Spectrum)",
      "title": "Reasonable AI", "track": "Keynote", "type": "Keynote", "abstract": "…", "description": "…",
      "persons": [{"code": "B37CUN", "public_name": "Kristian Kersting", "biography": "…"}]}]}}]}}}
```

**Mapping.** Iterate `days[].rooms{name: [talk]}`. `title` ← `title`, plus `": " + subtitle` if non-empty. `abstract` ← `abstract`, or `description` if empty (often both are filled with the same text). `speakers` ← `persons[].public_name` (fall back to `name`). `room` ← `room`. `track` ← `[track]` if not null. `start` ← `date`. `end` ← `end` if present, otherwise `date + duration`.

**Gotchas.** Breaks are not in the export, only submissions, so there is nothing to filter. `track` can be null. `type` (`Talk`, `Tutorial`, `Sponsored Talk`, `Kids Workshop`) is useful as a second track value or for filtering. The only `end` in older frab JSON may be `duration` (`"HH:MM"`). Fields are Markdown, not HTML.

**Deterministic.** Yes.

## 4. frab / Pentabarf XML (FOSDEM, CCC, pretalx `schedule.xml`)

**How to get it.** `https://fosdem.org/<year>/schedule/xml` (3.4 MB and 1,105 events for 2025). It is served as **`application/octet-stream`**, so you can't rely on Content-Type. Also available as pretalx `/<slug>/schedule/export/schedule.xml` (`text/xml`).

**Example** (`fixtures/schedules/frab-fosdem-2025-schedule.xml`, trimmed):
```xml
<schedule>
  <conference><acronym>fosdem-2025</acronym><title>FOSDEM 2025</title>
    <time_zone_name>Europe/Brussels</time_zone_name></conference>
  <tracks><track slug="keynote">Keynotes</track>…</tracks>
  <day index="1" date="2025-02-01" start="2025-02-01T09:00:00+01:00" end="2025-02-02T08:59:00+01:00">
    <room name="Janson" slug="janson">
      <event guid="fdbc5919-…" id="6712">
        <date>2025-02-01T09:30:00+01:00</date><start>09:30</start><duration>00:20</duration>
        <room>Janson</room><title>Welcome to FOSDEM 2025</title><subtitle/>
        <track slug="keynote">Keynotes</track><type>keynote</type>
        <abstract>&lt;p&gt;FOSDEM welcome and opening talk.&lt;/p&gt;</abstract>
        <persons><person id="2">FOSDEM Staff</person><person id="1324">Richard "RichiH" Hartmann</person></persons>
      </event>
```

**Mapping.** `title` ← `title` (plus `subtitle`). `abstract` ← `abstract` (or `description`): it is **HTML-escaped HTML**, so unescape it and strip tags. `speakers` ← `persons/person` text. `room` ← `room` (or the parent `room/@name`). `track` ← `track` text. `start` ← `date` (with offset). `end` ← `date + duration`, because **there is no end element**.

**Gotchas.** Pentabarf and pretalx variants differ slightly. FOSDEM puts `<tracks>` at the top level, while pretalx puts `<track name=…>` inside `<conference>`. FOSDEM's `day_change` is 09:00, so a day's events can run past midnight. Older files may lack an offset on `<date>`; in that case combine `day/@date` + `<start>` with `time_zone_name`. Parse with **`defusedxml.ElementTree`**, never plain `xml.etree` on untrusted uploads (entity-expansion and XXE).

**Deterministic.** Yes.

## 5. Unstructured sources (LLM fallback)

| Source | What we found | What the LLM needs | Pitfalls |
|---|---|---|---|
| **Luma** (`luma.com/<slug>`, `lu.ma/<slug>`) | `__NEXT_DATA__` JSON holds `start_at`/`end_at` (UTC) and `timezone: "America/Denver"` for the *whole event*, plus `sessions: []` (Luma's multi-session feature, empty for luma.com/cnh). Any agenda lives in `description_mirror` (ProseMirror rich text) as prose. | Plain text pulled from `description_mirror`, **plus the event `timezone` and date** as hints. | Usually no agenda at all. Return zero talks and a warning instead of inventing one. A single-event Luma page is not a schedule. |
| **Eventbrite / Meetup** | Event-level date and time only. Agendas are optional free text in the description, or an image. | Description text plus the event timezone. | Same as Luma. Many ticket pages are JS-rendered and bot-protected, so expect fetch failures. |
| **Plain HTML agenda** (e.g. `fixtures/schedules/html-devopsdays-chicago-2025-program.html`) | `All times are in US Central Time` (prose only), `March 18, 2025` as a day header, `<a>Reid Savage - Anti-DevOps: SRE at Honeycomb</a>`, `08:00 / 09:00` time cells, `Break`/`Sponsors`/`Lunch` rows, a 5-talk `Ignites` block inside one 30-minute slot, parallel `Open Space #1` and workshop rows. | Visible text with structure preserved (one line per row, headings kept, `<a>` text kept). Drop `script`/`style`/`nav`/`footer`. If there is schema.org `Event` JSON-LD, pass it too. | Speaker and title share one string, and the order varies (`Name - Title` here, `Title - Name` in Sched). The date and year come from a header far above the row. A multi-track grid becomes ambiguous once flattened to text (tables need `\t` between cells). Breaks and sponsor slots are not talks. Grouped lightning talks share one slot, so either split the slot evenly or give all of them the slot times with a warning. JS-rendered sites (Sched embeds, Sessionize widgets) are empty without JS. Detect the embed and use the API instead. |
| **PDF program** | Already supported for upload (`input_file`). | Send the PDF as `input_file` (the model sees layout). `pypdf` is already a backend dependency if you want to pre-extract text to chunk by day or cut tokens. | Multi-column grids lose column order in text extraction, so prefer sending the file. There is rarely a timezone, the year is often missing, and footnotes and sponsors get mixed in. |
| **Image / screenshot** | Already supported (`input_image`). | The image itself (PNG/JPEG/WEBP), unmodified. | Grids are read row by row, so rooms come from column headers. Small fonts cause OCR errors in names. There is never a timezone. Multiple screenshots may be needed for multi-day events. |

**For every LLM path,** the prompt must include the **conference timezone and dates** (§6). Tell the model to emit local wall-clock times plus a `tz` hint, or offsets computed from that zone. Tell it to put non-talk rows in `warnings` or flag them instead of inventing abstracts. Then **validate on the server**: parse every `start_time`/`end_time`, require `end > start`, require times inside the conference date range, and reject naive times. Large conferences (KubeCon has 540+ sessions) blow past output-token limits in one call, so chunk by day or page and merge.

## 6. Timezones

| Format | Where the zone lives | What to do |
|---|---|---|
| Sched ics | `DTSTART:…Z` (UTC) and `X-WR-TIMEZONE:UTC` | Nothing. The values are already UTC. |
| Generic ics | `DTSTART;TZID=Europe/Berlin:…` + `VTIMEZONE` (pretalx), `…Z`, or **floating** `DTSTART:20250423T103000` | `icalendar` resolves `TZID` to `zoneinfo`. For floating or `VALUE=DATE` values, localize with the conference zone. |
| Sessionize | `…Z` or **floating** (endpoint setting); no zone field | If naive, localize with the conference zone. |
| pretalx JSON / frab XML | Offset on every `date` + `time_zone_name` | Use the offset as-is. Use `time_zone_name` when the offset is missing (older frab). |
| Luma | Event `timezone` (IANA) | Use it as the hint for the description text. |
| HTML / PDF / image | Prose ("All times in US Central"), abbreviations (`EST` in Sched HTML), or nothing | Give the LLM the conference zone. **Don't map abbreviations** (`CST` is ambiguous), resolve to IANA. |

**Conference timezone source, in priority order:** an explicit organizer field on the conference record (add `timezone` as IANA; this is the only reliable fallback and is required for floating sources), then the timezone stated by the source (pretalx `timezone`, frab `time_zone_name`, ics `TZID`/`X-WR-TIMEZONE`, Luma `timezone`). If neither exists, **fail with a warning, don't guess UTC**. Localize with `datetime.replace(tzinfo=ZoneInfo(tz))` for naive wall-clock values (DST-correct per date), then convert to UTC at confirm time as we already do. Always show the resolved zone in the draft so the organizer can catch a wrong offset before confirming.

## 7. Detection

**By URL (before fetching):**
| Pattern | Format | Action |
|---|---|---|
| host `*.sched.com` | Sched | Fetch `https://<host>/all.ics` |
| `sessionize.com/api/v2/<id>/view/<v>` | Sessionize | Fetch `…/view/All`, require `application/json` |
| `sessionize.com/<event-slug>` (public event page) | Sessionize page | No API id there. Ask the organizer for the API URL, or fall back to HTML/LLM |
| `pretalx.com/<slug>/…`, or any host where `GET /api/events/<slug>/` returns JSON with `slug`+`timezone` | pretalx | Fetch `/<slug>/schedule/export/schedule.json` |
| path ends `/schedule/export/schedule.(json|xml|ics)`, `/schedule/xml`, `/schedule.xml` | frab/pretalx | Fetch as-is |
| `luma.com/*`, `lu.ma/*` | Luma | Event metadata + description → LLM (expect no agenda) |
| `eventbrite.*`, `meetup.com` | Ticketing | HTML → LLM (expect no agenda) |
| path ends `.ics`, `webcal://` (rewrite to `https://`) | ics | ics adapter |
| anything else | unknown | Fetch, then sniff the body (below) |

An HTML page can also *point at* a structured source. After fetching, grep it for `sessionize.com/api/v2/<id>/`, `<a href="…/all.ics">`, `<link rel="alternate" type="text/calendar">`, `schedule/export/schedule.json`, and `<meta name="generator" content="pretalx">`. Follow at most one such hop.

**By body (uploads and fetched responses).** Sniff the first ~2 KB after stripping a UTF-8 BOM and leading whitespace. Don't trust `Content-Type` (FOSDEM sends `application/octet-stream`, the Sessionize embed sends `text/javascript`, and Sched HEAD lies).
| Signature | Format |
|---|---|
| starts with `BEGIN:VCALENDAR` | ics |
| `<?xml` or `<schedule` and root element `schedule` with `conference` child | frab XML |
| JSON object with `schedule.conference.days` | pretalx/frab JSON |
| JSON object with `sessions` + `speakers` + `rooms` (+ `categories`) | Sessionize All |
| JSON array whose items have `groupName` + `sessions`, or `timeSlots` | Sessionize Sessions / GridSmart |
| starts with `document.write(` | Sessionize JS embed → reject with a "use the JSON endpoint" message |
| `%PDF-` | PDF → LLM `input_file` |
| `\x89PNG`, `\xFF\xD8\xFF`, `RIFF….WEBP` | image → LLM `input_image` |
| `PK\x03\x04` + `word/document.xml` | DOCX (already accepted) → text via `python-docx` → LLM |
| `<!doctype html` / `<html` | HTML → check for structured links, else text → LLM |

`/upload-schedule` currently accepts only PDF/DOCX/PNG/JPEG/WEBP. To accept these formats, the allow-list needs `text/calendar`, `application/json`, `application/xml`/`text/xml` and `text/html`, plus sniffing for `application/octet-stream`.

## 8. Recommended parser architecture

```
source_url ──► safe_fetch (SSRF-guarded) ─┐
                                          ├─► detect(url, bytes, content_type) ─► adapter
upload ───────────────────────────────────┘
adapters (deterministic, no LLM):  ics │ sessionize_all │ frab_json │ frab_xml
LLM fallback (gpt-5.4-mini, OPENAI_SCHEDULE_MODEL):  html_text │ pdf │ docx_text │ image
      ──► normalize (tz localize, html-unescape, trim, end>start, in-range) ──► draft {talks, warnings, source_format, timezone}
```

1. **Detect**, as in §7: a URL rewrite first, then body sniffing. Record `source_format` in the draft and on the `parse_schedule` span (`schedule.source_format`).
2. **Deterministic adapters** return the exact target shape plus warnings (non-talk rows, unscheduled sessions, floating times that were localized). Each one is a pure function over bytes, unit-tested against `tests/fixtures/schedules/*`. These cover KubeCon, Sessionize and pretalx events with zero LLM cost and no hallucination risk.
3. **LLM fallback** receives *extracted content* plus a hint block: conference name, dates and IANA timezone, plus the source URL for context only. HTML goes in as text, PDF as `input_file`, images as `input_image`, DOCX as text. It uses the existing strict `json_schema` output. Chunk by day or page for large inputs. Server-side validation always runs after it.
4. **Normalize** every path the same way: localize naive times with the conference timezone, unescape HTML entities, strip tags from abstracts, dedupe on (title, start, room), and drop or flag non-talks.

### URL fetching: do it on the server, SSRF-safe; don't hand URLs to the model

The current code sends the URL to the model as plain text with no tool, so the model cannot fetch it. The docstring's claim that delegating retrieval to the model prevents SSRF is bullshit in practice, because nothing is retrieved; every URL import today is a hallucination risk. The account does have `gpt-5-search-api` and the Responses `web_search` tool, which would avoid SSRF by never fetching from our pod. **Recommendation: don't use it for import.**
- The deterministic paths need the **raw bytes** (`.ics`, JSON, XML). A web-search tool returns model-summarized page content, not the file, so we'd lose every deterministic adapter and be back to LLM extraction for KubeCon's 540-event ics.
- It is non-reproducible and truncates. Search tools excerpt pages, and a large agenda gets silently cut, with no way to tell from the draft that sessions are missing.
- Robots and bot blocking apply to OpenAI's crawler too, it can't see private or unlisted organizer links, and the cost is per call plus tokens.
- The model would still need a timezone hint, which we only have on the server.

A guarded fetcher is about 60 lines with `httpx` (already installed as an `openai` dependency):
- **Scheme and port:** `https` only on port 443 (rewrite `webcal://` to `https://`). Reject userinfo in the URL.
- **Resolve, then check:** `socket.getaddrinfo` the host. Reject *any* result that is not globally routable (`ipaddress.ip_address(a).is_global` is False, which covers RFC1918, loopback, link-local `169.254.0.0/16` including cloud metadata, CGNAT `100.64/10`, ULA `fc00::/7`, multicast and reserved). Unwrap IPv4-mapped IPv6 before the check. Also reject the cluster's pod and service CIDRs if they're public-looking.
- **Pin the IP** to defeat DNS rebinding: connect to the vetted address while TLS SNI and `Host` keep the original hostname. With httpx, give `httpx.HTTPTransport`/`AsyncHTTPTransport` a custom httpcore network backend whose `connect_tcp(host, port, …)` resolves, checks and connects to the vetted IP. httpcore still does `start_tls` with the origin hostname, so certificate verification stays correct. (Note that `local_address=` is the *source* bind address, so it does not help here.) If pinning is too much for the hackathon, at minimum re-resolve and re-check right before connecting, and accept the small race.
- **Redirects:** `follow_redirects=False`. Follow manually up to 3 hops, re-running every check on each `Location`.
- **Limits:** connect 5 s, total 20 s. Stream the body and abort past 10 MiB (same as `MAX_UPLOAD_BYTES`). No cookies, no auth headers, and an honest `User-Agent` (e.g. `WeMakeDevs2026-schedule-import/1.0`).
- **Content-type allow-list** (checked, then confirmed by sniffing): `text/calendar`, `application/json`, `application/xml`, `text/xml`, `text/html`, `application/pdf`, `image/png|jpeg|webp`, and `application/octet-stream` only if sniffing finds a known format.
- Treat fetched bytes exactly like an upload: same detection, same adapters.

### Libraries
- `icalendar` (7.x; resolves `TZID`/`VTIMEZONE` to `zoneinfo`, handles folded *and* Sched's unfolded lines, unescapes `\,`). Add it to `backend/pyproject.toml`. It has been validated against both ics fixtures.
- `defusedxml` for frab XML. Stdlib `xml.etree` is fine for trusted fixtures but not for uploads.
- stdlib `json`, `zoneinfo`, `html` (`html.unescape`), `ipaddress`, `socket`.
- `httpx` for fetching.
- HTML to text: stdlib `html.parser` is enough. Use `selectolax` or `beautifulsoup4` only if table and grid handling needs it.
- `pypdf` and `python-docx` are already dependencies.

### Rate limits and ToS by source
- **Sched:** use only `/all.ics`. `robots.txt` disallows `/api`, `/grid/*` and query URLs, and the API needs the organizer's key. Fetch once per import and never crawl `/event/*` pages.
- **Sessionize:** the public API is meant for organizers' own sites. We saw no rate-limit headers and found no documented limit, but fetch once per import, never poll, and only use endpoints the organizer has published. `robots.txt` disallows only `/app/` and `/submission/helper/`.
- **pretalx:** public schedule exports and the API are unauthenticated for public events. We saw no rate-limit headers, but treat pretalx.com as shared community infrastructure. One request per import (two if we call `/api/events/<slug>/` for the timezone).
- **FOSDEM/frab:** static files, but the 3.4 MB XML is fine once per import.
- **Luma / Eventbrite / Meetup:** their ToS restrict scraping and the pages are bot-protected. Only fetch a URL the organizer pasted, once, and expect failures. Upload is the reliable path.
- **Personal data:** speaker names, bios and avatars on public schedules are public, but don't store avatar URLs or bios beyond what the talk shape needs. Sessionize `questionAnswers` can contain organizer-private answers on some endpoints, so ignore them.
