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
| T1 | S1, S2 | inline | done | `a4606d6`; RED (5 import errors) → GREEN 18 passed |
| T2 | S3 | inline | done | `87afebb`, `8db2a69`; RED → GREEN 21 passed; verifier PASS; native review approved |
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
- L6 (2026-10-19): T1 done in `a4606d6`. Checks: pytest 18 passed; the grep found no FastAPI/Anthropic/os/infrastructure imports in domain/application; a differential probe against `2c5fb53` (/health, /chat echo, 422 empty, 422 missing, CORS preflight) was identical. RDD assess: medium, review_due=false (under_budget), untracked .atl/ excluded. Risk: none. Next: T2 needs Python 3.12 installed locally.
- L7 (2026-10-19): Python 3.15.0 was released on 2026-10-09 (the user flagged it), but Vercel documents only 3.12/3.13/3.14 and winget lacks 3.15, so the user installed 3.14.7. T2 committed in `87afebb`: claude-haiku-5-5, effort low (ANTHROPIC_EFFORT), max_tokens 16000, anthropic 1.15.0, `.python-version` 3.14 read by CI. Real API smoke test pending: no ANTHROPIC_API_KEY in this environment. Risk: item 5 (dependencies + CI). The escalated RDD assess returned high and review_due. An independent verifier was launched before the native review.
- L8 (2026-10-19): Independent verifier gave S3 PASS. Clean 3.14 install: 19 passed. The differential matched bodies and status codes; the CORS headers differ only through the Starlette upgrade (vary, QUERY), judged an advisory, not a blocker. The SDK accepts output_config, and setup-python resolves python-version-file from the repo root. Follow-ups in `8db2a69`: ANTHROPIC_EFFORT is validated at startup, and a test pins the max_tokens=16000 default. `e78f23d` ignores .atl/ and *.stackdump. Native review lineage review-582f6e8c9ee1ca53 (lenses risk + reliability, base 1114817..e78f23d): user granted consent, approved, acknowledged (authority burned). Reviewed boundary is now e78f23d. The slice 2c5fb53..1114817 (T1) is still under_budget. Pending: live API smoke test needs ANTHROPIC_API_KEY.
