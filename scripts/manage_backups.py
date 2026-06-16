from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.core.config import get_settings

DEFAULT_BACKUP_DIR = ROOT / "apps" / "api" / "data" / "backups"


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = args.database_url or settings.database_url
    backup_dir = Path(args.backup_dir or DEFAULT_BACKUP_DIR)
    backend = database_backend(database_url)

    if args.command == "create":
        if backend == "sqlite":
            result = create_sqlite_backup(database_url, backup_dir)
        elif backend == "postgresql":
            result = create_postgres_backup(database_url, backup_dir)
        else:
            raise SystemExit(f"Unsupported database backend for backup: {backend}")
        print_json(result)
        return 0

    if args.command == "verify":
        result = verify_backup(Path(args.backup_path))
        print_json(result)
        return 0 if result["ok"] else 1

    if args.command == "restore-plan":
        result = restore_plan(database_url, Path(args.backup_path), backup_dir)
        print_json(result)
        return 0

    if args.command == "restore-sqlite":
        if backend != "sqlite":
            raise SystemExit("restore-sqlite only supports sqlite database URLs.")
        if not args.confirm:
            raise SystemExit("Refusing to restore without --confirm. Run restore-plan first.")
        result = restore_sqlite_backup(database_url, Path(args.backup_path), backup_dir)
        print_json(result)
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create, verify, and plan WorkBuddy database backups.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL. Defaults to runtime config.")
    parser.add_argument("--backup-dir", default="", help="Backup directory. Defaults to apps/api/data/backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("create", help="Create a database backup.")

    verify = subparsers.add_parser("verify", help="Verify a backup artifact.")
    verify.add_argument("backup_path", help="Path to .db, .sql, .dump, or metadata JSON.")

    plan = subparsers.add_parser("restore-plan", help="Print a restore plan without changing data.")
    plan.add_argument("backup_path", help="Path to backup artifact.")

    restore = subparsers.add_parser("restore-sqlite", help="Restore a SQLite backup. Requires --confirm.")
    restore.add_argument("backup_path", help="Path to SQLite backup artifact.")
    restore.add_argument("--confirm", action="store_true", help="Actually replace the configured SQLite database.")
    return parser.parse_args()


def create_sqlite_backup(database_url: str, backup_dir: Path) -> dict[str, object]:
    source = sqlite_path_from_url(database_url)
    if not source.exists():
        raise SystemExit(f"SQLite database does not exist: {source}")
    timestamp = timestamp_label()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"workbuddy-sqlite-{timestamp}.db"
    metadata_path = backup_dir / f"workbuddy-sqlite-{timestamp}.json"

    source_connection = sqlite3.connect(source)
    try:
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
    finally:
        source_connection.close()

    verified = verify_sqlite_backup(target)
    metadata = {
        "ok": True,
        "backend": "sqlite",
        "created_at": now_iso(),
        "source": str(source),
        "backup_path": str(target),
        "metadata_path": str(metadata_path),
        "size_bytes": target.stat().st_size,
        "verification": verified,
        "restore_command": f"npm run backup:restore:sqlite -- {target} --confirm",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def create_postgres_backup(database_url: str, backup_dir: Path) -> dict[str, object]:
    if shutil.which("pg_dump") is None:
        return {
            "ok": False,
            "backend": "postgresql",
            "created_at": now_iso(),
            "reason": "pg_dump is not installed in this runtime.",
            "install_hint": "Install PostgreSQL client tools or run inside the postgres container.",
            "suggested_command": "pg_dump --format=custom --file apps/api/data/backups/workbuddy-postgres-<timestamp>.dump \"$DATABASE_URL\"",
        }
    timestamp = timestamp_label()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"workbuddy-postgres-{timestamp}.dump"
    env = os.environ.copy()
    command = ["pg_dump", "--format=custom", "--file", str(target), database_url]
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return {
            "ok": False,
            "backend": "postgresql",
            "created_at": now_iso(),
            "backup_path": str(target),
            "error": completed.stderr.strip() or completed.stdout.strip(),
        }
    metadata = {
        "ok": True,
        "backend": "postgresql",
        "created_at": now_iso(),
        "backup_path": str(target),
        "size_bytes": target.stat().st_size,
        "restore_command": f"pg_restore --clean --if-exists --dbname \"$DATABASE_URL\" {target}",
    }
    metadata_path = backup_dir / f"workbuddy-postgres-{timestamp}.json"
    metadata["metadata_path"] = str(metadata_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def verify_backup(path: Path) -> dict[str, object]:
    backup_path = resolve_backup_path(path)
    if not backup_path.exists():
        return {"ok": False, "backup_path": str(backup_path), "reason": "Backup artifact not found."}
    if backup_path.suffix == ".json":
        metadata = json.loads(backup_path.read_text(encoding="utf-8"))
        nested = metadata.get("backup_path")
        if nested:
            return verify_backup(Path(str(nested)))
        return {"ok": True, "backup_path": str(backup_path), "metadata": metadata}
    if backup_path.suffix == ".db":
        return verify_sqlite_backup(backup_path)
    if backup_path.suffix in {".dump", ".sql"}:
        return {
            "ok": backup_path.stat().st_size > 0,
            "backend": "postgresql",
            "backup_path": str(backup_path),
            "size_bytes": backup_path.stat().st_size,
            "verification": "size_only",
        }
    return {"ok": False, "backup_path": str(backup_path), "reason": "Unknown backup artifact type."}


def verify_sqlite_backup(path: Path) -> dict[str, object]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            table_count = connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            message_count = safe_count(connection, "messages")
            approval_count = safe_count(connection, "approvals")
        finally:
            connection.close()
    except Exception as exc:  # noqa: BLE001 - backup verification should return diagnostics.
        return {"ok": False, "backend": "sqlite", "backup_path": str(path), "error": str(exc)}
    return {
        "ok": integrity == "ok",
        "backend": "sqlite",
        "backup_path": str(path),
        "integrity": integrity,
        "table_count": table_count,
        "message_count": message_count,
        "approval_count": approval_count,
        "size_bytes": path.stat().st_size,
    }


def restore_plan(database_url: str, backup_path: Path, backup_dir: Path) -> dict[str, object]:
    backend = database_backend(database_url)
    target = sqlite_path_from_url(database_url) if backend == "sqlite" else database_url
    return {
        "ok": True,
        "backend": backend,
        "target": str(target),
        "backup_path": str(resolve_backup_path(backup_path)),
        "pre_restore_backup_dir": str(backup_dir),
        "steps": restore_steps(backend, backup_path),
    }


def restore_sqlite_backup(database_url: str, backup_path: Path, backup_dir: Path) -> dict[str, object]:
    source = resolve_backup_path(backup_path)
    verification = verify_sqlite_backup(source)
    if not verification.get("ok"):
        raise SystemExit(f"Backup verification failed: {verification}")
    target = sqlite_path_from_url(database_url)
    if not target.exists():
        raise SystemExit(f"Configured SQLite database does not exist: {target}")
    pre_restore = create_sqlite_backup(database_url, backup_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "ok": True,
        "backend": "sqlite",
        "restored_at": now_iso(),
        "target": str(target),
        "restored_from": str(source),
        "pre_restore_backup": pre_restore,
        "verification": verify_sqlite_backup(target),
    }


def restore_steps(backend: str, backup_path: Path) -> list[str]:
    if backend == "sqlite":
        return [
            "Stop API, web workers, Feishu worker, and runtime-jobs before restore.",
            f"Run: npm run backup:restore:sqlite -- {resolve_backup_path(backup_path)} --confirm",
            "Restart API and workers.",
            "Run: npm run check:runtime-stack and the relevant IM acceptance checks.",
        ]
    if backend == "postgresql":
        return [
            "Stop API, workers, and scheduled jobs before restore.",
            "Create a fresh pre-restore pg_dump.",
            f"Run: pg_restore --clean --if-exists --dbname \"$DATABASE_URL\" {resolve_backup_path(backup_path)}",
            "Run: npm run db:migrate.",
            "Restart API and workers.",
        ]
    return ["Unsupported backend. Create a manual restore runbook before changing data."]


def safe_count(connection: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None


def resolve_backup_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def database_backend(database_url: str) -> str:
    prefix = database_url.split(":", 1)[0].lower()
    if prefix.startswith("postgresql"):
        return "postgresql"
    if prefix.startswith("sqlite"):
        return "sqlite"
    return prefix or "unknown"


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite"):
        raise SystemExit(f"Not a SQLite URL: {database_url}")
    parsed = urlparse(database_url)
    raw_path = parsed.path or database_url.replace("sqlite:///", "", 1)
    if raw_path.startswith("/") and database_url.startswith("sqlite:///./"):
        raw_path = database_url.replace("sqlite:///", "", 1)
    if raw_path.startswith("/./"):
        raw_path = raw_path[1:]
    path = Path(raw_path)
    return path if path.is_absolute() else ROOT / path


def timestamp_label() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
