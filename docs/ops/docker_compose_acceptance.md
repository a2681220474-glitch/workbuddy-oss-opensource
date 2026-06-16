# Docker Compose Acceptance

This runbook verifies the WorkBuddy OSS deployment shape on a Docker-capable
machine.

## 1. Static Checks

```bash
npm run check:deployment
docker compose config
```

Required services:

- `postgres`
- `redis`
- `api`
- `web`
- `feishu-worker`
- `runtime-jobs`

## 2. Full Stack Boot

```bash
docker compose up --build
```

Wait until:

- PostgreSQL healthcheck is healthy.
- Redis healthcheck is healthy.
- API starts after migrations.
- Web serves `http://localhost:5173`.
- Runtime jobs process starts.
- Feishu worker starts or reports missing credentials clearly.

## 3. Runtime Verification

```bash
curl http://localhost:8000/health
npm run check:runtime-stack
npm run check:logs
npm run check:deployment
```

Expected:

- API health status is `ok`.
- Database backend is PostgreSQL.
- Redis is configured.
- Logs are ready.
- Background jobs are enabled or have a clear disabled reason.

## 4. Demo Workflow Verification

1. Open `http://localhost:5173/#demo`.
2. Click `一键准备 Beta 验收`.
3. Confirm messages, AgentRun, business objects, approvals, reports, and
   knowledge objects are created.
4. Keep `ENABLE_EXTERNAL_SEND=false` unless this is an owned connector test.

## 5. Backup Verification

```bash
npm run backup:create
npm run backup:verify -- <backup-path>
npm run backup:restore-plan -- <backup-path>
```

For PostgreSQL, install `pg_dump` and `pg_restore` on the host or run the
commands inside a PostgreSQL client container.

Run a restore drill against a disposable database:

```bash
bash deploy/oci-free/postgres_restore_drill.sh \
  /absolute/path/to/backup.sql \
  workbuddy_restore_drill_$(date +%Y%m%d_%H%M%S) \
  /absolute/path/to/restore-drill-evidence.json
```

The script refuses the production database and PostgreSQL system databases,
requires the `workbuddy_restore_drill_` prefix, verifies restored schema and
business record counts, and removes the temporary database on exit.

## 6. Shutdown

```bash
docker compose down
```

To remove data volumes during a destructive local test only:

```bash
docker compose down -v
```

Never run `down -v` against a real team environment.
