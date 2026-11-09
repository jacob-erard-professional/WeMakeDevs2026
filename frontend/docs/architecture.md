# Frontend architecture

`App.tsx` owns the organizer and attendee flow, published conferences, and the active attendee session. `src/conference.ts` holds the local models, schedule parser, and recommendation logic. `src/demoConference.ts` contains synthetic talks and attendees. `Organizer.tsx`, `ProfileForm.tsx`, and `Recommendations.tsx` own their screen state and share controls from `src/ui.tsx`.

The mock uses one conference day in Mountain Time. Talk recommendations prioritize interest matches and exclude unavailable times. The schedule greedily selects recommendations without overlaps. Switching conferences clears the active profile and connection requests. The résumé picker retains the filename in memory only. The sample conference simulates new arrivals on refresh, and newly published conferences start with an empty people list.

Schedule import currently supports pasted text. The organizer QR encodes the same plain conference code shown on the entry pass. Native camera scanning and manual entry use the same in-memory conference lookup. The scanner accepts QR data as text and never opens a scanned URL. Shared join codes across devices, join links, URL/file schedule import, live recommendations, connection acceptance, and persistence depend on the FastAPI integration.

## Extend by feature

- Keep the root responsible for app setup and navigation once multiple screens exist. Put each screen and its feature-specific components together under `src/features/` as the flow is implemented. Move components to a shared folder when they have a second consumer.
- Keep view models independent of FastAPI wire formats. Introduce a data boundary when screens need asynchronous reads or writes. Give mocks and the eventual HTTP adapter the same operations so swapping them leaves UI behavior intact.
- Keep form state local. Scope shared flow state and any future cache to the active conference and attendee. Clear scoped state on conference switches and ignore responses from requests started under the previous scope.
- Keep unavailable times and talk times as absolute instants at the API boundary. Render in the conference's IANA timezone, with America/Denver for the hackathon fixture once time is represented.
- Use the public API base URL as client configuration once integration begins. Route private operations through authenticated FastAPI endpoints. Elasticsearch and LLM access belong behind the backend boundary.
- Instrument live requests and key actions with the repo's OpenTelemetry conventions. Use operation names, durations, and status, and keep user content and identifying URL parameters out of telemetry.

For each feature, verify the normal path plus the relevant empty, failure, retry, and accessibility states. Run the web export as a bundling check and exercise native behavior on a device or emulator when available.
