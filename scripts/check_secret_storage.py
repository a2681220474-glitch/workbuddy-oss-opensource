from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.modules.config_center.secret_store import (  # noqa: E402
    load_encrypted_secrets,
    migrate_plaintext_secrets,
    rotate_master_key,
    save_encrypted_secrets,
    secret_storage_status,
)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="workbuddy-secret-check-") as temp_dir:
        root = Path(temp_dir)
        env_path = root / ".env.local"
        store_path = root / "runtime_secrets.json"
        key_path = root / "runtime_secret.key"
        env_path.write_text(
            'LLM_PROVIDER=deepseek\nOPENAI_API_KEY="mock-llm-api-key"\nWORKBUDDY_WECOM_SECRET=mock-wecom-secret\n',
            encoding="utf-8",
        )

        before = secret_storage_status(env_path, store_path, key_path)
        checks.append(("detect_plaintext", before["plaintext_key_count"] == 2, "Plaintext secret keys are detected."))

        migration = migrate_plaintext_secrets(env_path, store_path, key_path)
        decrypted = load_encrypted_secrets(store_path, key_path)
        checks.append(("migration_count", len(migration["migrated_keys"]) == 2, "Both plaintext secrets were migrated."))
        checks.append(("decrypt_values", decrypted["LLM_API_KEY"] == "mock-llm-api-key", "Quoted dotenv values preserve their runtime value."))
        checks.append(("env_sanitized", "temporary-" not in env_path.read_text(encoding="utf-8"), "Runtime env no longer contains secret values."))
        checks.append(("backup_sanitized", "temporary-" not in Path(str(migration["backup_path"])).read_text(encoding="utf-8"), "Migration backup contains no secret values."))
        checks.append(("ciphertext_only", "temporary-" not in store_path.read_text(encoding="utf-8"), "Secret store contains ciphertext only."))

        save_encrypted_secrets({"DINGTALK_CLIENT_SECRET": "mock-dingtalk-secret"}, store_path, key_path)
        rotation = rotate_master_key(store_path, key_path)
        after_rotation = load_encrypted_secrets(store_path, key_path)
        checks.append(("rotation_count", len(rotation["rotated_keys"]) == 3, "All encrypted secrets were rotated."))
        checks.append(("rotation_readable", after_rotation["DINGTALK_CLIENT_SECRET"] == "mock-dingtalk-secret", "Rotated store remains readable."))
        checks.append(("private_key_mode", oct(key_path.stat().st_mode & 0o777) == "0o600", "Master key permissions are 0600."))
        checks.append(("private_store_mode", oct(store_path.stat().st_mode & 0o777) == "0o600", "Ciphertext store permissions are 0600."))

        payload = json.loads(store_path.read_text(encoding="utf-8"))
        checks.append(("store_format", payload.get("version") == 1 and payload.get("algorithm") == "fernet", "Store format is versioned."))

    failed = [check for check in checks if not check[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} secret storage check(s) failed.", file=sys.stderr)
        return 1
    print("\nSecret storage checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
