# Feishu Phase 1 Skeleton

This document describes the v0.2 Feishu integration skeleton. It supports both HTTP webhook callbacks and Feishu long-connection stream events. Real outbound sending remains disabled by default and the Phase 0 CSV / JSON demo flow is unchanged.

## Scope

Implemented in v0.2:

- Feishu webhook status endpoint.
- Feishu URL verification response.
- Plain `im.message.receive_v1` callback parsing.
- Long-connection stream worker for local development.
- Conversion from Feishu message payloads to the existing `ImportRecord` input.
- Reuse of the existing `MessageEvent -> Agent Router -> Action Engine -> Approval` pipeline.
- Channel event logging for bot added, bot deleted and p2p chat entered events.
- Placeholder `FeishuClient` for `tenant_access_token` and text send.
- Approval delivery flow: approved drafts can be sent back to Feishu, with mock mode as the default.
- User and conversation display enrichment with local cache and graceful fallback.
- Feishu connection status card data for demos.
- Feishu diagnostics page with worker status, token check, recent events, recent sends and send test actions.

Not implemented yet:

- Encrypted callback decryption.
- Feishu approval cards.
- Group binding UI.

## Integration Modes

### A. HTTP Webhook

HTTP webhook mode is kept as a fallback and for later server deployments. It requires a public callback URL.

## Local Callback URL

When running locally:

```text
http://localhost:8000/api/channels/feishu/webhook
```

For a real Feishu developer app, expose this URL through a tunnel such as cloudflared or ngrok.

Status check:

```bash
curl http://localhost:8000/api/channels/feishu/status
```

### B. Long-Connection Stream

Long-connection stream mode is recommended for local development because it does not require a public callback URL.

In the Feishu developer console:

1. Open the app event subscription page.
2. Select `使用长连接接收事件`.
3. Subscribe to these events:
   - `im.message.receive_v1`
   - `im.chat.member.bot.added_v1`
   - `im.chat.member.bot.deleted_v1`
   - `im.chat.access_event.bot_p2p_chat_entered_v1`
4. If event encryption is enabled in Feishu, save the matching Encrypt Key in
   WorkBuddy Config Center before starting the worker.

Start the API in one terminal:

```bash
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Start the stream worker in another terminal:

```bash
ENABLE_REAL_IM_ADAPTERS=true .venv/bin/python -m apps.api.workers.feishu_stream
```

Or use the root npm helper:

```bash
npm run dev:feishu-stream
```

The worker reads `FEISHU_APP_ID` and `FEISHU_APP_SECRET` from `.env` or environment variables. When Feishu shows `验证连接状态` as successful, private messages sent to the bot should create `MessageEvent`, `AgentRun`, business objects and `Approval` rows locally.

If `GET /api/channels/feishu/status` shows `"configured": false` while `"stream_worker": {"running": true}`, the API process itself does not have Feishu credentials, but the stream worker is online. For long-connection validation, `stream_worker.running` is the important field.

Important: Feishu console connection validation only succeeds while this worker process is online. If you stop the worker, or if validation happens during the SDK reconnect window, the console may show `连接失败`. Restart the worker, wait for a `connected to wss://msg-frontier.feishu.cn` log line, and click `重新验证`.

Local stream status:

```bash
curl http://localhost:8000/api/channels/feishu/stream-status
```

The regular status endpoint also includes the latest stream worker status:

```bash
curl http://localhost:8000/api/channels/feishu/status
```

Configuration-only check:

```bash
ENABLE_REAL_IM_ADAPTERS=true .venv/bin/python -m apps.api.workers.feishu_stream --check
```

## Environment

