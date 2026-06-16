# New Channel Adapter Checklist

This checklist is for adding a real IM channel after v0.4.1. Feishu is the reference implementation; WeCom and DingTalk currently remain skeleton adapters.

## 1. Define Channel Identity

- Pick a stable channel key: `feishu`, `wecom`, `dingtalk`, or a new lowercase key.
- Add a channel adapter under `apps/api/modules/adapters/`.
- Register the adapter in `apps/api/modules/adapters/registry.py`.
- Add UI labels and colors where channel labels are shown.

## 2. Receive Events

- Support either HTTP callback, stream worker, or both.
- Verify callback signatures or tokens before processing.
- Store every non-message callback in `channel_events`.
- Store parse failures as `channel_events` with `status=failed`.
- Never let a channel parse failure crash the main API process.

## 3. Normalize Message

Convert external payloads into the same fields used by CSV/JSON imports:

- `text`
- `sender_name`
- `sender_external_id`
- `conversation_id`
- `conversation_name`
- `conversation_type`
- `channel`
- `message_type`
- `external_message_id`
- `timestamp`
- `raw_payload`

Use the Adapter Test page before writing to the database:

```text
http://localhost:5173/#adapter-test
```

## 4. Resolve People And Conversations

- Resolve external user IDs into readable names when permissions allow.
- Cache user data in `external_users`.
- Resolve group/chat names into `conversations`.
- If permissions are missing, keep the external ID and record the failure in `channel_events`.

## 5. Reuse Runtime Pipeline

Do not call scenario agents directly from adapter code. The adapter should feed the existing flow:

```text
adapter event -> import_records -> MessageEvent -> Agent Router -> Action Engine -> Approval
```

This keeps AgentRun audit logs and approval policy consistent across channels.

## 6. Respect Channel Policy

All channel sends must respect:

- global default send mode from `runtime_settings`
- environment kill switch `ENABLE_EXTERNAL_SEND`
- conversation `send_mode`: `inherit`, `mock`, `real`, `disabled`
- conversation `bound_agent`: `auto`, `support_ticket_agent`, `sales_lead_agent`, `community_ops_agent`, `recruiting_hr_agent`

When unsure, choose mock mode and record why.

## 7. Send After Approval Only

- Never send directly from receive handlers.
- Only approved or edited approvals can send.
- Sending must create an AgentRun with `agent_type` ending in `_send_adapter` or a channel-specific equivalent.
- Duplicate sends should be idempotent.

## 8. UI Acceptance

Before marking a channel usable, verify:

- Config Center shows the channel capability matrix.
- Channel Conversations shows readable names and policy controls.
- Channel Events shows receives, failures and ignored events.
- Adapter Test previews sample payloads.
- Approvals show mock/real/failed send result clearly.
- Agent Runs show receive, route, action and send audit records.
