# OCI Always Free Deployment

This deployment target is optimized for an Oracle Cloud Infrastructure Always
Free Ampere A1 Ubuntu VM.

Recommended free shape:

- Shape: `VM.Standard.A1.Flex`
- OCPU: 2 to 4
- Memory: 12 GB to 24 GB if available
- OS: Ubuntu 22.04 or 24.04 LTS
- Boot volume: 80 GB+

Availability varies by region. If A1 capacity is temporarily unavailable, try a
different region or retry later.

## Security Model

Only these public ports should be open:

- `22/tcp`: SSH
- `80/tcp`: HTTP for Caddy ACME redirect/challenge
- `443/tcp`: HTTPS

Do not expose:

- API `8000`
- Web dev `5173`
- PostgreSQL `5432`
- Redis `6379`

Caddy terminates HTTPS and proxies:

- `/api/*`, `/health`, `/docs`, `/openapi.json` -> `api:8000`
- everything else -> static web container

## 1. Bootstrap Ubuntu

Copy this directory and the repository to the server, then run:

```bash
sudo bash deploy/oci-free/bootstrap_ubuntu.sh
```

The script installs Docker, Docker Compose plugin, UFW, and fail2ban, then opens
only SSH/HTTP/HTTPS.

## 2. Configure Environment

```bash
cp deploy/oci-free/.env.production.example .env.production
```

Edit:

- `WORKBUDDY_DOMAIN`
- `CADDY_ACME_EMAIL`
- `POSTGRES_PASSWORD`
- connector secrets only if needed

Keep `ENABLE_EXTERNAL_SEND=false` for the first deployment acceptance pass.

If you do not have a domain yet, use a temporary HTTP-only value:

```env
WORKBUDDY_DOMAIN=:80
CORS_ORIGINS=http://<server-public-ip>
```

After a domain is ready, change `WORKBUDDY_DOMAIN` to the domain name, change
`CORS_ORIGINS` to `https://<domain>`, and redeploy. Caddy will then issue HTTPS
certificates automatically.

## 3. Deploy

```bash
bash deploy/oci-free/deploy.sh
```

## 4. Verify

```bash
bash deploy/oci-free/check_remote.sh https://<your-domain>
```

Manual checks:

1. Open `https://<your-domain>`.
2. Open `https://<your-domain>/health`.
3. Confirm `/health` reports version `1.0.2`.

This deploy target runs database migrations once during `deploy.sh` before the
API and worker services start. That avoids migration races on fresh Postgres
instances.
4. Keep real IM sending disabled until connector acceptance passes.

## Notes

- Real deployment needs an Oracle account and an SSH key.
- A domain is strongly recommended for HTTPS. Caddy can also serve HTTP by IP
  for temporary smoke checks, but Feishu/WeCom callbacks should use stable
  HTTPS domains.
- Use Oracle security lists or network security groups to allow only ports
  `22`, `80`, and `443`.
