# Channel Policy Design

v0.4 turns the Feishu-only conversation controls into a channel-neutral policy layer. The goal is to make future WeCom and DingTalk adapters reuse the same routing and delivery rules.

## Data Shape

`conversations` is the shared IM conversation table. It stores the external conversation ID, readable name, channel, last activity time and policy fields.

Policy fields:

- `bound_agent`: `auto`, `support_ticket_agent`, `sales_lead_agent`
- `send_mode`: `inherit`, `mock`, `real`, `disabled`

`auto` means the Agent Router decides from message content. `inherit` means delivery follows the editable default send mode from Config Center, while `ENABLE_EXTERNAL_SEND` remains the real-send kill switch.

## Receive Path

1. Channel adapter receives an event.
2. Adapter resolves user and conversation names when possible.
3. Adapter converts the event into the shared import/message input.
4. The existing import service creates `MessageEvent`.
5. The router attaches conversation policy to the normalized payload.
6. Scenario agent creates structured Actions.
7. Action Engine creates Ticket, Lead, FollowupTask and Approval.
8. AgentRun records every receive, route, action and failure step.

## Routing Policy

For ordinary user messages:

- `support_ticket_agent` forces support ticket routing.
- `sales_lead_agent` forces sales lead routing.
- `auto` keeps existing keyword and confidence routing.

System commands and explicit control commands keep priority over bound agent policy.

## Send Policy

All customer-facing replies still require approval. When an approval is sent:

- `disabled`: block the send and record the reason.
- `mock`: record a mock send result only.
- `inherit`: follow `ENABLE_EXTERNAL_SEND`.
- `real`: allow real send if global credentials and permissions are valid.

This lets a demo chat stay mock-only even when global real sending is enabled.

## API Surface

- `GET /api/conversations?channel=feishu`
- `GET /api/conversations/feishu`
- `PATCH /api/conversations/{id}/policy`
- `GET /api/config/status`
- `PATCH /api/config/default-send-mode`
- `GET /api/channel-events`
- `POST /api/adapters/preview`

The UI currently exposes these through “渠道会话”, “配置中心”, “渠道事件” and “Adapter 测试台”. The API naming is channel-neutral so future WeCom and DingTalk pages can reuse it.
