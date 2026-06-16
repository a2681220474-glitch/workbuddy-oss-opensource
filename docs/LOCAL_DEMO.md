# Local Demo Guide

This guide is the local Business Alpha Beta happy path.

## 1. Configure

```bash
cp .env.example .env
```

Keep `LLM_PROVIDER=mock` unless you are intentionally testing a provider integration later.

## 2. Start

Docker:

```bash
docker compose up --build
```

Manual backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Manual frontend:

```bash
cd apps/web
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 3. Open

- Web console: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

## 4. Import Demo Data

Use the import screen to upload:

1. `examples/demo_support_messages.csv`
2. `examples/demo_sales_messages.csv`
3. `examples/demo_business_alpha_messages.csv`
4. `examples/demo_messages.json`

For a faster guided path, open `http://localhost:5173/#demo` and click “一键准备 Beta 验收”.

## 5. Verify

After import, confirm:

- messages are visible as MessageEvents
- support messages create Tickets
- sales messages create Leads
- customer-facing drafts enter Approvals
- AgentRun records exist for router and scenario Agent decisions
- Dashboard counts update
- Business Object Center shows Ticket, Lead, Task, Candidate, Knowledge and Report counts
- Tickets can be filtered by status/priority and moved through processing/resolved/closed
- Leads show a funnel and can be moved to contacted/proposal/won
- KnowledgeGap rows can be accepted into KnowledgeItem or ignored
- KnowledgeItem rows can be published or archived
- Reports can be generated and filtered by report type
- Dashboard operations summary shows support risk, sales funnel, knowledge gaps and latest reports
- Left navigation is grouped by workspace, message loop, scenario Agents, and bottom utility entries
- Ticket status changes follow the configured state machine
- SLA thresholds can be adjusted on the Tickets page
- Ticket knowledge check shows hit/miss and can create KnowledgeGap or published KnowledgeItem
- Support daily report includes SLA risk, status distribution and knowledge gaps
- Sidebar second-level groups are collapsed by default after refresh
- Sales leads follow the configured stage state machine
- Sales lead assistant shows score dimensions, next step and external reply draft
- Sales reply drafts enter the approval queue instead of being sent directly
- Sales daily report includes high-intent leads, stalled leads, follow-up work and won/lost progress
- Community operations page shows group activity, high-intent users, unanswered questions, risk messages and community tasks
- Community risk replies can be generated as drafts and sent into the approval queue
- Community tasks can be completed from the dedicated page
- Community daily report includes high-intent users, unanswered questions, risk messages, tasks and group activity
- Candidate stages can be advanced through screening, interview, offer, onboarding, hired and rejected
- Candidate assistant shows JD/resume match dimensions, strengths, risks, gaps and recommendation
- Interview questions are grouped by capability, resume highlight, risk point and motivation fit
- Onboarding checklist items can be checked off from the candidate assistant
- Recruiting progress report includes funnel, high-match candidates, interview work, offer/onboarding preparation, risk candidates and recruiting tasks
- Dashboard shows four Agent overview cards and a risk aggregation strip
- Approval queue can be filtered by status, Agent and business object type
- AgentRun page can be filtered by Agent, status and business object, with prompt/output/action details
- Demo mode preparation shows a Beta validation report with pass/fail checks

## Demo Narrative

Support path:

```text
customer asks for refund
  -> MessageEvent
  -> support route
  -> Ticket
  -> reply draft
  -> pending Approval
  -> AgentRun audit
```

Sales path:

```text
prospect asks about private deployment price
  -> MessageEvent
  -> sales route
  -> Lead
  -> follow-up recommendation
  -> pending Approval
  -> AgentRun audit
```

Community path:

```text
group member asks about buying / complains no one replied
  -> MessageEvent
  -> community route
  -> community task / lead / knowledge gap
  -> risk reply draft
  -> pending Approval
  -> community daily report
```

Recruiting path:

```text
candidate or HR message mentions resume / interview / onboarding
  -> MessageEvent
  -> recruiting route
  -> Candidate
  -> interview questions
  -> onboarding Checklist
  -> candidate-facing reply Approval
  -> recruiting progress report
```

Beta readiness path:

```text
open Demo Mode
  -> one-click prepare Beta validation data
  -> review Beta validation report
  -> inspect Dashboard four-Agent overview
  -> filter Approval queue by Agent / object
  -> trace AgentRun prompt, output and structured actions
```
