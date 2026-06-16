from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD = "FormalClosure#2026"


def main() -> int:
    original_cwd = Path.cwd()
    checks: list[tuple[str, bool, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="workbuddy-formal-closure-") as temp_dir:
            temp_root = Path(temp_dir)
            configure_isolated_runtime(temp_root)
            os.chdir(temp_root)
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            from fastapi.testclient import TestClient

            from apps.api.main import app
            from apps.api.version import APP_VERSION

            with TestClient(app) as client:
                bootstrap = client.post(
                    "/api/auth/bootstrap",
                    json={
                        "username": "closure_admin",
                        "display_name": "正式收口管理员",
                        "password": ADMIN_PASSWORD,
                    },
                )
                if bootstrap.status_code != 200:
                    raise RuntimeError(f"bootstrap returned {bootstrap.status_code}: {bootstrap.text[:500]}")

                status = client.get("/api/config/status")
                if status.status_code != 200:
                    raise RuntimeError(f"config status returned {status.status_code}: {status.text[:500]}")
                audit = status.json().get("release_audit") or {}
                closure = audit.get("formal_closure") or {}
                boundary = closure.get("maintenance_boundary") or {}

                package_json = read_json(ROOT / "package.json")
                scripts = package_json.get("scripts") or {}
                release_doc = read_text(ROOT / f"docs/release/v{APP_VERSION}.md")
                rc = read_text(ROOT / "docs/RELEASE_CANDIDATE_CHECKLIST.md")

                package_version = str(package_json.get("version") or "")
                record(
                    checks,
                    "version",
                    APP_VERSION == package_version,
                    f"Formal closure version matches package metadata at v{APP_VERSION}.",
                )
                record(
                    checks,
                    "local_closure_status",
                    audit.get("local_code_ready") is True
                    and closure.get("status") == "local_formal_closure_ready",
                    "Local code readiness exposes a formal closure status.",
                )
                record(
                    checks,
                    "aggregate_script",
                    scripts.get("check:formal-closure") == ".venv/bin/python scripts/check_formal_closure.py"
                    and "check:formal-release" in scripts
                    and "check:release-gap-audit" in scripts.get("check:formal-release", "")
                    and "check:connector-acceptance" in scripts.get("check:formal-release", ""),
                    "Package scripts expose formal closure and aggregate release checks.",
                )
                record(
                    checks,
                    "maintenance_allowed",
                    {"P0/P1 缺陷修复", "安全、权限、密钥和审计修复"}.issubset(
                        set(boundary.get("allowed_changes") or [])
                    ),
                    "Maintenance boundary lists the allowed repair categories.",
                )
                record(
                    checks,
                    "maintenance_blocked",
                    {"新增大业务模块", "未授权真实外发", "未授权远程 ECS 滚动升级"}.issubset(
                        set(boundary.get("blocked_changes") or [])
                    ),
                    "Maintenance boundary freezes large scope and unauthorized production actions.",
                )
                record(
                    checks,
                    "authorization_boundary",
                    len(boundary.get("requires_authorization") or []) >= 1
                    and audit.get("connector_evidence", {}).get("new_real_validation_completed") is True,
                    "Acceptance is complete while future ECS upgrades remain authorization-gated.",
                )
                record(
                    checks,
                    "release_doc",
                    "本地正式收口" in release_doc
                    and "npm run check:formal-release" in release_doc
                    and "远程 ECS 后续不随每个小版本自动升级" in release_doc
                    and "真实外发仍需用户明确授权" in release_doc,
                    "Release doc records scope, aggregate command, and controlled remote rollout boundary.",
                )
                record(
                    checks,
                    "release_boundary",
                    f"v{APP_VERSION}" in release_doc
                    and "npm run check:formal-release" in release_doc
                    and "真实外发仍需用户明确授权" in release_doc,
                    "Release doc records the formal closure boundary.",
                )
                record(
                    checks,
                    "rc_checklist",
                    "npm run check:formal-release" in rc
                    and "check:formal-closure" in rc
                    and "Release Boundary" in rc,
                    "RC checklist points operators to the aggregate command.",
                )
                record(
                    checks,
                    "isolated_artifacts",
                    (temp_root / "formal-closure.db").exists()
                    and not (ROOT / "formal-closure.db").exists(),
                    "Formal closure acceptance leaves real local data and secrets untouched.",
                )
    except Exception as exc:
        print(f"[fatal] formal_closure: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_cwd)

    failed = [item for item in checks if not item[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} formal closure check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nFormal closure checks passed ({len(checks)} checks).")
    return 0


def configure_isolated_runtime(temp_root: Path) -> None:
    os.environ.update(
        {
            "WORKBUDDY_ENVIRONMENT": "local",
            "WORKBUDDY_DATABASE_URL": f"sqlite:///{temp_root / 'formal-closure.db'}",
            "WORKBUDDY_AUTH_SECRET_PATH": str(temp_root / "auth-secret.txt"),
            "WORKBUDDY_SECRET_STORE_PATH": str(temp_root / "runtime-secrets.json"),
            "WORKBUDDY_SECRET_KEY_PATH": str(temp_root / "runtime-secret.key"),
            "WORKBUDDY_FEISHU_STREAM_STATUS_PATH": str(temp_root / "feishu-status.json"),
            "WORKBUDDY_BACKGROUND_JOBS_STATUS_PATH": str(temp_root / "runtime-jobs-status.json"),
            "WORKBUDDY_ENABLE_EXTERNAL_SEND": "false",
            "WORKBUDDY_ENABLE_BACKGROUND_JOBS": "false",
            "WORKBUDDY_LLM_PROVIDER": "mock",
            "WORKBUDDY_LLM_API_KEY": "",
        }
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
