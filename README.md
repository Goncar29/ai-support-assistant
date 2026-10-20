# AI Support Assistant

React + TypeScript frontend, FastAPI backend, LLM integration (Claude).

How it works (hexagonal layers, request flow, streaming, persistence): see [ARCHITECTURE.md](ARCHITECTURE.md).

## Run

Backend (Python 3.14, pinned in `backend/.python-version`; works offline without an API key, echoing the message):

    cd backend
    py -3.14 -m venv .venv && .venv\Scripts\activate
    pip install -r requirements-dev.txt   # runtime deps + pytest; Vercel installs only requirements.txt
    python -m app.migrate            # once, only when DATABASE_URL is set: creates the tickets table
    python -m uvicorn app.main:app --reload --env-file .env

Put secrets in `backend/.env` (git-ignored), one `NAME=value` per line; real environment variables take precedence.

Backend environment variables (all optional):

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Enables the Claude agent; without it the API echoes messages | unset (offline mode) |
| `ANTHROPIC_MODEL` | Claude model id | `claude-haiku-5-5` |
| `ANTHROPIC_EFFORT` | Reasoning effort (`low`, `medium`, `high`, `xhigh`, `max`); lower is faster | `low` |
| `N8N_WEBHOOK_URL` | Webhook notified when a ticket is created | unset (no notification) |
| `DATABASE_URL` | Postgres connection string (use Neon's pooled `-pooler` host); without it tickets live in memory and are lost on restart | unset (in-memory) |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API | `http://localhost:5173` |

Frontend:

    cd frontend
    npm install
    npm run dev

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check: `{"status": "ok"}` |
| `POST /chat` | `{"message": "..."}` → `{"reply": "..."}` once the agent finishes |
| `POST /chat/stream` | Same input, answered as Server-Sent Events: `delta` (`{"text"}` chunks as they are generated), `tool` (`{"name"}` when the agent runs a tool), then `done` (`{"reply"}`, the authoritative final answer) or `error` (`{"message"}`) |

The frontend uses `/chat/stream`, so text appears while the model is still writing.

Tests: `cd backend && python -m pytest` (backend; Postgres integration tests run only when `TEST_DATABASE_URL` is set, each in a throwaway schema) and `cd frontend && npm test` (frontend, Vitest + Testing Library)

## Roadmap
- [x] Day 1-4: FastAPI + chat endpoint + LLM integration (tests)
- [x] Day 7-8: React chat UI (basic)
- [x] Day 5-6: agent with tool use (search_faq, create_ticket)
- [x] Day 9: n8n webhook flow (set `N8N_WEBHOOK_URL`; import `n8n/ticket-notification.json`)
- [x] GitHub Actions CI (backend tests, frontend build)
- [x] Hexagonal architecture with a provider-neutral LLM port
- [x] Claude Haiku 5.5 + SDK upgrade
- [x] Streaming replies (SSE)
- [x] Postgres persistence (Neon)
- [ ] Free deploy on Vercel
