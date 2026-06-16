#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
COMPOSE_FILE="${ROOT_DIR}/deploy/oci-free/docker-compose.yml"
BACKUP_PATH="${1:-}"
TARGET_DB="${2:-workbuddy_restore_drill_$(date +%Y%m%d_%H%M%S)}"
EVIDENCE_PATH="${3:-}"

if [[ -z "${BACKUP_PATH}" ]]; then
  echo "Usage: bash deploy/oci-free/postgres_restore_drill.sh <backup.sql|backup.dump> [target_db] [evidence.json]" >&2
  exit 2
fi

if [[ ! "${TARGET_DB}" =~ ^workbuddy_restore_drill_[a-zA-Z0-9_]+$ ]]; then
  echo "Unsafe target database name: ${TARGET_DB}" >&2
  echo "The target must start with workbuddy_restore_drill_." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

if [[ ! -f "${BACKUP_PATH}" ]]; then
  echo "Backup artifact not found: ${BACKUP_PATH}" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
else
  COMPOSE=(docker-compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
fi

postgres_exec() {
  "${COMPOSE[@]}" exec -T postgres "$@"
}

POSTGRES_USER_NAME="$(postgres_exec sh -lc 'printf "%s" "$POSTGRES_USER"')"

postgres_psql() {
  local database="$1"
  shift
  postgres_exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER_NAME}" -d "${database}" "$@"
}

PRODUCTION_DB="$(postgres_exec sh -lc 'printf "%s" "$POSTGRES_DB"')"
if [[ "${TARGET_DB}" == "${PRODUCTION_DB}" || "${TARGET_DB}" == "postgres" || "${TARGET_DB}" == "template0" || "${TARGET_DB}" == "template1" ]]; then
  echo "Refusing to restore into protected database: ${TARGET_DB}" >&2
  exit 1
fi

TARGET_CREATED=false
cleanup() {
  if [[ "${TARGET_CREATED}" == "true" ]]; then
    postgres_psql postgres -c "DROP DATABASE IF EXISTS \"${TARGET_DB}\" WITH (FORCE);" >/dev/null
  fi
}
trap cleanup EXIT

if postgres_psql postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}'" | grep -q 1; then
  echo "Target database already exists: ${TARGET_DB}" >&2
  exit 1
fi

BACKUP_SIZE="$(wc -c < "${BACKUP_PATH}" | tr -d ' ')"
BACKUP_SHA256="$(sha256sum "${BACKUP_PATH}" | awk '{print $1}')"
if [[ "${BACKUP_SIZE}" -le 0 ]]; then
  echo "Backup artifact is empty: ${BACKUP_PATH}" >&2
  exit 1
fi

postgres_psql postgres -c "CREATE DATABASE \"${TARGET_DB}\" TEMPLATE template0;" >/dev/null
TARGET_CREATED=true

case "${BACKUP_PATH}" in
  *.sql)
    postgres_exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER_NAME}" -d "${TARGET_DB}" < "${BACKUP_PATH}" >/dev/null
    ;;
  *.dump)
    postgres_exec pg_restore --exit-on-error --no-owner --no-privileges -U "${POSTGRES_USER_NAME}" -d "${TARGET_DB}" < "${BACKUP_PATH}" >/dev/null
    ;;
  *)
    echo "Unsupported backup format: ${BACKUP_PATH}" >&2
    exit 1
    ;;
esac

TABLE_COUNT="$(postgres_psql "${TARGET_DB}" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")"
MESSAGE_COUNT="$(postgres_psql "${TARGET_DB}" -Atc "SELECT count(*) FROM messages;")"
APPROVAL_COUNT="$(postgres_psql "${TARGET_DB}" -Atc "SELECT count(*) FROM approvals;")"
ALEMBIC_VERSION="$(postgres_psql "${TARGET_DB}" -Atc "SELECT version_num FROM alembic_version LIMIT 1;")"

if [[ "${TABLE_COUNT}" -le 0 ]]; then
  echo "Restore verification failed: no public tables found." >&2
  exit 1
fi

cleanup
TARGET_CREATED=false

TARGET_EXISTS_AFTER_CLEANUP="$(postgres_psql postgres -Atc "SELECT count(*) FROM pg_database WHERE datname = '${TARGET_DB}';")"
if [[ "${TARGET_EXISTS_AFTER_CLEANUP}" != "0" ]]; then
  echo "Cleanup verification failed: ${TARGET_DB} still exists." >&2
  exit 1
fi

RESULT="$(
  cat <<EOF
{
  "ok": true,
  "backend": "postgresql",
  "mode": "isolated_restore_drill",
  "completed_at": "$(date -Iseconds)",
  "production_database_untouched": "${PRODUCTION_DB}",
  "temporary_database": "${TARGET_DB}",
  "backup_path": "${BACKUP_PATH}",
  "backup_size_bytes": ${BACKUP_SIZE},
  "backup_sha256": "${BACKUP_SHA256}",
  "restored_public_tables": ${TABLE_COUNT},
  "restored_messages": ${MESSAGE_COUNT},
  "restored_approvals": ${APPROVAL_COUNT},
  "alembic_version": "${ALEMBIC_VERSION}",
  "temporary_database_removed": true
}
EOF
)"

if [[ -n "${EVIDENCE_PATH}" ]]; then
  mkdir -p "$(dirname "${EVIDENCE_PATH}")"
  printf '%s\n' "${RESULT}" > "${EVIDENCE_PATH}"
  chmod 600 "${EVIDENCE_PATH}"
fi

printf '%s\n' "${RESULT}"