Add these values to `.env.local` or `.env` when you begin real Feishu testing. Both the API and Feishu stream worker read the same settings source, so Config Center and Worker checks should agree after restart:

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_API_BASE_URL=https://open.feishu.cn
FEISHU_STREAM_STATUS_PATH=apps/api/data/feishu_stream_status.json
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
```

Keep `ENABLE_EXTERNAL_SEND=false` for Phase 0.2 local verification. AI replies still enter the human approval queue. Do not commit `.env`.

## Approval Delivery

All AI replies still enter the approval queue first. After an approval is `approved` or `edited`, click send in the approval queue.

Default behavior:

- `ENABLE_EXTERNAL_SEND=false`
- WorkBuddy records a `sent` approval status.
- WorkBuddy writes a `feishu_send_adapter` `AgentRun`.
- No external Feishu message is sent.

Real send behavior:

- Set `ENABLE_EXTERNAL_SEND=true` in `.env`.
- Ensure the API process has `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
- Restart the API process.
- Approved Feishu-sourced replies call `FeishuClient.send_text_to_chat`.
- WorkBuddy records Feishu's returned `message_id`, source `chat_id`, and request UUID in the `feishu_send_adapter` audit run.
- Re-sending an already sent approval is blocked to avoid duplicate customer replies.

Non-Feishu source messages are still recorded as mock delivery in Phase 0.2.x.

Delivery diagnostics:

```bash
curl "http://localhost:8000/api/channels/feishu/diagnostics"
curl "http://localhost:8000/api/channels/feishu/diagnostics?check_token=true"
curl "http://localhost:8000/api/channels/feishu/diagnostics/full?check_token=true"
```

The token check never returns the raw token. If Feishu returns an error code, WorkBuddy keeps the code, message and a short repair suggestion in the failed delivery audit run.

v0.3.2 adds a dedicated diagnostics page in the web console:

```text
http://localhost:5173
左侧菜单 -> 飞书诊断
```

The page shows:

- Stream worker online/offline state and latest heartbeat.
- Current send mode: mock or real.
- Token check result without exposing the raw token.
- Latest Feishu channel event, message and send record.
- Recent `channel_events` rows for Feishu.
- Recent Feishu-related `AgentRun` rows.
- Safe mock send test, which records an audit run but never sends to Feishu.
- Real send test, available only when `ENABLE_EXTERNAL_SEND=true`, requiring an explicit confirmation payload.
- Business trace links from the latest Feishu message to Message Events, Agent Runs, Leads, Tickets, Follow-up Tasks, Approvals and send audit rows.
- Feishu conversation management with per-conversation agent binding and send policy.

Safe mock send API:

```bash
curl -X POST http://localhost:8000/api/channels/feishu/mock-send \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"diagnostics-mock-chat","text":"WorkBuddy OSS mock send"}'
```

Real diagnostics send API:

```bash
curl -X POST http://localhost:8000/api/channels/feishu/test-send \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"oc_xxx","text":"WorkBuddy OSS diagnostics test","confirm_real_send":true}'
```

The real test endpoint is intentionally separate from `mock-send` so demos cannot accidentally send messages while checking UI state.

v0.3.3 adds lightweight hash navigation without React Router:

```text
#messages?id=19
#approvals?id=14
#leads?id=11
#tickets?id=3
#tasks?id=11
#agent-runs?id=36
```

When opened from the Feishu diagnostics page, the target list page highlights the corresponding row. This makes the demo path explicit:

```text
Feishu message -> MessageEvent -> AgentRun -> Lead/Ticket/Task -> Approval -> Feishu send audit
```

v0.3.4 adds conversation policy management. v0.4.1 upgrades this page to channel-neutral conversation management:

```text
http://localhost:5173/#conversations
```

Each Feishu conversation can be configured with:

- Agent binding:
  - `auto`: keep using the Agent Router.
  - `support_ticket_agent`: always create support-ticket style output for new messages.
  - `sales_lead_agent`: always create sales-lead style output for new messages.
- Send policy:
  - `inherit`: follow Config Center default send mode; `ENABLE_EXTERNAL_SEND` remains the real-send kill switch.
  - `mock`: approval send records an audit run but never calls Feishu send.
  - `real`: allow real send when global external send is enabled.
  - `disabled`: block approval send for this conversation.

These policies apply to new incoming messages and future approval sends. Existing AgentRuns keep their historical routing result.

## User and Conversation Display

v0.2.5 adds a small local directory cache:

