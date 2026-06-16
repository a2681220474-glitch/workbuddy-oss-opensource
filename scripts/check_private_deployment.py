from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "deploy/oci-free/README.md",
    "deploy/oci-free/.env.production.example",
    "deploy/oci-free/Caddyfile",
    "deploy/oci-free/api.Dockerfile",
    "deploy/oci-free/web.Dockerfile",
    "deploy/oci-free/web-nginx.conf",
    "deploy/oci-free/docker-compose.yml",
    "deploy/oci-free/bootstrap_ubuntu.sh",
    "deploy/oci-free/deploy.sh",
    "deploy/oci-free/check_remote.sh",
    "deploy/oci-free/postgres_restore_drill.sh",
    ".dockerignore",
]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    for path in REQUIRED_FILES:
        checks.append((f"file:{path}", (ROOT / path).exists(), path))
    checks.append(("dockerignore_env", dockerignore_contains(".env.production"), ".dockerignore excludes production env."))
    checks.append(("compose_no_public_db", not compose_exposes("5432"), "PostgreSQL is not exposed publicly."))
    checks.append(("compose_no_public_redis", not compose_exposes("6379"), "Redis is not exposed publicly."))
    checks.append(("compose_has_caddy", "caddy:" in compose_text(), "Caddy service is present."))
    checks.append(("web_same_origin_api", "VITE_API_BASE_URL: /api" in compose_text(), "Web build uses same-origin /api."))

    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"Private deployment check failed: {', '.join(failed)}")
        return 1
    print("Private deployment check passed.")
    return 0


def compose_text() -> str:
    return (ROOT / "deploy/oci-free/docker-compose.yml").read_text(encoding="utf-8")


def compose_exposes(port: str) -> bool:
    content = compose_text()
    return f'"{port}:{port}"' in content or f"'{port}:{port}'" in content or f"- {port}:{port}" in content


def dockerignore_contains(rule: str) -> bool:
    return rule in (ROOT / ".dockerignore").read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
