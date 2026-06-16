# Roadmap

## Phase 0: Local MVP

Goal: prove the business loop locally.

- CSV / JSON imports
- MessageEvent normalization
- Agent Router
- Action Engine
- Support Ticket Agent
- Sales Lead Agent
- Approval queue
- AgentRun audit logs
- React admin console
- Demo data and docs

Acceptance:

- backend starts locally
- frontend starts locally
- support demo creates Ticket and Approval
- sales demo creates Lead and Approval
- every Agent decision has AgentRun audit data

## Phase 1: Feishu Loop

Goal: run the first real IM workflow.

- Feishu bot callback
- Feishu message normalization
- Feishu user/group mapping
- approval card draft
- approved send action
- delivery audit

## Phase 2: Scenario Depth

Goal: make templates valuable for real teams.

- better support knowledge workflow
- private traffic/community Agent
- sales follow-up pipeline
- daily/weekly reports
- configurable prompts and rules

## Phase 3: More Adapters

Goal: broaden Chinese workplace IM coverage.

- WeCom adapter
- DingTalk adapter
- generic webhook adapter
- adapter SDK draft

## Phase 4: Ecosystem

Goal: turn WorkBuddy OSS into an extensible open-source project.

- Agent template registry
- IM adapter SDK
- prompt registry
- action/tool plugin interface
- production deployment examples
