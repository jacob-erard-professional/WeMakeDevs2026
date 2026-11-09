# Conference frontend

Standalone React Native and TypeScript app based on Expo's blank TypeScript template. The starter displays a sample conference with talk and people recommendations and their reasons. It runs with synthetic data and needs no backend or credentials.

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
