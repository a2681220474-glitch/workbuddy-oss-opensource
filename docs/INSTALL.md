# WorkBuddy OSS Install Guide

This guide is the install entry for `v0.20.x` release-candidate preparation. It
covers local single-machine use first, then points to deployment docs for the
Docker/PostgreSQL/Redis path.

## Requirements

Minimum local tools:

- Python 3.11+
- Node.js 20+
- npm
- Git

Optional but recommended for deployment validation:

- Docker
- Docker Compose

## 1. Clone And Configure

```bash
git clone <repo-url>
cd WorkBuddy\ OSS
cp .env.example .env
```

Keep real secrets in `.env.local` rather than `.env` when working on a shared
machine. Both files are ignored by git.

## 2. Install API Dependencies

```bash
python3 -m venv .venv
. .venv/bin/activate
.venv/bin/pip install -r apps/api/requirements.txt
```

## 3. Install Web Dependencies

```bash
npm --prefix apps/web install
```

## 4. Initialize The Database

```bash
npm run db:migrate
```

The default database is SQLite at `apps/api/data/workbuddy.db`. For a new local
trial, no manual seed is required. Open the demo page and use `一键准备 Beta 验收`
when you want sample data.

## 5. Start Local Services

API:

```bash
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Web:

```bash
npm --prefix apps/web run dev -- --host 127.0.0.1 --port 5173
```

Open:

- Web console: `http://127.0.0.1:5173`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## 6. Verify The Install

```bash
npm run build:web
.venv/bin/python -m compileall apps/api
npm run db:migrate
npm run check:release
```

Expected result:

- Web build passes.
- API compile passes.
- Alembic migration is at head.
- Release readiness check reports required local docs and safety defaults.

## 7. Next Steps

- For demo data and safe public demos, read `docs/RELEASE_MODES.md`.
- For runtime environment keys, read `docs/RUNTIME_CONFIG.md`.
- For Feishu and WeCom setup, use `docs/FEISHU_SETUP.md` and
  `docs/WECOM_SETUP.md`.
- For Docker/PostgreSQL/Redis deployment validation, use `docs/DEPLOYMENT.md`
  and `docs/ops/docker_compose_acceptance.md`.
