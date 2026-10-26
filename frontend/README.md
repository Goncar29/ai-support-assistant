# AI Support Assistant: frontend

React + TypeScript (Vite) chat UI for the support assistant. Setup, configuration and deploy are in the [root README](../README.md); the request flow is in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on http://localhost:5173 |
| `npm test` | Vitest + Testing Library |
| `npm run lint` | Oxlint |
| `npm run build` | Type check and production build |

Set `VITE_API_URL` to point at a backend other than `http://localhost:8000`.

## Layout

| Path | Contents |
|---|---|
| `src/api/` | SSE client for `/chat/stream` |
| `src/hooks/useChat.ts` | Chat state: sends the message plus recent history, streams the reply |
| `src/hooks/conversationStorage.ts` | Saves and restores the conversation in `localStorage` |
| `src/hooks/useSpeechInput.ts` | Voice input through the Web Speech API |
| `src/components/` | Header, message list, composer, mic button, orb |
| `src/i18n/` | English and Spanish strings |
