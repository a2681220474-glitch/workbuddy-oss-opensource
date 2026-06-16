# Release Modes

WorkBuddy OSS supports two local operating modes during `v0.20.x` release
candidate preparation: demo mode and real-connector mode.

## Demo Mode

Use demo mode when presenting the product or validating the local workflow
without sending messages to external users.

Recommended settings:

```env
LLM_PROVIDER=mock
ENABLE_REAL_IM_ADAPTERS=false
ENABLE_EXTERNAL_SEND=false
ENABLE_BACKGROUND_JOBS=false
```

Expected behavior:

- No real IM worker is required.
- External replies are simulated.
- Demo data can be prepared from the web console.
- Approval, audit, business objects, reports, and knowledge flows are still
  visible.

Manual acceptance:

1. Start API and Web.
2. Open `http://127.0.0.1:5173/#demo`.
3. Click `一键准备 Beta 验收`.
4. Confirm the validation report reaches the expected complete state.
5. Open messages, business objects, approvals, knowledge, and reports.

## Real-Connector Test Mode

Use real-connector mode only when validating an owned Feishu or WeCom test app.

Recommended settings:

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
REQUIRE_APPROVAL_FOR_EXTERNAL_REPLIES=true
```

Expected behavior:

- Real messages can be received.
- Generated replies still enter the approval queue.
- External sending remains simulated until explicitly enabled.

To intentionally send externally:

```env
ENABLE_EXTERNAL_SEND=true
```

Before enabling real send:

1. Confirm the target app, group, or user belongs to your test workspace.
2. Confirm approval detail shows the correct send preview.
3. Confirm the conversation send policy allows real send.
4. Approve or edit the draft manually.

## Empty Environment

For a clean local trial:

1. Copy `.env.example` to `.env`.
2. Leave all channel secrets empty.
3. Run `npm run db:migrate`.
4. Start API and Web.
5. Use the import page, demo page, or adapter test console to create first data.

Do not commit local SQLite databases, `.env.local`, screenshots containing
secrets, or exported private customer data.
