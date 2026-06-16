# Quickstart

This guide gets a local WorkBuddy OSS Beta demo running and verified.

For repeatable demo reset behavior, see `docs/DEMO_DATA_RESET.md`.

## 1. Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web console: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Runtime health: `http://localhost:8000/health`

Manual start is documented in `docs/LOCAL_DEMO.md`.

Current `v0.18.x` note:

- `docker compose up --build` now targets a fuller runtime stack and is the preferred way to validate deployment shape.
- Local single-process mode can still use SQLite.

## 2. Prepare Demo Data

Open `http://localhost:5173/#demo` and click `一键准备 Beta 验收`.

Expected result:

- Beta validation report: `8/8`
- Messages: imported
- Tickets, leads, community tasks and candidates: created
- Knowledge item and reports: generated
- Approvals and AgentRun audit logs: present

## 3. Inspect The Product

Follow this path:

1. `#dashboard`: four-Agent overview and risk aggregation.
2. `#messages`: normalized messages, route result and related objects.
3. `#objects`: Ticket, Lead, Task, Candidate, Knowledge and Report counts.
4. `#tickets`: support workflow, SLA and knowledge loop.
5. `#leads`: sales funnel, scorecard and approval draft.
6. `#community`: community risks, high-intent users and tasks.
7. `#candidates`: match analysis, interview questions and onboarding checklist.
8. `#approvals`: filter by status, Agent and business object.
9. `#agent-runs`: trace prompt, output and structured actions.

## 4. Safety Defaults

- `LLM_PROVIDER=mock` is the default.
- `ENABLE_EXTERNAL_SEND=false` means external sends are simulated.
- Feishu history is preserved when using demo prepare.
- WeCom and DingTalk are mock adapter boundaries only.

## 5. First Troubleshooting

- API health: `curl http://localhost:8000/health`
- Runtime stack: `npm run check:runtime-stack`
- Migrate schema: `npm run db:migrate`
- Background jobs: `npm run check:background-jobs`
- Web URL: `http://localhost:5173`
- Rebuild frontend: `npm run build:web`
- Compile backend: `.venv/bin/python -m compileall apps/api`
