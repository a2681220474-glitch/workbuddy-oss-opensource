# WorkBuddy OSS Master Plan

The canonical master plan currently lives at:

`../MASTER_PLAN_FINAL.md`

This file exists so GitHub readers can find the plan under `docs/`, while keeping the original final planning document intact at the repository root.

Current summary:

- Repository name: WorkBuddy OSS
- Product name: WorkBuddy OSS
- Positioning: open-source IM Agent workflow middleware for Chinese teams
- Core value: turn chat messages into trackable, approvable, auditable business objects
- Phase 0: local MVP with CSV/JSON imports, MessageEvent, Agent Router, Action Engine, approval queue, AgentRun audit logs, support tickets, sales leads and demo data
- Phase 1: first real IM integration, planned around Feishu
- Later phases: private traffic/community operations, recruiting/onboarding, enterprise adapters, plugin ecosystem

Important Phase 0 boundary:

Do not connect real Feishu, WeCom or DingTalk yet. Keep adapter placeholders and interfaces only. The first milestone is a local demo loop that can run without external credentials.
