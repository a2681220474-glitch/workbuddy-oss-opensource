from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.core.config import get_settings
from apps.api.shared.runtime_status import runtime_stack_snapshot


def main() -> int:
    snapshot = runtime_stack_snapshot(get_settings())
    database = snapshot["database"]
    backup = snapshot["backup"]
    background = snapshot["background_jobs"]
    logs = snapshot["logs"]
    deployment = snapshot["deployment"]
    docker_available = shutil.which("docker") is not None
    compose = compose_status()

    checks = [
        ("database_connected", bool(database.get("connected")), database.get("advice") or ""),
        ("backup_ready", bool(backup.get("ready")), backup.get("advice") or ""),
        ("logs_ready", bool(logs.get("ready")), logs.get("advice") or ""),
        (
            "background_jobs_known",
            bool(background.get("scheduled_jobs")),
            "Scheduled jobs are registered in runtime status.",
        ),
        (
            "compose_file_ready",
            compose["ready"],
            compose["message"],
        ),
        (
            "docker_available",
            docker_available,
            "Docker is available." if docker_available else "Docker command is not available on this machine.",
        ),
    ]

    print(f"Deployment mode: {deployment.get('mode')}")
    print(f"Compose command: {deployment.get('compose_up_command')}")
    print(f"Backup command: {backup.get('create_command')}")
    print(f"Log command: {logs.get('tail_command')}")
    print("")
    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'warn'}] {name}: {detail}")

    blocking = [name for name, ok, _ in checks if name in {"database_connected", "backup_ready"} and not ok]
    if blocking:
        print(f"Blocking deployment checks: {', '.join(blocking)}")
        return 1
    print("Deployment readiness check passed with warnings allowed.")
    return 0


def compose_status() -> dict[str, object]:
    compose_file = ROOT / "docker-compose.yml"
    required = {"api", "web", "feishu-worker", "runtime-jobs", "postgres", "redis"}
    if not compose_file.exists():
        return {"ready": False, "message": "docker-compose.yml is missing."}
    content = compose_file.read_text(encoding="utf-8")
    missing = [service for service in sorted(required) if f"  {service}:" not in content]
    if missing:
        return {"ready": False, "message": f"Missing compose services: {', '.join(missing)}"}
    return {"ready": True, "message": "Target compose services are declared."}


if __name__ == "__main__":
    raise SystemExit(main())
