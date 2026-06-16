# Agent Guide

This guide describes how WorkBuddy OSS scenario Agents should behave in the Business Alpha.

## v0.6 Support Ticket Knowledge Loop

The support ticket knowledge Agent now has a tighter local loop:

- Ticket status transitions are constrained by a small state machine: open, in progress, waiting customer, resolved and closed.
- SLA thresholds are tenant settings stored locally and can be adjusted without connecting external systems.
- Each ticket can run a knowledge hit/miss check against published KnowledgeItem records.
- Missed tickets can be converted into KnowledgeGap records, or directly published as KnowledgeItem when the operator has a reliable answer.
- Support daily reports should call out SLA risk, ticket status distribution, priority distribution and knowledge gaps.

## v0.7 Sales Lead Follow-Up Loop

The sales lead Agent now focuses on making follow-up explicit and auditable:

- Lead stage transitions are constrained by the configured funnel state machine.
- Scoring is explained through budget, timing, need, decision role and risk dimensions.
- Each lead can generate a suggested next step and an external reply draft.
- External sales replies must enter the approval queue before they can be sent.
- Sales daily reports should call out high-intent leads, stalled leads, today follow-ups, proposal/negotiation work and won/lost progress.

## v0.8 Community Operations Loop

The community operations Agent now has a dedicated local console:

- Community messages are grouped into conversations with activity, high-intent, unanswered and risk counts.
- High-intent community users are surfaced as leads for sales or operations follow-up.
- Unanswered or repeated community questions stay visible as `KnowledgeGap` candidates.
- Risk messages can generate community-facing reply drafts that must enter approval before any external send.
- Community follow-up tasks can be completed from the community page.
- Community daily reports should call out high-intent users, unanswered questions, risk messages, tasks and group activity.

## v0.9 Recruiting And Onboarding Loop

The recruiting HR Agent now has a deeper candidate workflow:

- Candidate stages are constrained by a local funnel: screening, interview, offer, onboarding, hired and rejected.
- JD/resume matching is explained through role fit, experience depth, collaboration, motivation and risk dimensions.
- Interview questions should be grouped by capability, resume highlight, risk point and motivation fit.
- Onboarding checklist items are structured with owner, phase, status and completed state.
- Recruiting progress reports should call out funnel counts, high-match candidates, interview work, offer/onboarding preparation, risk candidates and open recruiting tasks.

## v0.10 Beta Readiness Loop

The four scenario Agents now share a clearer Beta acceptance surface:

- Dashboard shows one card per Agent with object count, pending work, risk count, approval count and report count.
- Risk inbox aggregates support risks, high-intent sales leads, knowledge gaps and high-risk approvals.
- Approval queue can be filtered by status, target Agent and business object type.
- AgentRun audit can be filtered by Agent, status and business object, and the detail drawer shows prompt, output and structured actions.
- Demo preparation returns a validation report for message import, all four Agents, knowledge, reports, approvals and audit logs.

## Contract

Every Agent receives a normalized `MessageEvent` plus a route decision and returns structured Action JSON.

Agents should not send external messages directly. Customer-facing, candidate-facing or community-facing replies must become approval drafts first.

Minimum output shape:

```json
{
  "agent_name": "support_ticket_agent",
  "prompt": { "key": "support.ticket.v1", "version": "v0.5-alpha" },
  "analysis": {
    "confidence": 0.82,
    "summary": "short business reasoning"
  },
  "actions": [
    {
      "action_type": "create_ticket",
      "priority": "high",
      "requires_approval": false,
      "business_object": {
        "type": "ticket",
        "fields": {}
      }
    }
  ]
}
```

## Router Order

The Router chooses the target Agent in this order:

1. System commands such as `/help`, `/report`, `/pause`, `/bind`, `/settings`.
2. Conversation-bound Agent policy from `conversations.bound_agent`.
3. Keyword rules for recruiting, support, community and sales.
4. Mock/LLM fallback classification.
5. Low-confidence `chat_agent` fallback, which becomes a human inbox item.

## Built-In Agents

### Support Ticket Agent

Expected objects:

- `Ticket`
- `KnowledgeGap` when an answer is missing or likely reusable
- `Approval` for any external reply
- `AgentRun` audit log

Typical intents: refund, complaint, bug, account issue, billing issue, how-to question and feature request.

### Sales Lead Agent

Expected objects:

- `Lead`
- `FollowupTask`
- `Approval` for any external reply
- `AgentRun` audit log

Typical intents: pricing, demo, trial, proposal and purchase intent.

### Community Ops Agent

Expected objects:

- `FollowupTask` with `task_type=community_followup`
- `Lead` for high-intent users
- `KnowledgeGap` for unanswered or repeated questions
- `Approval` for community-facing replies
- Report signals for community daily reports

Typical intents: high-intent user, unanswered question, risk/complaint, activity feedback and community question.

### Recruiting HR Agent

Expected objects:

- `Candidate`
- `FollowupTask` with `task_type=recruiting_followup`
- `Approval` for candidate-facing replies

The Alpha does not parse PDFs or resumes deeply. It accepts local text/JSON messages, extracts simple role/name signals, gives a lightweight match score, suggests structured interview questions and creates an onboarding checklist that can be checked off locally.

## Safety Rules

- Treat external replies as drafts.
- Keep API keys and credentials outside code.
- Preserve `AgentRun` for every route/action decision.
- Prefer deterministic rules for common business messages.
- Add new business objects through the Action Engine instead of writing database side effects inside an adapter.
- Beta features should keep cross-Agent visibility consistent: every new Agent output should be traceable from Dashboard, Approval, AgentRun and Business Object Center.
