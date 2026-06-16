# Privacy And Security Notes

WorkBuddy OSS turns IM messages into business objects. That means message text,
sender names, attachments, approval drafts, AgentRun prompts, and audit logs may
contain private or regulated information.

## Data Categories

Potentially sensitive data:

- customer support messages
- sales lead details
- community member messages
- candidate resumes or interview notes
- channel user IDs and chat IDs
- approval drafts and final replies
- AgentRun prompts and model outputs
- raw adapter callback payloads

## Local Storage

Default local mode stores data in:

```text
apps/api/data/workbuddy.db
apps/api/data/logs/
apps/api/data/backups/
```

These paths are ignored by git. Do not attach them to public issues without
redaction.

## Logging

Structured logs are useful for operations, but may include object IDs and error
details. Avoid logging raw secrets. When sharing logs:

1. remove API keys and channel secrets
2. remove real user identifiers
3. remove private message content unless necessary
4. prefer AgentRun/Approval/Message IDs over raw payloads

## Model Providers

When `LLM_PROVIDER=openai_compatible`, selected message text may be sent to the
configured model provider for low-confidence routing. Use mock mode when testing
with private data that must not leave the local machine.

Recommended private-data mode:

```env
LLM_PROVIDER=mock
ENABLE_EXTERNAL_SEND=false
```

## Real IM Connectors

Feishu and WeCom connector setup should use test apps first. Before enabling
real send:

- verify the target workspace and conversation
- verify send preview
- verify conversation policy
- keep one human approval step
- confirm delivery audit after send

## Backups

Backups can contain the full database. Store them in a private location, encrypt
them for off-machine transfer, and verify restore plans before deleting source
data.
