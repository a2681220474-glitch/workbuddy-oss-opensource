from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.1.16"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local WorkBuddy acceptance checks without mutating local data.")
    parser.add_argument("--api-base", default="http://localhost:8000", help="Local API base URL.")
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("favicon", (ROOT / "apps/web/public/favicon.svg").exists(), "Browser tab favicon exists."))
    checks.append(("web_index_favicon", 'href="/favicon.svg"' in read_text("apps/web/index.html"), "Web index references favicon."))
    checks.append(
        (
            "current_release_doc",
            (ROOT / f"docs/release/v{EXPECTED_VERSION}.md").exists(),
            f"v{EXPECTED_VERSION} release doc exists.",
        )
    )
    checks.append(
        (
            "handoff_version",
            f"v{EXPECTED_VERSION}" in read_text("docs/HANDOFF_NEXT_CHAT.md"),
            f"Handoff records v{EXPECTED_VERSION}.",
        )
    )

    health = get_json(f"{args.api_base.rstrip('/')}/health")
    checks.append(("api_health_reachable", health is not None, "Local API health endpoint is reachable."))
    if health is not None:
        checks.append(("api_version", health.get("version") == EXPECTED_VERSION, f"API reports version {EXPECTED_VERSION}."))
        checks.append(("database_connected", bool((health.get("database") or {}).get("connected")), "Database is connected."))

    bootstrap = get_json(f"{args.api_base.rstrip('/')}/api/auth/bootstrap-status")
    checks.append(("auth_bootstrap_status", bootstrap is not None, "Auth bootstrap status endpoint is reachable."))
    if bootstrap is not None:
        checks.append(("auth_bootstrap_shape", "needs_bootstrap" in bootstrap, "Auth bootstrap response has expected shape."))

    failed = [item for item in checks if not item[1]]
    for name, ok, message in checks:
        status = "ok" if ok else "fail"
        print(f"[{status}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} local acceptance check(s) failed.", file=sys.stderr)
        return 1
    print("\nLocal acceptance checks passed.")
    return 0


def read_text(path: str) -> str:
    full_path = ROOT / path
    return full_path.read_text(encoding="utf-8") if full_path.exists() else ""


def get_json(url: str) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return get_json_with_test_client(url)


def get_json_with_test_client(url: str) -> dict[str, object] | None:
    try:
        from fastapi.testclient import TestClient

        from apps.api.main import app

        path = "/" + url.split("://", 1)[-1].split("/", 1)[-1]
        with TestClient(app) as client:
            response = client.get(path)
        if response.status_code >= 400:
            return None
        return response.json()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
