# Release Candidate Checklist

This checklist covers the current private release-candidate line.

## Required Local Checks

Run:

```bash
npm run build:web
.venv/bin/python -m compileall apps/api scripts
npm run db:migrate
npm run check:release
npm run check:deployment
npm run check:release-gap-audit
npm run check:formal-closure
npm run check:formal-release
npm run check:rc
git status --short
```

Expected:

- Web build passes.
- API and scripts compile.
- Alembic migrations are at head.
- Release readiness passes.
- Deployment static readiness passes; Docker warning is acceptable only on a
  machine without Docker.
- Release gap audit separates completed, manual, deployment, and observation items.
- Formal closure check verifies maintenance boundaries and the aggregate command.
- Formal release aggregate check passes.
- RC check passes.
- Working tree has no unintended tracked changes.

## Manual Product Checks

Demo mode:

1. Start API and Web.
2. Open `http://127.0.0.1:5173/#demo`.
3. Run `一键准备 Beta 验收`.
4. Confirm messages, AgentRun, business objects, approvals, reports, and
   knowledge objects are created.

Knowledge:

1. Open `#knowledge`.
2. Check list, detail, version history, graph, quality governance, import, and
   lightweight search.
3. Send/import a message that matches published knowledge.
4. Open approval detail and confirm `知识引用`.

Connectors:

1. Follow `docs/FEISHU_SETUP.md` for Feishu.
2. Follow `docs/WECOM_SETUP.md` for WeCom.
3. Keep `ENABLE_EXTERNAL_SEND=false` for the first pass.
4. Only enable real send for an owned test workspace after mock send acceptance.

Deployment:

1. Follow `docs/DEPLOYMENT.md`.
2. On a Docker host, follow `docs/ops/docker_compose_acceptance.md`.
3. Run backup create, verify, and restore-plan checks.

Security:

1. Read `SECURITY.md`.
2. Read `docs/PRIVACY_SECURITY.md`.
3. Read `docs/RELEASE_HYGIENE.md`.
4. Confirm no real secrets or private data are committed.

## Release Boundary

This RC line can claim:

- local install path
- demo mode and empty-environment path
- Feishu and WeCom setup manuals
- deployment target and static Compose readiness
- security, privacy, and release hygiene docs
- login, role-based write protection, and encrypted runtime secrets
- hybrid local RAG with citations, feedback, rollback, and quality governance
- supervised local API/Web/runtime-jobs services
- safe connector acceptance without automatic real external sending
- local formal closure boundary and aggregate release check command

This RC line must not claim:

- Docker full-stack boot on this machine
- Docker/Postgres/Redis full-stack execution unless it was run on a Docker host
- remote ECS upgrade beyond the validated `v1.1.14`
- two weeks of continuous real-team operation
- real connector send unless the operator ran the connector-specific acceptance
- maintenance mode for the full product line before real-team observation and user confirmation
