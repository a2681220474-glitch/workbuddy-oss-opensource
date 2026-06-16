# Channel Adapter Guide

WorkBuddy OSS keeps channel adapters thin. They translate external IM events into the existing `MessageEvent` pipeline, and translate approved reply Actions back into platform-specific send calls only after human approval.

## Common Adapter Contract

Every channel adapter should eventually provide the same surface:

- `receive_event`: accept HTTP callback, long-connection event, or local import.
- `normalize_message`: convert raw payload into the shared message input used by imports.
- `send_message`: send an approved message, respecting global and conversation policy.
- `resolve_user`: map external user IDs to readable names and cache them locally.
- `resolve_conversation`: map external chat IDs to readable conversation names and cache them locally.
- `record_audit`: write `channel_events` and `agent_runs` for receive, parse, send and failure paths.

The concrete protocol lives in `apps/api/modules/adapters/base.py`. Feishu has a real implementation path; WeCom and DingTalk currently use skeleton adapters so the UI and API can show future readiness without pretending to connect accounts.

## Phase 0 Sources

- CSV import
- JSON import
- optional manual paste import

These sources should exercise the same normalization path as future real IM callbacks.

## v0.4 Channel Matrix

Feishu:

- HTTP webhook remains available as backup.
- Long-connection Stream Worker is recommended for local development.
- User and conversation names are cached locally when permissions allow.
- Approval send supports mock, real and disabled policy modes.

WeCom:

- Adapter interface is present.
- Real credential flow, callback parsing and send APIs are not implemented yet.
- Future focus: internal app and customer group scenarios.

DingTalk:

- Adapter interface is present.
- Real Stream/callback parsing and send APIs are not implemented yet.
- Future focus: message receive, approval cards and task notifications.

## Channel Policy

Conversation-level policy is channel-neutral:

- `bound_agent`: `auto`, `support_ticket_agent`, `sales_lead_agent`
- `send_mode`: `inherit`, `mock`, `real`, `disabled`

The router uses `bound_agent` before keyword routing for normal messages. The delivery layer uses `send_mode` to decide whether an approval send should be mocked, sent for real, or blocked.

## Non-Goals In v0.4.0

- no real WeCom or DingTalk account connection
- no production permission model
- no full receive retry queue yet
- no background queue, Redis, Celery or vector database

Business meaning stays in `MessageEvent`, Agent Router, Action Engine and scenario Agents. Adapter code should remain mostly transport and identity resolution.