- `external_users` caches Feishu `open_id` profile lookups.
- `conversations.name` is updated with a readable Feishu chat name when available.
- If Feishu permissions are missing, WorkBuddy keeps the original `open_id` / `chat_id`, records a failed `channel_events` entry, and continues the message pipeline.

Useful permissions for better display names:

- Contact/user read permission for resolving `open_id`.
- IM chat read permission for resolving group names.

## Demo Script

1. Start the API:

```bash
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

2. Start the web app:

```bash
npm run dev:web -- --host 0.0.0.0 --port 5173
```

3. Start the Feishu stream worker:

```bash
npm run dev:feishu-stream
```

4. Open the console:

```text
http://localhost:5173
```

5. Send a Feishu message to the bot:

```text
我想试用一下，你们多少钱，可以发报价方案吗？
```

6. In WorkBuddy:

- Workbench: check stream worker status, send mode and recent Feishu activity.
- Message Events: filter source by Feishu and inspect sender / conversation display.
- Approval Queue: open the detail drawer, approve or edit the draft, then send.
- Feishu Diagnostics: check Token, inspect recent stream/send audit rows, and run a safe mock send.
- Feishu Diagnostics: use the business trace links to jump to the created message, lead/task, approval and send audit rows.
- Feishu Conversations: bind the active test chat to a fixed agent or set it to mock-only before a demo.
- Demo Mode: prepare the local demo state, review the live checklist and switch risky real-send conversations back to mock.
- Config Center: review global IM switches and the Feishu / WeCom / DingTalk adapter capability matrix.
- Agent Runs: verify `feishu_stream_worker`, scenario agent and `feishu_send_adapter` audit rows.

7. With `ENABLE_EXTERNAL_SEND=false`, send is recorded as mock. With `ENABLE_EXTERNAL_SEND=true` and Feishu send permissions, the bot replies in Feishu.

## URL Verification Test

Payload:

```json
{
  "type": "url_verification",
  "token": "your-verification-token-if-configured",
  "challenge": "test_challenge"
}
```

Expected response:

```json
{
  "challenge": "test_challenge"
}
```

If `FEISHU_VERIFICATION_TOKEN` is set, the callback token must match it. If the setting is empty, local tests accept any token.

## Message Receive Test

Payload:

```json
{
  "schema": "2.0",
  "header": {
    "event_id": "evt_demo_001",
    "event_type": "im.message.receive_v1",
    "token": "your-verification-token-if-configured",
    "create_time": "1779253200000"
  },
  "event": {
    "sender": {
      "sender_id": {
        "open_id": "ou_demo_user"
      },
      "sender_type": "user"
    },
    "message": {
      "message_id": "om_demo_001",
      "chat_id": "oc_demo_chat",
      "chat_type": "group",
      "message_type": "text",
      "create_time": "1779253200000",
      "content": "{\"text\":\"这个方案多少钱？可以发报价吗？\"}"
    }
  }
}
```

Expected behavior:

- Creates a `MessageEvent` with `channel=feishu`.
- Runs the existing Agent Router.
- Creates a sales lead and follow-up task when sales rules match.
- Creates an approval draft instead of sending anything externally.

## Encrypted Callback

Encrypted callbacks contain an `encrypt` field. v0.15.1 supports encrypted HTTP
callbacks when `FEISHU_ENCRYPT_KEY` is configured in the Config Center or local
runtime environment.

If decrypt fails, WorkBuddy records a failed `ChannelEvent` with
`event_type=feishu.webhook.parse.failed` so the diagnostics pages can expose the
error without silently dropping the callback.

## Stream Event Behavior

`im.message.receive_v1`:

- Converts the SDK event to the same `ImportRecord` shape used by CSV, JSON and HTTP webhook imports.
- Calls the existing `import_records` service.
- Reuses the Agent Router and Action Engine.
- Generates `MessageEvent`, `AgentRun`, `Ticket` or `Lead`, `FollowupTask` and `Approval` records based on existing rules.

Channel events:

- `im.chat.member.bot.added_v1`
- `im.chat.member.bot.deleted_v1`
- `im.chat.access_event.bot_p2p_chat_entered_v1`

These are stored as `channel_events` records for audit and future UI work. They do not create business messages or approvals.
