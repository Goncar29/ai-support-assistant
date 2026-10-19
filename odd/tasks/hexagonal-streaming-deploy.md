# Hexagonal architecture, streaming and free deploy

Objective: restructure the backend into a hexagonal architecture with a provider-neutral LLM port, add streaming and Postgres persistence, and deploy for free on Vercel + Neon.
Branch: `feat/hexagonal-architecture` · Delivery strategy: ask-on-risk · Test runner: `cd backend && python -m pytest -q`; frontend `npm run build`.

## Specs

- **S1 — Clean architecture.** "tratemos de hacer esto en una clean artquitecture". The domain and application layers must not import FastAPI, Anthropic, n8n or env vars. Adapters plug into ports in a single composition root. Existing behavior must be kept: `/health`, `/chat`, offline echo without an API key, FAQ search, ticket creation, and the best-effort n8n notification.
- **S2 — Multi-provider LLM port.** "podriamos hacer que esto sirba para integrar otras IA, si ya usamos una arquitectura limpia podemos hacer algo para varias IA". The agent loop depends on a neutral `LLMProvider` port with its own message, tool call and tool result types. First version ships only the Anthropic adapter plus test fakes; a second provider comes later ("bien vamos por como lo recomiendas").
- **S3 — Newest model.** "si bien el defecto de claude es haiku 4.5, este en poco tiempo sera quitado asique tendremos que usar el modelo mas nuevo 5.5". Default model `claude-haiku-5-5`, configurable by env var; upgrade the Anthropic SDK. Requires Python >= 3.10 locally (assumption: SDK 1.x needs it).
- **S4 — Fast and good quality.** "busco que sea eficiente, escalable", "me interesa que sea todo rapido, funcional, que sea algo de buena calidad". Stream the reply to the frontend (SSE) so text appears as it is generated.
- **S5 — Persistence.** Tickets must survive restarts and serverless instances: Postgres adapter (Neon) behind the ticket repository port; in-memory adapter stays for tests/local.
- **S6 — Free deploy.** "seguimos con Render + Vercel", later refined to frontend + FastAPI on Vercel, Neon for Postgres. Validate FastAPI + streaming on Vercel first. Deploy requires the user's accounts.
- **S7 — Docs.** README explains the architecture, flows and how to run/deploy; the user wants to learn ("ayudame a ir entendiendo de que va el proyecto, flujos, etc quiero ir aprendiendo sobre todo").

## Tasks

| ID | Specs | Route | Status | Evidence |
|----|-------|-------|--------|----------|
| T1 | S1, S2 | inline | in progress | — |
| T2 | S3 | inline | blocked: needs Python 3.12 locally | — |
| T3 | S4 | inline | pending | — |
| T4 | S5 | inline | pending: needs Neon `DATABASE_URL` | — |
| T5 | S6 | inline | pending: needs Vercel account | — |
| T6 | S7 | inline | pending | — |

Route evidence: no Writer trigger (tasks depend on each other in sequence, not parallel units); all inline.

## Log

- L1 (2026-10-19, user's original request): "dale, commiteá y seguimos con Render + Vercel, tratemos de hacer esto en una clean artquitecture, ayudame a ir entendiendo de que va el proyecto, flujos, etc quiero ir aprendiendo sobre todo"
- L2 (2026-10-19): "el backend escrito hoy no es el problema, busco que sea eficiente, escalable, si bien esto si sera como portfolio, me interesa que sea todo rapido, funcional, que sea algo de buena calidad y que si alguien lo ve pueda decir que sea excelente aun usando herramientas gratuitas, sobre claude con tool te actualizo un poco, si bien el defecto de claude es haiku 4.5, este en poco tiempo sera quitado asique tendremos que usar el modelo mas nuevo 5.5 asique si hay que actualizar como dices, sobre SSR que dices vamos por esa o que opcion crees si esto lo hacemos bien?" → Decision: no SSR; host the frontend and FastAPI on Vercel, Neon for Postgres, Haiku 5.5, SSE streaming.
- L3 (2026-10-19): "perfecto, otra cosa, aqui hablamos solo de claude, pero podriamos hacer que esto sirba para integrar otras IA, si ya usamos una arquitectura limpia podemos hacer algo para varias IA" → Decision: neutral LLM port; Anthropic adapter first.
- L4 (2026-10-19): "bien vamos por como lo recomiendas" → second provider deferred until after deploy.
- L5: local Python is 3.9.13; pip only offers anthropic <= 0.125.0 there. T2 waits for Python 3.12 (CI already uses 3.12). T1 code stays 3.9-compatible.
