# AI Support Assistant

A customer-support chat powered by Claude. The agent searches an FAQ, answers in the user's language, and opens a support ticket when the FAQ has no answer. Replies stream to the browser as they are written, and tickets persist in Postgres.

**Live demo:** https://ai-support-assistant-sigma.vercel.app (API: https://ai-support-assistant-api.vercel.app/health)

> The live demo currently runs in **demo mode**: no Anthropic API key is configured, so a scripted model stands in for Claude. It still drives the real agent loop: it searches the FAQ in English or Spanish (try refunds, shipping or passwords, or "¿Cuánto tarda el envío?") and opens a real ticket in Postgres when you ask for one ("open a ticket", "talk to a human"). Streaming, tools, storage, rate limiting and the deploy are all real; only the reasoning is fixed.

The interface follows your browser language (English or Spanish, switchable from the header) and accepts voice input in browsers with the Web Speech API (Chrome, Edge, Safari); the orb reacts to what the assistant is doing and to your voice.

How it works (hexagonal layers, request flow, streaming, persistence): see [ARCHITECTURE.md](ARCHITECTURE.md).

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript (Vite), Vitest + Testing Library |
| Backend | FastAPI, Server-Sent Events, hexagonal architecture (ports and adapters) |
| LLM | Claude Haiku 5.5, OpenAI or Gemini, behind a provider-neutral port (`LLM_PROVIDER`) |
| Database | Postgres on Neon (psycopg 3); in-memory fallback |
| Automation | n8n webhook on new tickets (optional) |
| Hosting | Vercel (frontend + FastAPI function), Neon free plan |
| CI | GitHub Actions: backend tests (including Postgres integration against a `postgres:17` service), frontend lint + tests + build |

## Run locally

Requirements: Python 3.14 (pinned in `backend/.python-version`) and Node 22+.

**Backend** (works with no configuration: demo mode, in-memory tickets):

    cd backend
    py -3.14 -m venv .venv && .venv\Scripts\activate
    pip install -r requirements-dev.txt   # runtime deps + pytest; Vercel installs only requirements.txt
    python -m app.migrate                 # once, only when DATABASE_URL is set: creates the tickets and rate_limits tables
    python -m uvicorn app.main:app --reload --env-file .env

Put secrets in `backend/.env` (git-ignored), one `NAME=value` per line; real environment variables take precedence.

**Frontend:**

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173.

## Configuration

Backend (all optional):

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | `anthropic`, `openai`, `gemini` or `demo`; the app refuses to start if the chosen provider's key is missing | unset (Claude if `ANTHROPIC_API_KEY` is set, else demo mode) |
| `ANTHROPIC_API_KEY` | Enables the Claude agent; without it a scripted demo model drives the tools | unset (demo mode) |
| `ANTHROPIC_MODEL` | Claude model id | `claude-haiku-5-5` |
| `ANTHROPIC_EFFORT` | Reasoning effort (`low`, `medium`, `high`, `xhigh`, `max`); lower is faster | `low` |
| `OPENAI_API_KEY` | OpenAI key, used with `LLM_PROVIDER=openai` | unset |
| `OPENAI_MODEL` | OpenAI model id | `gpt-6-luna` |
| `GEMINI_API_KEY` | Gemini key, used with `LLM_PROVIDER=gemini` | unset |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.5-flash-lite` |
| `DATABASE_URL` | Postgres connection string (use Neon's pooled `-pooler` host); without it tickets live in memory and are lost on restart | unset (in-memory) |
| `N8N_WEBHOOK_URL` | Webhook notified when a ticket is created | unset (no notification) |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API | `http://localhost:5173` |
| `RATE_LIMIT_REQUESTS` | Chat requests each client (IP) may make per window, across `/chat` and `/chat/stream`; counted in Postgres when `DATABASE_URL` is set, otherwise in memory per process | `10` |
| `GLOBAL_RATE_LIMIT_REQUESTS` | Chat requests all clients together may make per window; caps total model spend even when many IPs are used. Checked after the per-client limit, so requests that limit denies do not count | `100` |
| `RATE_LIMIT_WINDOW_SECONDS` | Length of the rate-limit window | `60` |

Frontend:

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_URL` | Backend base URL, baked into the build | `http://localhost:8000` |

## Deploy

Two Vercel projects (Hobby plan) linked to this repository, plus a Neon Postgres database in AWS us-east-1:

| Vercel project | Root directory | Framework | Environment variables |
|---|---|---|---|
| `ai-support-assistant-api` | `backend/` | FastAPI, functions in `iad1` (next to Neon) | `CORS_ORIGINS` = frontend URL; `DATABASE_URL` and the provider's API key as **Sensitive** |
| `ai-support-assistant` | `frontend/` | Vite | `VITE_API_URL` = API URL |

Steps for a fresh setup:

1. Create a Neon project, copy its pooled connection string, and run `python -m app.migrate` once with it in `backend/.env`.
2. Create both Vercel projects from this repository with the root directories above.
3. Set the environment variables (secrets only in the Vercel dashboard, never in the repo).
4. Push: every push to the repository deploys both projects.

Vercel reads the Python version from `backend/.python-version` and installs only `backend/requirements.txt`.

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check: `{"status": "ok"}` |
| `POST /chat` | `{"message": "...", "history": [{"role": "user" \| "assistant", "content": "..."}]}` → `{"reply": "..."}` once the agent finishes. `history` is optional: the earlier conversation, oldest first, at most 20 messages of up to 4000 characters each |
| `POST /chat/stream` | Same input, answered as Server-Sent Events: `delta` (`{"text"}` chunks as they are generated), `tool` (`{"name"}` when the agent runs a tool), then `done` (`{"reply"}`, the authoritative final answer) or `error` (`{"code", "message"}`; `code` is `model_unavailable` when the AI provider is busy, `server_error` otherwise) |

The frontend uses `/chat/stream`, so text appears while the model is still writing.

Both chat endpoints are rate limited per client IP (per /64 network for IPv6, so rotating addresses inside one allocation does not reset the budget). Over the limit they answer `429` with `{"detail": "Too many requests. Please try again later."}` and a `Retry-After` header (seconds). When the AI provider is busy even after two retries, `/chat` answers `503` with `{"detail": "The assistant is busy right now. Please try again in a moment."}`. On Vercel the client IP comes from `X-Forwarded-For`, which Vercel overwrites; elsewhere it comes from the connection, so a client cannot dodge the limit by sending its own header.

## Tests

| Command | Covers |
|---|---|
| `cd backend && python -m pytest` | Agent loop with fake LLMs, tools, SSE, settings, adapters, migrations |
| same, with `TEST_DATABASE_URL` set | Postgres integration tests, each in a throwaway schema |
| `cd frontend && npm test` | SSE client and the `useChat` hook (Vitest + Testing Library) |

## Roadmap

- [x] FastAPI + chat endpoint + LLM integration (tests)
- [x] React chat UI
- [x] Agent with tool use (`search_faq`, `create_ticket`)
- [x] n8n webhook flow (set `N8N_WEBHOOK_URL`; import `n8n/ticket-notification.json`)
- [x] GitHub Actions CI (backend tests with a Postgres service, frontend lint + tests + build)
- [x] Hexagonal architecture with a provider-neutral LLM port
- [x] Claude Haiku 5.5 + SDK upgrade
- [x] Streaming replies (SSE)
- [x] Postgres persistence (Neon)
- [x] Free deploy on Vercel
- [x] Per-IP rate limit on the chat endpoints
- [ ] Live Claude in the demo (needs API credits)
- [ ] A second LLM provider behind the same port
