from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from apps.api.main import app
from scripts import check_deployment, check_private_deployment, check_release_readiness


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    version = root_version()

    results.append(("release_readiness", check_release_readiness.main() == 0, "Required release docs and metadata are present."))
    results.append(("deployment_static", check_deployment.main() == 0, "Static deployment readiness passes with Docker warning allowed."))
    results.append(("private_deployment", check_private_deployment.main() == 0, "OCI private deployment files are present and not exposing DB/Redis."))
    results.append(("health_version", health_version() == version, f"/health version should be {version}."))
    results.append(("release_docs", release_docs_present(version), "Release docs exist for v0.20.0 through current version."))
    results.append(("known_issues", (ROOT / "docs/KNOWN_ISSUES.md").exists(), "Known issues document exists."))

    print("")
    for name, ok, detail in results:
        print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")

    failed = [name for name, ok, _ in results if not ok]
    if failed:
        print(f"Release candidate check failed: {', '.join(failed)}")
        return 1
    print("Release candidate check passed.")
    return 0


def root_version() -> str:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    return str(package["version"])


def health_version() -> str:
    client = TestClient(app)
    return str(client.get("/health").json().get("version") or "")


def release_docs_present(current_version: str) -> bool:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current_version)
    if not match:
        return False
    major, minor, patch = (int(value) for value in match.groups())
    if major == 0 and minor == 20:
        expected = [f"v0.20.{number}" for number in range(patch + 1)]
    elif major == 1:
        expected = [f"v1.0.{number}" for number in range(10)]
        for current_minor in range(1, minor + 1):
            last_patch = patch if current_minor == minor else latest_release_patch(major, current_minor)
            if last_patch < 0:
                return False
            expected.extend(f"v1.{current_minor}.{number}" for number in range(last_patch + 1))
    else:
        expected = [f"v{current_version}"]
    for version in expected:
        if not (ROOT / f"docs/release/{version}.md").exists():
            return False
    return True


def latest_release_patch(major: int, minor: int) -> int:
    pattern = re.compile(rf"v{major}\.{minor}\.(\d+)\.md$")
    patches = [
        int(match.group(1))
        for path in (ROOT / "docs/release").glob(f"v{major}.{minor}.*.md")
        if (match := pattern.fullmatch(path.name))
    ]
    return max(patches, default=-1)


if __name__ == "__main__":
    raise SystemExit(main())
