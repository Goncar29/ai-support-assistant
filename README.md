# AI Support Assistant

React + TypeScript frontend, FastAPI backend, LLM integration (Claude).

## Run

Backend (works offline without an API key, echoing the message):

    cd backend
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=...        # optional
    python -m uvicorn app.main:app --reload

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
- [ ] Day 10-11: AWS deploy
