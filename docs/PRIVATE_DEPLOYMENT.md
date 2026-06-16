# Private Deployment Target

`v1.0.0` starts with an Oracle Cloud Infrastructure Always Free deployment
target because it is the best current fit for a free private WorkBuddy OSS
server that can run the full stack.

## Selected Target

Recommended target:

- Provider: Oracle Cloud Infrastructure
- Free tier: Always Free
- Shape: Ampere A1 `VM.Standard.A1.Flex`
- OS: Ubuntu LTS
- Stack: Docker Compose, PostgreSQL, Redis, API, Web, Caddy, runtime jobs

Why this target:

- It can run a real VM rather than a sleeping app container.
- It has enough memory for Postgres, Redis, API, Web, and workers when capacity
  is available.
- It supports standard Linux hardening: SSH keys, firewall, fail2ban, Docker,
  and Caddy-managed HTTPS.

Tradeoffs:

- Oracle account signup usually requires payment-method verification.
- Ampere A1 capacity can be region-dependent.
- The server must still be hardened and monitored; "free" does not mean
  maintenance-free.

## Alternatives Considered

- Google Cloud free `e2-micro`: useful for very small services, but too small
  for the full WorkBuddy stack with Postgres/Redis/workers.
- Fly.io/Render/Railway-style app hosting: convenient for demos, but free
  allowances and sleeping behavior are not ideal for a private IM workflow
  server.
- Local machine + tunnel: useful for testing Feishu/WeCom callbacks, not a
  stable private deployment.

## Required User-Side Setup

These steps need the account owner:

1. Create or open an Oracle Cloud account.
2. Create an Always Free Ampere A1 Ubuntu instance.
3. Attach an SSH public key.
4. Configure VCN/security list or NSG to allow only:
   - `22/tcp`
   - `80/tcp`
   - `443/tcp`
5. Point a domain `A` record to the server public IP.
6. Provide the server IP/domain and SSH username/key access for deployment.

## Repository Deployment Assets

The OCI deployment package is in:

```text
deploy/oci-free/
```

Important files:

- `README.md`: operator runbook
- `.env.production.example`: production env template
- `docker-compose.yml`: full private stack
- `Caddyfile`: HTTPS and reverse proxy
- `bootstrap_ubuntu.sh`: Docker/UFW/fail2ban setup
- `deploy.sh`: build and start stack
- `check_remote.sh`: remote health check

## First Acceptance Target

The first remote acceptance target is intentionally conservative:

```text
HTTPS homepage loads
  -> local /health returns the current local version (the validated ECS currently reports 1.1.14)

For Docker deployment, run schema migrations once during deployment before
starting API and worker services. Fresh Postgres installs should not rely on
multiple services racing to migrate on boot.
  -> Postgres and Redis are internal only
  -> external send remains disabled
  -> connector setup follows Feishu/WeCom guides later
```

Real Feishu/WeCom external sending should remain off until receive and mock send
acceptance pass on the server.
