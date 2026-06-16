from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "deploy/oci-free/postgres_restore_drill.sh"
EVIDENCE_PATH = ROOT / "docs/ops/postgres_restore_drill_example.json"


def main() -> int:
    text = SCRIPT_PATH.read_text(encoding="utf-8") if SCRIPT_PATH.exists() else ""
    evidence = EVIDENCE_PATH.read_text(encoding="utf-8") if EVIDENCE_PATH.exists() else ""
    checks = [
        ("script_exists", SCRIPT_PATH.exists(), "PostgreSQL isolated restore drill script exists."),
        (
            "isolated_target_guard",
            "workbuddy_restore_drill_" in text and "Unsafe target database name" in text,
            "Restore targets require the isolated database prefix.",
        ),
        (
            "protected_database_guard",
            'TARGET_DB}" == "${PRODUCTION_DB}' in text and '"template0"' in text and '"template1"' in text,
            "Production and PostgreSQL system databases are protected.",
        ),
        (
            "restore_failure_is_blocking",
            "ON_ERROR_STOP=1" in text and "--exit-on-error" in text,
            "SQL and custom-format restores stop on the first error.",
        ),
        (
            "backup_integrity_evidence",
            "sha256sum" in text and "backup_size_bytes" in text and "backup_sha256" in text,
            "The drill records backup size and SHA-256 evidence.",
        ),
        (
            "business_data_verification",
            "restored_public_tables" in text
            and "restored_messages" in text
            and "restored_approvals" in text
            and "alembic_version" in text,
            "The restored database verifies schema, migrations, messages, and approvals.",
        ),
        (
            "cleanup_trap",
            "trap cleanup EXIT" in text
            and "DROP DATABASE IF EXISTS" in text
            and "temporary_database_removed" in text,
            "The temporary database is removed on success or failure.",
        ),
        (
            "no_secret_output",
            "POSTGRES_PASSWORD" not in text and '"password"' not in text.lower(),
            "The drill never prints or records the PostgreSQL password.",
        ),
        (
            "example_drill_evidence",
            EVIDENCE_PATH.exists()
            and '"ok": true' in evidence
            and '"temporary_database_removed": true' in evidence
            and '"remaining_temporary_databases": 0' in evidence,
            "An example restore drill evidence file is retained for public releases.",
        ),
    ]

    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"PostgreSQL restore drill check failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"PostgreSQL restore drill checks passed ({len(checks)} checks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
