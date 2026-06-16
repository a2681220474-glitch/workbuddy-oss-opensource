# Data Model

Phase 0 keeps the model small and demo-friendly while preserving the long-term shape.

## MessageEvent

Normalized message created from CSV, JSON or future IM callbacks.

Suggested fields:

- `id`
- `source`: `csv`, `json`, `feishu`, `wecom`, `dingtalk`, `webhook`
- `external_message_id`
- `conversation_id`
- `conversation_type`: `private`, `group`
- `sender_id`
- `sender_name`
- `sender_role`
- `sent_at`
- `content_type`: `text`, `image`, `file`, `mixed`
- `content`
- `raw_payload`
- `normalized_at`

## AgentRun

Every Agent or LLM-like decision writes one audit row.

Suggested fields:

- `id`
- `agent_name`
- `scenario`: `support`, `sales`, `community`, `recruiting`, `router`
- `message_event_id`
- `intent`
- `input_snapshot`
- `prompt_snapshot`
- `model_provider`
- `model_name`
- `model_output`
- `action_json`
- `confidence`
- `status`
- `error_message`
- `created_at`

## Approval

Human review item for every external reply draft.

Suggested fields:

- `id`
- `agent_run_id`
- `message_event_id`
- `business_object_type`
- `business_object_id`
- `action_type`
- `draft_content`
- `status`: `pending`, `approved`, `rejected`, `edited`
- `reviewer`
- `review_note`
- `created_at`
- `reviewed_at`

## Ticket

Support object generated from customer service messages.

Suggested fields:

- `id`
- `title`
- `customer_name`
- `conversation_id`
- `source_message_id`
- `category`
- `priority`
- `status`
- `summary`
- `suggested_reply`
- `created_at`
- `updated_at`

## Lead

Sales object generated from high-intent messages.

Suggested fields:

- `id`
- `customer_name`
- `company`
- `conversation_id`
- `source_message_id`
- `intent_level`
- `budget_signal`
- `timeline`
- `pain_points`
- `next_step`
- `suggested_reply`
- `status`
- `created_at`
- `updated_at`

## Action

Actions are not only free text. They are structured instructions that can be reviewed, persisted and eventually executed.

Example:

```json
{
  "type": "create_ticket",
  "requires_approval": true,
  "business_object": {
    "category": "refund",
    "priority": "high"
  },
  "draft_reply": "已收到你的退款问题，我们先核对订单状态，稍后给你明确处理方案。"
}
```
