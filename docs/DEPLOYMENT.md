# Deployment Guide

This guide describes the `v0.20.x` deployment target for WorkBuddy OSS. Local
SQLite remains supported for development, while release-candidate deployment
validation targets Docker Compose with PostgreSQL and Redis.

For the first `v1.0.0` private deployment target, see
`docs/PRIVATE_DEPLOYMENT.md` and `deploy/oci-free/`.

## Deployment Shape

Target services:

- `postgres`: PostgreSQL 16 data store
- `redis`: Redis runtime dependency
- `api`: FastAPI service
- `web`: Vite/React web console
- `feishu-worker`: Feishu long-connection worker
- `runtime-jobs`: background scans and scheduled reports

Declared Compose file:

```bash
docker compose config
docker compose up --build
```

If Docker is unavailable on the current machine, run static readiness instead:

```bash
npm run check:deployment
```

This confirms the required services are declared, but it is not a substitute for
a real Compose boot on a Docker host.

## Environment

Start from:

```bash
cp .env.example .env
```

For Compose, these values are supplied by `docker-compose.yml` unless overridden:

```env
DATABASE_URL=postgresql+psycopg://workbuddy:workbuddy@postgres:5432/workbuddy
REDIS_URL=redis://redis:6379/0
ENABLE_BACKGROUND_JOBS=true
BACKGROUND_QUEUE_DRIVER=database_polling
```

Keep real channel secrets in `.env.local` and never commit them.

## First Boot

```bash
docker compose up --build
```

Then open:

- Web: `http://localhost:5173`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

Expected health indicators:

- database connected
- Redis configured and connected
- logs ready
- background jobs enabled
- Feishu worker state visible

## Migration

The API service runs:

```bash
python scripts/run_migrations.py
```

For manual migration:

```bash
npm run db:migrate
```

Run migrations before enabling real traffic on a restored or upgraded database.

## Runtime Checks

```bash
curl http://localhost:8000/health
npm run check:runtime-stack
npm run check:deployment
npm run check:logs
npm run check:background-jobs
```

Connector-specific checks:

```bash
npm run check:feishu-stream
npm run check:feishu-acceptance
npm run check:wecom-runtime
npm run check:wecom-acceptance
```

Only run real connector checks after credentials are configured.

## Backup And Restore

Create and verify a backup:

```bash
npm run backup:create
npm run backup:verify -- <backup-path>
npm run backup:restore-plan -- <backup-path>
```

SQLite local restore:

```bash
npm run backup:restore:sqlite -- <backup-path> --confirm
```

PostgreSQL target restore should use PostgreSQL client tools:

```bash
pg_restore --clean --if-exists --dbname "$DATABASE_URL" <backup-path>
npm run db:migrate
```

Always stop API, workers, and scheduled jobs before restore.

For a non-destructive restore drill, keep production services online and restore
into a disposable database:

```bash
bash deploy/oci-free/postgres_restore_drill.sh \
  /absolute/path/to/backup.sql \
  workbuddy_restore_drill_$(date +%Y%m%d_%H%M%S) \
  /absolute/path/to/restore-drill-evidence.json
```

This command refuses the production database, verifies the restored schema,
messages, approvals, and Alembic version, then drops the temporary database.

## Production Notes

- Use managed PostgreSQL/Redis or durable Docker volumes.
- Put API behind HTTPS and a reverse proxy.
- Use stable public callback domains for WeCom HTTP callbacks.
- Keep Feishu long-connection worker as a supervised process.
- Rotate channel secrets if they are exposed.
- Keep `ENABLE_EXTERNAL_SEND=false` until connector acceptance passes.
