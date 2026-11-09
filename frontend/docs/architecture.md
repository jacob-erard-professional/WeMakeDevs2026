# Frontend architecture

`App.tsx` owns public navigation and the active attendee session. `src/api.ts` maps FastAPI calls to frontend data. `src/conference.ts` holds shared models and the schedule fallback. Screens share controls from `src/ui.tsx`.

FastAPI ranks talks and people for the attendee's conference. **My conferences** restores saved check-ins per event. The published schedule can be browsed before completing a profile. Similar past talks, people refresh, and connection requests use the signed-in attendee's conference token.

The public catalog separates confirmed schedules in `talks` from historical talks in the read-only `talks-archive` alias. The frontend requests result pages as needed and displays loading, empty, and retry states.

The profile flow keeps one draft while moving between About you and Availability. `src/Flow.tsx` provides short content transitions and disables them when the device or browser requests reduced motion.

Organizer schedule import sends links and files to FastAPI for parsing. Structured single-day text is parsed locally and converted to the same publish payload. The entry pass encodes a public web join link. Native scanning and manual entry extract its conference ID and use the same lookup. The full-screen presentation provides native sharing or browser sharing and clipboard copy. See the [backend handoff](integration.md#backend-handoff-for-the-conference-experience) for event metadata and app-link requirements.

## Extend by feature

- Keep the root responsible for app setup and navigation once multiple screens exist. Put each screen and its feature-specific components together under `src/features/` as the flow is implemented. Move components to a shared folder when they have a second consumer.
- Keep view models independent of FastAPI wire formats. Introduce a data boundary when screens need asynchronous reads or writes. Give mocks and the eventual HTTP adapter the same operations so swapping them leaves UI behavior intact.
- Keep form state local. Scope shared flow state and any future cache to the active conference and attendee. Clear scoped state on conference switches and ignore responses from requests started under the previous scope.
- Keep unavailable times and talk times as absolute instants at the API boundary. Use the conference's IANA timezone when the API supplies it. The current frontend uses America/Denver.
- Use the public API base URL as client configuration once integration begins. Route private operations through authenticated FastAPI endpoints. Elasticsearch and LLM access belong behind the backend boundary.
- Instrument live requests and key actions with the repo's OpenTelemetry conventions. Use operation names, durations, and status, and keep user content and identifying URL parameters out of telemetry.

For each feature, verify the normal path plus the relevant empty, failure, retry, and accessibility states. Run the web export as a bundling check and exercise native behavior on a device or emulator when available.
