# WorkBuddy OSS API

Phase 0 local FastAPI service for WorkBuddy OSS. It uses SQLite and SQLModel, creates tables on startup, and keeps all external IM adapters as local placeholders.

## Run

```bash
cd /home/you/Desktop/WorkBuddy\ OSS
python -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload --port 8000
```

Health check: `http://localhost:8000/health`

## Main APIs

- `POST /api/imports/csv`
- `POST /api/imports/json`
- `GET /api/messages`
- `GET /api/tickets`
- `GET /api/leads`
- `GET /api/approvals`
- `PATCH /api/approvals/{approval_id}`
- `GET /api/agent-runs`
- `GET /api/dashboard/summary`

The import flow normalizes chat rows to `MessageEvent` records and then calls Agent B's `apps.api.modules.routing.orchestrator.handle_message_event(session, message)` if present. Until Agent B is wired, a narrow Phase 0 rule fallback creates support tickets, sales leads, `AgentRun` audit rows, and pending approvals.
