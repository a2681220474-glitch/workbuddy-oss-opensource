#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "${BASE_URL}" ]]; then
  echo "Usage: bash deploy/oci-free/check_remote.sh https://workbuddy.example.com" >&2
  exit 1
fi

BASE_URL="${BASE_URL%/}"
HEALTH_JSON="$(curl -fsS --max-time 15 "${BASE_URL}/health")"
VERSION="$(printf '%s' "${HEALTH_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version", ""))')"

if [[ "${VERSION}" != "1.0.2" ]]; then
  echo "Unexpected health version: ${VERSION}" >&2
  echo "${HEALTH_JSON}" >&2
  exit 1
fi

curl -fsS --max-time 15 "${BASE_URL}/" >/dev/null

echo "Remote WorkBuddy health check passed: ${BASE_URL} version ${VERSION}"
