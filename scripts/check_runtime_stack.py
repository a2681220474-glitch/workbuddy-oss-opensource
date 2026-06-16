from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.core.config import get_settings
from apps.api.shared.runtime_status import runtime_stack_snapshot


def main() -> int:
    args = parse_args()
    snapshot = running_snapshot(args.api_base) or runtime_stack_snapshot(get_settings())
    database = snapshot["database"]
    redis = snapshot["redis"]
    background = snapshot["background_jobs"]
    logs = snapshot["logs"]
    deployment = snapshot["deployment"]

    print(f"Runtime status: {snapshot['status']}")
    print(
        f"Database: {database['label']} [{database['status']}] "
        f"persistence={database['persistence']} url={database['url_masked']}"
    )
    if database.get("advice"):
        print(f"  advice: {database['advice']}")
    if database.get("error"):
        print(f"  error: {database['error']}")

    print(
        f"Redis: {'configured' if redis['configured'] else 'not_configured'} "
        f"[{redis['status']}] url={redis.get('url_masked') or '-'}"
    )
    if redis.get("advice"):
        print(f"  advice: {redis['advice']}")
    if redis.get("error"):
        print(f"  error: {redis['error']}")

    print(
        f"Background jobs: {'enabled' if background['enabled'] else 'disabled'} "
        f"driver={background['queue_driver']} ready={background['ready']}"
    )
    print(f"  scheduled: {', '.join(background['scheduled_jobs'])}")
    worker = background.get("worker") or {}
    print(
        f"  worker: {'running' if worker.get('running') else 'stopped'} "
        f"health={worker.get('health_level', '-')}"
    )
    if worker.get("health_message"):
        print(f"  worker_advice: {worker['health_message']}")
    print(f"Logs: {'ready' if logs.get('ready') else 'not_ready'} dir={logs.get('log_dir')}")
    print(f"  command: {logs.get('tail_command')}")
    print(f"Deployment mode: {deployment['mode']}")
    print(f"Compose up: {deployment['compose_up_command']}")

    failed = []
    if not database["connected"]:
        failed.append("database")
    if background["enabled"] and not background["ready"]:
        failed.append("background_jobs")
    if failed:
        print(f"Blocking runtime issues: {', '.join(failed)}")
        return 1
    print("Runtime stack check passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the active WorkBuddy runtime stack.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    return parser.parse_args()


def running_snapshot(api_base: str) -> dict | None:
    try:
        with urlopen(f"{api_base.rstrip('/')}/health", timeout=2) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError):
        return None
    required = {"status", "database", "redis", "background_jobs", "logs"}
    if not required.issubset(payload):
        return None
    payload.setdefault("deployment", runtime_stack_snapshot(get_settings())["deployment"])
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
