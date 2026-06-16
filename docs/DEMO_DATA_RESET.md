# Demo Data Reset

WorkBuddy OSS has two demo data paths.

## Safe Beta Prepare

Use this for normal demos:

```bash
curl -X POST http://localhost:8000/api/demo/prepare
```

It performs a local demo refresh:

- removes local CSV demo business records
- keeps Feishu history and Feishu channel records
- imports support, sales, community and recruiting demo CSV files
- promotes pending KnowledgeGap records into KnowledgeItem records
- generates operations, support, sales, community, recruiting and knowledge gap reports
- restores conversation policies to automatic routing and inherited send mode
- returns the Beta validation report

The Web console button is:

```text
演示模式 -> 一键准备 Beta 验收
```

## Full Tenant Reset

Use this only when you want a clean tenant-level demo dataset:

```bash
curl -X POST http://localhost:8000/api/demo/reset
```

It clears tenant demo records, including channel/conversation records, then imports the demo CSV files. It is useful for local development, but it is not the recommended public demo button because it also removes Feishu demo history.

## Empty Database Cold Start

For release validation, run against a temporary SQLite database:

```bash
WORKBUDDY_DATABASE_URL=sqlite:////private/tmp/workbuddy-v012-cold.db \
  .venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8012
```

Then prepare demo data:

```bash
curl -X POST http://localhost:8012/api/demo/prepare
```

Expected result:

- validation report shows `8/8`
- messages are imported
- tickets, leads, tasks and candidates are created
- knowledge item and reports are generated
- approvals and AgentRun audit logs are present

## Public Demo Safety

Recommended public demo defaults:

```env
LLM_PROVIDER=mock
ENABLE_EXTERNAL_SEND=false
```

With these defaults, approval sending creates audit records but does not touch external IM platforms.
