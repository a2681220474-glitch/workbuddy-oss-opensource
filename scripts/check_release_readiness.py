from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    root_package = read_json(ROOT / "package.json")
    web_package = read_json(ROOT / "apps/web/package.json")
    api_version = read_api_version()
    root_version = str(root_package.get("version", ""))
    web_version = str(web_package.get("version", ""))

    checks.append(("version_sync", root_version == web_version == api_version, f"root={root_version}, web={web_version}, api={api_version}"))
    checks.append(("install_doc", exists("docs/INSTALL.md"), "docs/INSTALL.md is required."))
    checks.append(("release_modes_doc", exists("docs/RELEASE_MODES.md"), "docs/RELEASE_MODES.md is required."))
    checks.append(("feishu_setup_doc", exists("docs/FEISHU_SETUP.md"), "docs/FEISHU_SETUP.md is required."))
    checks.append(("wecom_setup_doc", exists("docs/WECOM_SETUP.md"), "docs/WECOM_SETUP.md is required."))
    checks.append(("deployment_doc", exists("docs/DEPLOYMENT.md"), "docs/DEPLOYMENT.md is required."))
    checks.append(("docker_acceptance_doc", exists("docs/ops/docker_compose_acceptance.md"), "docs/ops/docker_compose_acceptance.md is required."))
    checks.append(("security_doc", exists("SECURITY.md"), "SECURITY.md is required."))
    checks.append(("privacy_security_doc", exists("docs/PRIVACY_SECURITY.md"), "docs/PRIVACY_SECURITY.md is required."))
    checks.append(("release_hygiene_doc", exists("docs/RELEASE_HYGIENE.md"), "docs/RELEASE_HYGIENE.md is required."))
    checks.append(("rc_checklist_doc", exists("docs/RELEASE_CANDIDATE_CHECKLIST.md"), "docs/RELEASE_CANDIDATE_CHECKLIST.md is required."))
    checks.append(("known_issues_doc", exists("docs/KNOWN_ISSUES.md"), "docs/KNOWN_ISSUES.md is required."))
    checks.append(("private_deployment_doc", exists("docs/PRIVATE_DEPLOYMENT.md"), "docs/PRIVATE_DEPLOYMENT.md is required."))
    checks.append(("quickstart_doc", exists("docs/QUICKSTART.md"), "docs/QUICKSTART.md is required."))
    checks.append(("env_example", env_example_safe(), ".env.example should keep secrets blank."))
    checks.append(("gitignore_secrets", gitignore_has_secret_rules(), ".gitignore should ignore local env files and runtime data."))
    checks.append(("license", exists("LICENSE"), "LICENSE is required before public release."))
    checks.append(("contributing", exists("CONTRIBUTING.md"), "CONTRIBUTING.md is required before public release."))

    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"Release readiness failed: {', '.join(failed)}")
        return 1
    print("Release readiness check passed.")
    return 0


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_api_version() -> str:
    content = (ROOT / "apps/api/version.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else ""


def env_example_safe() -> bool:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    secret_keys = [
        "LLM_API_KEY",
        "FEISHU_APP_SECRET",
        "FEISHU_VERIFICATION_TOKEN",
        "FEISHU_ENCRYPT_KEY",
        "WECOM_SECRET",
        "WECOM_TOKEN",
        "WECOM_ENCODING_AES_KEY",
        "DINGTALK_CLIENT_SECRET",
        "DINGTALK_WEBHOOK_SECRET",
    ]
    for key in secret_keys:
        match = re.search(rf"^{re.escape(key)}=(.*)$", content, re.MULTILINE)
        if match and match.group(1).strip():
            return False
    return True


def gitignore_has_secret_rules() -> bool:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required = [
        ".env",
        ".env.local",
        ".env.production",
        "apps/api/.env",
        "apps/api/.env.local",
        "apps/api/data/",
        "generated_documents/",
        "docs/assets/workbuddy_v0.12.0_demo.mp4",
        "scripts/generate_workbuddy_video_ffmpeg.py",
    ]
    return all(rule in content for rule in required)


if __name__ == "__main__":
    raise SystemExit(main())
