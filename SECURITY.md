# Security Policy

WorkBuddy OSS is a local-first release-candidate project. It can connect to real
IM platforms, so treat channel credentials, callback payloads, message content,
and approval drafts as sensitive.

## Supported Versions

Security reports should target the latest `main` branch and the current
`v0.20.x` release-candidate line.

## Reporting A Vulnerability

Open a private report or contact the repository maintainer before publishing
details. Do not include real customer messages, API keys, Feishu/WeCom secrets,
or raw callback payloads in public issues.

Useful report content:

- affected version or commit
- reproduction steps using mock or redacted data
- expected and actual behavior
- relevant logs with secrets removed
- whether external sending could be triggered

## Secret Handling

Never commit:

- `.env`
- `.env.local`
- `apps/api/.env`
- `apps/api/.env.local`
- SQLite databases
- Feishu App Secret, Verification Token, or Encrypt Key
- WeCom Secret, Token, or EncodingAESKey
- LLM API keys
- raw customer/candidate/member data

Use `.env.example` for blank configuration keys only.

## External Sending

Keep these defaults unless intentionally validating a test connector:

```env
ENABLE_EXTERNAL_SEND=false
REQUIRE_APPROVAL_FOR_EXTERNAL_REPLIES=true
```

Real sends must go through approval preview, approval decision, delivery audit,
and connector-specific acceptance.
