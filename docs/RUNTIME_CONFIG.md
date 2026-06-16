# Runtime Configuration

`v0.18.1` keeps moving WorkBuddy OSS from a demo-only skeleton toward a configurable local runtime and a more formal deployment stack.

## Configuration Source

Runtime secrets are read from process environment variables or these local files:

- `.env`
- `.env.local`
- `apps/api/.env`
- `apps/api/.env.local`

Later files override earlier files when the process starts. They provide deployment defaults and bootstrap configuration.

These files and directories are ignored by git:

- `.env`
- `.env.local`
- `apps/api/.env`
- `apps/api/.env.local`
- `*.db`
- `apps/api/data/`
- `apps/web/.env.local`

Do not commit real API keys or channel secrets.

## Configure In The Web Console

Open:

```text
http://localhost:5173/#config
```

The Config Center provides forms for:

- LLM provider, base URL, API key, model and timeout
- real IM adapter switch and external send switch
- Feishu App ID, App Secret, Verification Token and Encrypt Key
- WeCom Corp ID, Agent ID, Secret, Token and EncodingAESKey
- DingTalk Client ID, Client Secret, Robot Code and Webhook Secret

The page now also surfaces runtime-stack status for:

- current database backend and connection health
- Redis configuration and connectivity
- background-job enablement and scheduled job types
- recommended Docker Compose and local start commands

Saving from the page writes non-secret values to `apps/api/data/runtime.env` and reloads the API settings cache immediately. UI-managed runtime values override deployment defaults so saved switches and channel IDs do not snap back after refresh.

Secret values are encrypted in `apps/api/data/runtime_secrets.json`; they are never written to `runtime.env` or returned to the browser. If a secret field already has a value, leaving the input empty keeps the existing value.

In Docker deployments, `apps/api/data/` must be mounted as a shared persistent volume for the API and workers. This keeps runtime settings, encrypted secrets, the master key, and worker status available across container recreation.

The Feishu stream worker is a separate process. After changing Feishu App ID / Secret, restart the worker so it can use the new credentials.

## LLM Runtime

Default mode:

```env
LLM_PROVIDER=mock
LLM_MODEL=workbuddy-demo
```

OpenAI-compatible mode:

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=30
```

The same contract can be used for OpenAI, DeepSeek, Qwen, Moonshot and other OpenAI-compatible providers:

- `LLM_PROVIDER=openai_compatible`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

The current runtime uses rules first. If no strong rule matches, the Router can call the configured LLM provider for intent classification. Scenario Agents still produce deterministic structured actions so the local workflow remains stable.

## Feishu

Local testing can use a real Feishu test app/account.

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_API_BASE_URL=https://open.feishu.cn
FEISHU_STREAM_STATUS_PATH=apps/api/data/feishu_stream_status.json
```

Run stream worker:

```bash
npm run dev:feishu-stream
```

When you intentionally want real sends in the test app:

```env
ENABLE_EXTERNAL_SEND=true
```

External replies still pass through the approval queue before send.

## Deployment Runtime

Environment keys:

```env
DATABASE_URL=sqlite:///./apps/api/data/workbuddy.db
REDIS_URL=
ENABLE_BACKGROUND_JOBS=false
BACKGROUND_QUEUE_DRIVER=redis
```

Recommended checks:

```bash
curl http://localhost:8000/health
npm run check:runtime-stack
npm run db:migrate
npm run check:background-jobs
```

Docker Compose target stack for `v0.18.x`:

- `api`
- `web`
- `feishu-worker`
- `postgres`
- `redis`

Current behavior:

- local single-process mode still works with SQLite
- Docker Compose is now aligned toward PostgreSQL + Redis validation
- if `BACKGROUND_QUEUE_DRIVER=redis`, Redis must be reachable for the runtime stack to be considered ready
- `BACKGROUND_QUEUE_DRIVER=database_polling` can run the first background worker without Redis
- `v0.18.2` adds Alembic baseline and a first `runtime-jobs` worker
- the first runtime-jobs worker currently handles failed delivery retry scan and overdue object scan

## WeCom

Configuration keys:

```env
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
```

Local webhook entry:

```text
GET  /api/channels/wecom/webhook
POST /api/channels/wecom/webhook
```

Current state:

- configuration status is visible in Config Center
- payloads can be normalized through Adapter Test Console
- URL verification, callback signature verification and encrypted callback decrypt are implemented
- XML and JSON payloads can enter MessageEvent -> Agent Router -> business object flow
- approval send preview can resolve WeCom delivery targets
- approved drafts can send WeCom text to a user or ChatId group when real credentials are configured
- diagnostics page: `http://localhost:5173/#wecom`
- acceptance script: `npm run check:wecom-acceptance`

## DingTalk

Configuration keys:

```env
DINGTALK_CLIENT_ID=
DINGTALK_CLIENT_SECRET=
DINGTALK_ROBOT_CODE=
DINGTALK_WEBHOOK_SECRET=
```

Local webhook entry:

```text
POST /api/channels/dingtalk/webhook
```

Current state:

- configuration status is visible in Config Center
- payloads can be normalized through Adapter Test Console
- webhook payloads can enter MessageEvent -> Agent Router -> business object flow
- platform signature verification, encrypted callback support and real send need test-account integration

## Config Center

The Web Config Center intentionally does not display secrets. It only shows:

- provider/channel configured or missing
- required key names
- webhook paths
- effective send mode
- worker status
- recent Feishu activity
