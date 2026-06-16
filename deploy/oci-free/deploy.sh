#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
COMPOSE_FILE="${ROOT_DIR}/deploy/oci-free/docker-compose.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy deploy/oci-free/.env.production.example first." >&2
  exit 1
fi

if grep -q "change-me-long-random-password" "${ENV_FILE}"; then
  echo "POSTGRES_PASSWORD still uses the example value. Set a long random password first." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
else
  COMPOSE=(docker-compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
fi

"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d postgres redis
"${COMPOSE[@]}" run --rm api python scripts/run_migrations.py
"${COMPOSE[@]}" up -d api web runtime-jobs caddy
"${COMPOSE[@]}" ps

echo "Deployment started. Check health with:"
DOMAIN="$(grep '^WORKBUDDY_DOMAIN=' "${ENV_FILE}" | cut -d= -f2)"
if [[ "${DOMAIN}" == ":80" ]]; then
  echo "  bash deploy/oci-free/check_remote.sh http://<server-public-ip>"
else
  echo "  bash deploy/oci-free/check_remote.sh https://${DOMAIN}"
fi
