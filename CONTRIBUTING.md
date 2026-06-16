# Contributing

Thanks for helping build WorkBuddy OSS.

The current Alpha focuses on a local-first open-source workflow:

- FastAPI backend with SQLite and SQLModel.
- React + Vite + Ant Design admin UI.
- CSV / JSON chat import plus Feishu adapter safeguards.
- Rule-first Agent Router.
- Four scenario Agents: support, sales, community and recruiting.
- Structured actions, business objects, approval queue, reports and AgentRun audit logs.

Please keep changes small, documented, and easy to run locally.

## Local Checks

Run these before opening a pull request:

```bash
.venv/bin/python -m compileall apps/api
npm run build:web
```

For UI or adapter changes, also verify the relevant page under `http://localhost:5173`.

## Contribution Areas

- New scenario rules or Agent actions: start with `docs/AGENT_GUIDE.md`.
- New channel adapters: start with `docs/ADAPTER_GUIDE.md` and `docs/ADAPTER_DEV_CHECKLIST.md`.
- Business object UI changes: keep list pages compact and link back to source messages and AgentRun logs.
- Real external sends: preserve approval-first behavior and idempotency.
