# Conference frontend

React Native and TypeScript app for conference planning and attendee discovery.

To try the app without FastAPI:

- Choose **I’m an attendee**, **Join sample conference**, then **Use sample profile**. Continue through availability to see a schedule, talk suggestions, and people recommendations.
- Choose **I’m an organizer** and **Try sample organizer flow**. Continue with the prefilled event and schedule, preview and publish it, then select **Try attendee check-in**. The sample event and QR are for this app session.

Choose **I am an organizer** to enter event details and import a link, image, PDF, or structured text schedule. Publishing through FastAPI creates an attendee link. Tap the QR to present it full screen and share the link from the presentation. Attendees can follow the link in a browser, type the event code, or scan it from the native app. The event schedule opens session details and can look up similar recordings after attendee check-in.

Organizer publishing and live conference links require a reachable FastAPI instance. See the [API configuration and backend handoff](docs/integration.md).

From the repository root in Command Prompt, using Node.js 24 and npm:

```cmd
cd frontend
npm ci
npm run web
```

Use `npm start` for Expo's development server and a compatible device client. This project uses Expo SDK 58. For native setup and client compatibility, see the [Expo environment guide](https://docs.expo.dev/get-started/set-up-your-environment/).

```cmd
npm run typecheck
npx expo export --platform web
```

Start with the [frontend documentation](docs/README.md) and [agent instructions](AGENTS.md).
