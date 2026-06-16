# WeCom Setup Guide

This guide covers a test Enterprise WeChat / WeCom internal app connected to
WorkBuddy OSS through HTTP callback mode.

## Safety Defaults

Recommended local settings:

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
REQUIRE_APPROVAL_FOR_EXTERNAL_REPLIES=true
```

WorkBuddy can receive encrypted WeCom callbacks and create business objects
without sending external replies until `ENABLE_EXTERNAL_SEND=true`.

## 1. Prepare A WeCom Internal App

In the WeCom admin console:

1. Create or open a test internal app.
2. Copy Corp ID, Agent ID, and Secret.
3. Prepare callback Token and EncodingAESKey.
4. Configure a trusted IP if your WeCom tenant requires API source IP checks.

Keep all credentials in `.env.local` or the Config Center. Do not paste them
into docs, issues, or commits.

## 2. Configure WorkBuddy

```env
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
```

Open `http://127.0.0.1:5173/#config` to check whether the configuration is
recognized.

## 3. Expose The Local Callback

Local API callback path:

```text
http://127.0.0.1:8000/api/channels/wecom/webhook
```

For real WeCom callback verification, expose it with a public HTTPS tunnel.
Examples include cloudflared, ngrok, or localtunnel.

The WeCom callback URL should be:

```text
https://<public-domain>/api/channels/wecom/webhook
```

Do not use a temporary tunnel URL as a production callback domain.

## 4. Runtime Checks

```bash
npm run check:wecom-runtime
curl "http://127.0.0.1:8000/api/channels/wecom/status"
curl "http://127.0.0.1:8000/api/channels/wecom/diagnostics/full?check_token=true"
```

In the web console, open `#wecom` and confirm:

- credentials are recognized
- token check is ready
- callback decrypt status is ready after WeCom verification
- real send mode remains disabled unless intentionally enabled
- acceptance traces appear after test messages

## 5. Manual Callback Acceptance

1. Start the API.
2. Start the public HTTPS tunnel.
3. Configure the WeCom callback URL, Token, and EncodingAESKey.
4. Complete WeCom URL verification.
5. Send a test message to the app:

```text
系统登录不上，一直报错，客户很着急
```

6. Verify in WorkBuddy:
   - `#messages`: WeCom MessageEvent exists
   - `#agent-runs`: routing run exists
   - `#objects`: business object exists
   - `#approvals`: pending approval exists
   - `#wecom`: acceptance trace is ready or complete

7. Run:

```bash
npm run check:wecom-acceptance
```

## 6. Manual Send Acceptance

First pass with `ENABLE_EXTERNAL_SEND=false`:

1. Open the generated approval.
2. Confirm send preview shows mock/simulated mode.
3. Approve or edit the draft.
4. Send from the approval page.
5. Confirm WorkBuddy records send audit without external delivery.

Real send pass:

1. Set `ENABLE_EXTERNAL_SEND=true`.
2. Restart the API.
3. Ensure WeCom trusted IP allows the machine's public IP if required.
4. Send one approved test reply.
5. Confirm WeCom receives it and WorkBuddy records the send result.

## Troubleshooting

- Error `60020` usually means the current public IP is not in the WeCom trusted
  IP allowlist.
- If callback verification fails, compare Token and EncodingAESKey in WeCom with
  WorkBuddy config.
- If decrypt fails, regenerate EncodingAESKey and update `.env.local`.
- If send preview is blocked, check conversation policy and
  `ENABLE_EXTERNAL_SEND`.
- If the public tunnel changes, update the WeCom callback URL and verify again.
