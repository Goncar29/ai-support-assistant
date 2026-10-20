# AI Support Assistant

React + TypeScript frontend, FastAPI backend, LLM integration (Claude).

## Run

Backend (Python 3.14, pinned in `.python-version`; works offline without an API key, echoing the message):

    cd backend
    py -3.14 -m venv .venv && .venv\Scripts\activate
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=...        # optional
    python -m uvicorn app.main:app --reload

Backend environment variables (all optional):

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Enables the Claude agent; without it the API echoes messages | unset (offline mode) |
| `ANTHROPIC_MODEL` | Claude model id | `claude-haiku-5-5` |
| `ANTHROPIC_EFFORT` | Reasoning effort (`low`, `medium`, `high`, `xhigh`, `max`); lower is faster | `low` |
| `N8N_WEBHOOK_URL` | Webhook notified when a ticket is created | unset (no notification) |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API | `http://localhost:5173` |

## Architecture

The backend follows a hexagonal (ports and adapters) layout. Dependencies point inward: `domain` and `application` never import FastAPI, the Anthropic SDK or environment variables.

    backend/app/
    ├── domain/          Ticket entity
    ├── application/     support agent loop, tools, ports, provider-neutral conversation types
    ├── infrastructure/  adapters: Anthropic + offline echo LLMs, in-memory repositories, n8n notifier
    ├── api/             FastAPI routes and request/response schemas
    ├── config.py        settings read from the environment
    └── main.py          composition root: wires adapters into ports

Frontend:

    cd frontend
    npm install
    npm run dev

Tests: `cd backend && python -m pytest`

## Roadmap
- [x] Day 1-4: FastAPI + chat endpoint + LLM integration (tests)
- [x] Day 7-8: React chat UI (basic)
- [x] Day 5-6: agent with tool use (search_faq, create_ticket)
- [x] Day 9: n8n webhook flow (set `N8N_WEBHOOK_URL`; import `n8n/ticket-notification.json`)
- [x] GitHub Actions CI (backend tests, frontend build)
- [x] Hexagonal architecture with a provider-neutral LLM port
- [x] Claude Haiku 5.5 + SDK upgrade
- [ ] Streaming replies (SSE)
- [ ] Postgres persistence (Neon)
- [ ] Free deploy on Vercel
