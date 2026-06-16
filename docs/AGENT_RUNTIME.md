# Agent Runtime

The Phase 0 runtime is intentionally small: rules first, mock/demo LLM second, structured Actions always.

## Router

Agent Router receives a `MessageEvent` and returns a route decision.

Suggested output:

```json
{
  "scenario": "support",
  "intent": "refund_request",
  "confidence": 0.88,
  "reason": "message contains refund and order issue keywords"
}
```

Routing rules:

- Support: refund, complaint, broken, unavailable, invoice, order, after-sales, error, cannot login
- Sales: price, quote, trial, demo, contract, procurement, budget, compare, deployment
- Community: high-intent user, unanswered question, complaint/risk, activity feedback, community question
- Recruiting: resume screening, interview scheduling, onboarding
- System command: `/help`, `/report`, `/pause`, `/bind`, `/settings`
- Unknown: no strong rule match, stays in the human inbox fallback

## LLM Provider

Phase 0 uses a mock/demo provider by default. The provider interface should be stable enough for future DeepSeek, Qwen, Moonshot, OpenAI-compatible and Ollama providers.

Environment defaults:

- `LLM_PROVIDER=mock`
- `LLM_MODEL=workbuddy-demo`
- no real secret required

## Scenario Agents

Support Agent:

- Creates or updates a Ticket.
- Classifies category and priority.
- Drafts a customer-facing reply.
- Creates an Approval for the reply.
- Writes an AgentRun.

Sales Agent:

- Creates or updates a Lead.
- Extracts company, budget signal, timeline and pain points when available.
- Drafts a follow-up reply.
- Creates an Approval for the reply.
- Writes an AgentRun.

Community Ops Agent:

- Creates a community follow-up task.
- Creates a Lead for high-intent community users.
- Creates a KnowledgeGap for repeated or unanswered questions.
- Drafts a community-facing reply for approval.
- Emits signals that can be used by community daily reports.

Recruiting HR Agent:

- Creates a Candidate.
- Produces a lightweight JD/resume text match score.
- Suggests interview questions.
- Creates an onboarding checklist and HR follow-up task.
- Drafts candidate-facing replies for approval.

## Action Engine

The Action Engine receives structured Action JSON and performs local side effects.

Phase 0 action types:

- `create_ticket`
- `update_ticket`
- `create_lead`
- `update_lead`
- `create_approval`
- `create_task`
- `create_candidate`
- `add_to_knowledge_base`
- `include_in_daily_report`
- `write_agent_run`

Future action types:

- `send_im_message`
- `sync_to_external_system`

External send actions must remain disabled until the approval workflow and real adapters are implemented.
