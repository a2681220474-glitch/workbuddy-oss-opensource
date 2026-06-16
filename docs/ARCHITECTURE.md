# Architecture

WorkBuddy OSS is a local-first open-source IM Agent workflow hub. The product proves one core loop: chat records and IM messages become standardized events, events are routed to scenario Agents, Agents emit structured Actions, Actions create business objects and human approvals, and every Agent run is auditable.

## Current Components

```text
apps/api
  FastAPI
  SQLite + SQLModel
  CSV / JSON import
  MessageEvent persistence
  Agent Router
  Action Engine
  Approval queue
  AgentRun audit log
  Business Object Center
  support, sales, community, recruiting scenario modules

apps/web
  React + Vite
  Ant Design
  Dashboard
  import screen
  approval queue
  tickets
  leads
  tasks
  candidates
  knowledge gaps and items
  reports
  AgentRun log

examples
  demo CSV and JSON messages
  small knowledge snippets
```

## Runtime Flow

```text
Import source
  -> normalize raw row/object
  -> MessageEvent
  -> Agent Router
  -> scenario Agent
  -> Action Engine
  -> Ticket / Lead / Task / Candidate / KnowledgeGap / Approval
  -> AgentRun
  -> Business Object Center / web review / report generation
```

## Business Objects

The runtime creates durable objects instead of only returning chat text.

| Object | Purpose |
| --- | --- |
| `Ticket` | Customer support problems, refunds, bugs, complaints and knowledge gaps. |
| `Lead` | Sales interest, pricing, demo, trial, proposal and purchase signals. |
| `FollowupTask` | Human follow-up tasks for support, sales, community and recruiting. |
| `Candidate` | Recruiting and onboarding records with match score, interview questions and checklist. |
| `KnowledgeGap` | Repeated or unanswered questions that should become reusable knowledge. |
| `KnowledgeItem` | Accepted knowledge content produced from gaps or manual curation. |
| `Report` | Internal daily/progress reports for support, sales, community, recruiting and knowledge gaps. |

Business objects are intentionally small SQLModel tables in v0.5.0. The goal is an understandable open-source Alpha that can run locally before adding heavier workflow engines.

## Scenario Agents

The four product Agents from `MASTER_PLAN_FINAL.md` are represented as scenario modules:

- `support_ticket_agent`: creates tickets, knowledge gaps and external reply approvals.
- `sales_lead_agent`: creates leads, follow-up tasks and external reply approvals.
- `community_ops_agent`: detects high-intent users, unanswered questions, risk messages, community tasks and report signals.
- `recruiting_hr_agent`: creates candidates, JD/resume match summaries, interview questions and onboarding checklists.

The Router supports system commands, conversation-bound Agents, keyword rules and low-confidence fallback into the human inbox.

## Boundary Decisions

- SQLite is enough for the local Alpha.
- Mock/demo LLM provider is the default.
- Rules run before model classification.
- Agent output should be structured Action JSON.
- External replies are never sent directly from receive handlers.
- Feishu keeps its existing receive/send-approval path. WeCom and DingTalk remain adapter skeletons and test payloads until real credentials are explicitly configured.

## Module Ownership

- Backend foundation: `apps/api/`
- Agent runtime: `apps/api/modules/routing/`, `apps/api/modules/actions/`, `apps/api/modules/scenarios/`
- Frontend console: `apps/web/`
- Documentation and demo assets: `README.md`, `docs/`, `examples/`, `.env.example`, compose files

These boundaries are intentionally simple so multiple agents can work without touching the same files.
