# Feishu Setup Guide

This guide takes a new WorkBuddy OSS tester from an empty Feishu app to a
manually accepted message workflow. Use a test workspace and test app first.

## Safety Defaults

Recommended local settings:

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
REQUIRE_APPROVAL_FOR_EXTERNAL_REPLIES=true
```

With these settings, WorkBuddy can receive real Feishu messages, but approval
sends are simulated unless you later enable `ENABLE_EXTERNAL_SEND=true`.

## 1. Create Or Open A Feishu App

In the Feishu developer console:

1. Create an internal app for your test workspace.
2. Copy App ID and App Secret.
3. Open event subscription settings.
4. Prefer long-connection event receiving for local testing.

Subscribe to:

- `im.message.receive_v1`
- `im.chat.member.bot.added_v1`
- `im.chat.member.bot.deleted_v1`
- `im.chat.access_event.bot_p2p_chat_entered_v1`

If the app enables event encryption, copy the Encrypt Key into WorkBuddy as
`FEISHU_ENCRYPT_KEY`.

## 2. Configure WorkBuddy

Use either `.env.local` or the Config Center at `http://127.0.0.1:5173/#config`.

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_API_BASE_URL=https://open.feishu.cn
FEISHU_STREAM_STATUS_PATH=apps/api/data/feishu_stream_status.json
WORKBUDDY_PUBLIC_BASE_URL=
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
```

Do not commit `.env.local`.

## 3. Start Services

API:

```bash
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Web:

```bash
npm --prefix apps/web run dev -- --host 127.0.0.1 --port 5173
```

Feishu stream worker:

```bash
npm run dev:feishu-stream
```

The Feishu developer console connection check only succeeds while the stream
worker is online.

## 4. Runtime Checks

```bash
npm run check:feishu-stream
curl http://127.0.0.1:8000/api/channels/feishu/status
curl "http://127.0.0.1:8000/api/channels/feishu/diagnostics/full?check_token=true"
```

In the web console, open `#feishu` and confirm:

- stream worker is online
- token check is ready
- real send mode is disabled unless intentionally enabled
- card callback status is clear
- recent events and recent messages update after test messages

## 5. Manual Receive Acceptance

1. Add the bot to a Feishu test group or send it a private message.
2. Send a support-like message, for example:

```text
系统登录不上，一直报错，客户很着急
```

3. Open WorkBuddy pages:
   - `#messages`: new MessageEvent exists
   - `#agent-runs`: routing run exists
   - `#objects`: business object exists
   - `#approvals`: pending approval exists
   - `#feishu`: trace links connect the chain

4. Run:

```bash
npm run check:feishu-acceptance
```

## 6. Manual Send Acceptance

Keep `ENABLE_EXTERNAL_SEND=false` for the first pass:

1. Open the generated approval.
2. Confirm send preview shows mock/simulated mode.
3. Approve or edit the draft.
4. Send from the approval page.
5. Confirm an audit record is created and no real Feishu message is sent.

Only after mock send is accepted:

1. Set `ENABLE_EXTERNAL_SEND=true`.
2. Restart the API.
3. Confirm the target conversation is a test conversation.
4. Confirm the conversation policy allows real send.
5. Send one approved test reply.
6. Confirm Feishu receives it and WorkBuddy records the Feishu message id.

## 7. Approval Card Button Callback

Feishu approval cards are sent as interactive cards. Clicking `通过`, `拒绝`,
or `查看详情` does not use the long-connection worker. Feishu calls a public HTTP
callback URL instead.

If the Feishu client shows:

```text
目标回调服务当前未在线
```

the callback URL configured in the Feishu developer console cannot reach the
current WorkBuddy API.

For local testing:

1. Start the API and Web normally.
2. Start an HTTPS tunnel or use a deployed HTTPS domain that forwards to the API.
3. Set:

```env
WORKBUDDY_PUBLIC_BASE_URL=https://your-public-domain.example.com
```

4. Restart the API.
5. Open `#feishu` and copy the generated card callback URL.
6. In the Feishu developer console, configure the card interaction / bot callback URL as:

```text
https://your-public-domain.example.com/api/channels/feishu/webhook
```

7. Send a WorkBuddy approval card to the test approval chat.
8. Click `通过` or `拒绝` in Feishu.
9. Confirm the WorkBuddy approval status changes and `卡片操作历史` records the callback.

## Troubleshooting

- If the Feishu console says connection failed, restart `npm run dev:feishu-stream`
  and wait for the worker to reconnect.
- If an approval card button says `目标回调服务当前未在线`, configure
  `WORKBUDDY_PUBLIC_BASE_URL`, restart the API, and update the Feishu card
  interaction callback URL to `/api/channels/feishu/webhook`.
- If status says credentials are missing, restart the API after saving
  `.env.local`.
- If real send fails, check app permissions, bot group membership, and the
  approval send preview before retrying.
- If messages do not appear, send a new message after the worker is online;
  long-connection workers do not replay old messages by default.
