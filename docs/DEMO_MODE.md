# Demo Mode

v0.12.0 keeps the demo mode page as the Release Candidate acceptance console. It keeps the current Feishu integration intact while making the Business Alpha Beta scenario path explicit and safer.

## What The Button Does

`POST /api/demo/prepare` performs a local demo reset:

- deletes local CSV/JSON demo business records
- preserves Feishu message history and Feishu channel records
- re-imports support, sales, community and recruiting demo CSV files
- promotes pending KnowledgeGap records into published KnowledgeItem records
- generates operations, support, sales, community, recruiting and knowledge gap reports
- restores all conversation policies to `bound_agent=auto` and `send_mode=inherit`
- returns object counts, import-created object counts, generated reports and a clickable validation flow

This is different from `POST /api/demo/reset`, which clears all tenant demo data including Feishu records.

## Live Demo Steps

1. Start API:

```bash
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

2. Start Web:

```bash
npm run dev:web -- --host 0.0.0.0 --port 5173
```

3. Start Feishu Stream Worker:

```bash
npm run dev:feishu-stream
```

4. Open:

```text
http://localhost:5173/#demo
```

5. Click “一键准备 Beta 验收”.

6. Optionally send this to the Feishu bot:

```text
群里有人吗？我想报名训练营，怎么买？
```

7. In WorkBuddy, follow the Release Candidate checklist:

- 消息导入
- 消息事件 and AgentRun routing audit
- Business Object Center
- 客服工单流转
- 销售线索推进
- 知识沉淀
- 报告生成
- 审批队列 and audit logs

## Safety Checks

The demo page shows whether `ENABLE_EXTERNAL_SEND` is enabled. If a conversation is set to `send_mode=real`, the page displays it and provides a one-click switch to `mock`.

For public demos, recommended settings are:

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
```

If real sending is intentionally needed, keep `ENABLE_EXTERNAL_SEND=true`, then verify the target conversation before pressing “发送” in the approval queue.
