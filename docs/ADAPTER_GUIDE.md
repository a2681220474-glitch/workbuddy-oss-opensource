# Adapter Guide

WorkBuddy OSS adapters convert external IM payloads into the same local message contract used by CSV and JSON imports.

## Current Status

| Channel | Status | Notes |
| --- | --- | --- |
| Feishu | Working path | Long connection worker, HTTP fallback, directory enrichment, approval-based mock/real send safeguards. |
| WeCom | Skeleton | Mock payload preview/import only. No real account integration in v0.5.0. |
| DingTalk | Skeleton | Mock payload preview/import only. No real account integration in v0.5.0. |
| CSV/JSON/Text | Working path | Local import path for open-source users and repeatable product tests. |

## Adapter Responsibilities

An adapter should:

- Verify signatures or tokens when receiving real webhooks.
- Store raw channel events in `channel_events`.
- Normalize message payloads into `ImportRecord`.
- Call the shared import/runtime path.
- Never call a scenario Agent directly.
- Never send a reply from a receive handler.

Normalized fields:

```json
{
  "text": "message body",
  "sender_name": "readable sender",
  "sender_external_id": "external user id",
  "conversation_id": "external chat id",
  "conversation_name": "readable chat name",
  "conversation_type": "group",
  "channel": "feishu",
  "message_type": "text",
  "external_message_id": "unique external id",
  "timestamp": "2026-05-24T10:00:00+08:00",
  "raw_payload": {}
}
```

## Shared Runtime Path

```text
adapter payload
  -> ImportRecord
  -> import_records
  -> MessageEvent
  -> Agent Router
  -> Action Engine
  -> Business Object / Approval / AgentRun
```

This keeps CSV, Feishu, future WeCom and future DingTalk behavior consistent.

## Send Policy

All external sends must respect:

- `ENABLE_EXTERNAL_SEND`
- global default send mode
- conversation send mode: `inherit`, `mock`, `real`, `disabled`
- approval status
- idempotency checks

When any requirement is unclear, the adapter should choose mock mode or block the send and write a diagnostic AgentRun.

## Testing A New Adapter

1. Add or update `apps/api/modules/adapters/<channel>.py`.
2. Register it in `apps/api/modules/adapters/registry.py`.
3. Add a mock payload doc under `docs/`.
4. Verify the Adapter Test page can preview the payload.
5. Import the payload and confirm MessageEvent, AgentRun, Approval and business objects appear.
6. Confirm Channel Events show successes and parse failures.
7. Keep real sending disabled until approval send preview clearly explains the mode.
