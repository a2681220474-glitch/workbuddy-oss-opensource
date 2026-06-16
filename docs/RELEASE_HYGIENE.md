# Release Hygiene Checklist

Use this checklist before tagging a public release or opening the repository for
external users.

## Repository Cleanliness

Run:

```bash
git status --short
npm run check:release
npm run check:deployment
npm run build:web
.venv/bin/python -m compileall apps/api
npm run db:migrate
```

Only intentional source files, docs, scripts, migrations, and examples should be
tracked.

## Never Commit

- `.env` or `.env.local`
- runtime SQLite databases
- `apps/api/data/`
- generated private reports
- raw customer/candidate/member exports
- local demo videos unless intentionally prepared for release
- one-off media generation scripts unless reviewed

The current local-only artifacts are ignored by default:

```text
generated_documents/
docs/assets/workbuddy_v0.12.0_demo.mp4
scripts/generate_workbuddy_video_ffmpeg.py
```

## Documentation Checks

Confirm these docs exist and match the current version line:

- `docs/INSTALL.md`
- `docs/RELEASE_MODES.md`
- `docs/FEISHU_SETUP.md`
- `docs/WECOM_SETUP.md`
- `docs/DEPLOYMENT.md`
- `SECURITY.md`
- `docs/PRIVACY_SECURITY.md`

## Data Redaction

Before sharing logs, screenshots, or issue payloads:

1. remove credentials
2. remove personal names if not needed
3. remove chat IDs and open IDs unless needed
4. replace private message text with representative samples
5. keep object IDs for debugging when safe

## Release Boundary

A release candidate can ship with documented warnings. It should not claim:

- Docker full-stack boot if Docker was unavailable
- real Feishu/WeCom send if only mock send was tested
- production-ready authentication if local identity switching is still used
- vector RAG if only lightweight retrieval is implemented
