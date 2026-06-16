from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD = "ReleaseGapAudit#2026"


def main() -> int:
    original_cwd = Path.cwd()
    checks: list[tuple[str, bool, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="workbuddy-release-gap-") as temp_dir:
            temp_root = Path(temp_dir)
            configure_isolated_runtime(temp_root)
            os.chdir(temp_root)
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            from fastapi.testclient import TestClient

            from apps.api.main import app
            from apps.api.version import APP_VERSION
            from scripts.check_release_candidate import release_docs_present

            with TestClient(app) as client:
                bootstrap = client.post(
                    "/api/auth/bootstrap",
                    json={
                        "username": "release_admin",
                        "display_name": "发布审计管理员",
                        "password": ADMIN_PASSWORD,
                    },
                )
                if bootstrap.status_code != 200:
                    raise RuntimeError(f"bootstrap returned {bootstrap.status_code}: {bootstrap.text[:500]}")
                response = client.get("/api/config/status")
                if response.status_code != 200:
                    raise RuntimeError(f"config status returned {response.status_code}: {response.text[:500]}")
                audit = response.json().get("release_audit") or {}

                record(checks, "version", audit.get("version") == APP_VERSION, f"Audit reports v{APP_VERSION}.")
                baselines = audit.get("baselines") or []
                record(checks, "nine_baselines", len(baselines) == 9, "All nine post-v1.0.9 baselines are represented.")
                summary = audit.get("summary") or {}
                record(
                    checks,
                    "status_classification",
                    summary.get("completed") == 9
                    and summary.get("manual_required") == 0
                    and summary.get("deployment_required") == 0
                    and summary.get("local_gaps") == 0,
                    "Completed, manual, deployment, and local-gap counts remain explicit.",
                )
                record(
                    checks,
                    "local_boundary",
                    audit.get("local_code_ready") is True and audit.get("formal_private_use_ready") is True,
                    "Local code and formal private deployment readiness are both complete.",
                )
                stop = audit.get("stop_development") or {}
                record(
                    checks,
                    "phase_one",
                    (stop.get("phase_one") or {}).get("local_code_ready") is True
                    and (stop.get("phase_one") or {}).get("status") == "ready",
                    "Phase one is complete and feature expansion remains stopped.",
                )
                record(
                    checks,
                    "phase_two",
                    (stop.get("phase_two") or {}).get("status") == "observation_required",
                    "Phase two still requires two weeks of real-team observation and user confirmation.",
                )
                evidence = audit.get("connector_evidence") or {}
                record(
                    checks,
                    "connector_safety",
                    evidence.get("new_real_validation_completed") is True
                    and evidence.get("new_real_validation_requires_authorization") is False
                    and evidence.get("validated_at") == "2026-06-15",
                    "The audit records the user-confirmed real Feishu acceptance.",
                )
                runtime_boundary = audit.get("runtime_boundary") or {}
                record(
                    checks,
                    "remote_ecs_acceptance",
                    runtime_boundary.get("remote_ecs_deployed_version") == "1.1.14",
                    "The controlled ECS rollout is recorded as completed.",
                )
                deployment_evidence = audit.get("deployment_evidence") or {}
                record(
                    checks,
                    "postgres_restore_drill",
                    deployment_evidence.get("postgres_restore_drill_completed") is True
                    and deployment_evidence.get("temporary_database_removed") is True
                    and deployment_evidence.get("restored_public_tables") == 24,
                    "The PostgreSQL isolated restore drill and cleanup evidence are recorded.",
                )
                record(
                    checks,
                    "rc_version_support",
                    release_docs_present(APP_VERSION),
                    "Release-candidate continuity supports the current v1.1.x line.",
                )
                closure = audit.get("formal_closure") or {}
                record(
                    checks,
                    "formal_closure",
                    closure.get("status") == "local_formal_closure_ready"
                    and closure.get("aggregate_check_command") == "npm run check:formal-release",
                    "Audit exposes the local formal closure boundary and aggregate command.",
                )
                record(
                    checks,
                    "isolated_artifacts",
                    (temp_root / "release-gap.db").exists() and not (ROOT / "release-gap.db").exists(),
                    "Audit acceptance leaves real local data and secrets untouched.",
                )
    except Exception as exc:
        print(f"[fatal] release_gap_audit: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_cwd)

    failed = [item for item in checks if not item[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} release gap audit check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nRelease gap audit checks passed ({len(checks)} checks).")
    return 0


def configure_isolated_runtime(temp_root: Path) -> None:
    os.environ.update(
        {
            "WORKBUDDY_ENVIRONMENT": "local",
            "WORKBUDDY_DATABASE_URL": f"sqlite:///{temp_root / 'release-gap.db'}",
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


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
