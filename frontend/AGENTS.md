# Frontend agent instructions

Apply the [root repository instructions](../AGENTS.md) and the [frontend architecture](docs/architecture.md). Keep Expo code and its npm lockfile here. Coordinate backend and shared CI changes with their owners.

- Keep demo data synthetic and separate from UI. Keep transport and wire-format mapping outside screens. Read the [integration notes](docs/integration.md) before adding or changing an API call.
- Treat resume sharing, discovery, and connection acceptance as distinct decisions. Default resumes to private in the UI. Require server authorization for every conference-scoped read, write, and disclosure.
- Keep secrets server-side. Expo public environment values are bundled into the client. Keep resumes, profile text, contact details, credentials, and join tokens out of fixtures, client persistence, and telemetry.
- Label controls and inputs, preserve logical focus order, support keyboard and screen-reader use, and pair status colors with text. Check text scaling and avoid fixed-height text containers.
- When adding network flows, handle loading, empty, timeout, and error states. Prevent duplicate submissions, discard stale results after conference or profile changes, and use the existing OpenTelemetry approach for live requests without logging payloads.
- Before opening a small Gitar-reviewed PR, run `npm ci`, `npm run typecheck`, and `npx expo export --platform web` from this folder. Include the exercised flow and any native accessibility checks in the PR.

## Gitar review focus

Flag client-side secrets, unauthorized profile or resume disclosure, cross-conference state leaks, duplicate writes, inaccessible controls, and divergence from the agreed API contract. Verify recommendation reasons are visible as text and are safe to show to the recipient. Treat the endpoint sketch as provisional.
