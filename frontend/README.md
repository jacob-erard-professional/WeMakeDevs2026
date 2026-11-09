# Conference frontend

Standalone React Native and TypeScript app for conference planning and attendee discovery. Demo data and edits stay in the running session.

Choose **Join sample conference** to try a profile, schedule, talk suggestions, and people recommendations. Refresh the People view to simulate another attendee arriving.

Choose **Organizer** to preview and publish a pasted schedule. The entry pass shows a QR code and the equivalent text code. On Android or iOS, choose **Scan QR code** at attendee check-in and allow camera access, or type the code. Web check-in accepts text. Newly published demo events resolve within the same app session. Joining them from another device requires the live backend.

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
