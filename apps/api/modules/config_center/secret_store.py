from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from threading import Lock
from typing import Mapping

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values


SECRET_STORE_PATH = Path("apps/api/data/runtime_secrets.json")
SECRET_KEY_PATH = Path("apps/api/data/runtime_secret.key")
LOCAL_RUNTIME_ENV_PATH = Path("apps/api/data/runtime.env")
SECRET_ENV_KEYS = {
    "LLM_API_KEY",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_ENCRYPT_KEY",
    "WECOM_SECRET",
    "WECOM_TOKEN",
    "WECOM_ENCODING_AES_KEY",
    "DINGTALK_CLIENT_SECRET",
    "DINGTALK_WEBHOOK_SECRET",
}
SECRET_FIELD_BY_ENV_KEY = {
    "LLM_API_KEY": "llm_api_key",
    "FEISHU_APP_SECRET": "feishu_app_secret",
    "FEISHU_VERIFICATION_TOKEN": "feishu_verification_token",
    "FEISHU_ENCRYPT_KEY": "feishu_encrypt_key",
    "WECOM_SECRET": "wecom_secret",
    "WECOM_TOKEN": "wecom_token",
    "WECOM_ENCODING_AES_KEY": "wecom_encoding_aes_key",
    "DINGTALK_CLIENT_SECRET": "dingtalk_client_secret",
    "DINGTALK_WEBHOOK_SECRET": "dingtalk_webhook_secret",
}
SECRET_CANONICAL_BY_ENV_KEY = {
    "LLM_API_KEY": "LLM_API_KEY",
    "WORKBUDDY_LLM_API_KEY": "LLM_API_KEY",
    "OPENAI_API_KEY": "LLM_API_KEY",
    "FEISHU_APP_SECRET": "FEISHU_APP_SECRET",
    "WORKBUDDY_FEISHU_APP_SECRET": "FEISHU_APP_SECRET",
    "LARK_APP_SECRET": "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN": "FEISHU_VERIFICATION_TOKEN",
    "WORKBUDDY_FEISHU_VERIFICATION_TOKEN": "FEISHU_VERIFICATION_TOKEN",
    "LARK_VERIFICATION_TOKEN": "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_ENCRYPT_KEY": "FEISHU_ENCRYPT_KEY",
    "WORKBUDDY_FEISHU_ENCRYPT_KEY": "FEISHU_ENCRYPT_KEY",
    "LARK_ENCRYPT_KEY": "FEISHU_ENCRYPT_KEY",
    "WECOM_SECRET": "WECOM_SECRET",
    "WORKBUDDY_WECOM_SECRET": "WECOM_SECRET",
    "WECOM_TOKEN": "WECOM_TOKEN",
    "WORKBUDDY_WECOM_TOKEN": "WECOM_TOKEN",
    "WECOM_ENCODING_AES_KEY": "WECOM_ENCODING_AES_KEY",
    "WORKBUDDY_WECOM_ENCODING_AES_KEY": "WECOM_ENCODING_AES_KEY",
    "DINGTALK_CLIENT_SECRET": "DINGTALK_CLIENT_SECRET",
    "WORKBUDDY_DINGTALK_CLIENT_SECRET": "DINGTALK_CLIENT_SECRET",
    "DINGTALK_WEBHOOK_SECRET": "DINGTALK_WEBHOOK_SECRET",
    "WORKBUDDY_DINGTALK_WEBHOOK_SECRET": "DINGTALK_WEBHOOK_SECRET",
}
RUNTIME_FIELD_BY_ENV_KEY = {
    "LLM_PROVIDER": "llm_provider",
    "LLM_BASE_URL": "llm_base_url",
    "LLM_MODEL": "llm_model",
    "LLM_TIMEOUT_SECONDS": "llm_timeout_seconds",
    "ENABLE_REAL_IM_ADAPTERS": "enable_real_im_adapters",
    "ENABLE_EXTERNAL_SEND": "enable_external_send",
    "FEISHU_APP_ID": "feishu_app_id",
    "FEISHU_API_BASE_URL": "feishu_api_base_url",
    "FEISHU_APPROVAL_CHAT_ID": "feishu_approval_chat_id",
    "WECOM_CORP_ID": "wecom_corp_id",
    "WECOM_AGENT_ID": "wecom_agent_id",
    "DINGTALK_CLIENT_ID": "dingtalk_client_id",
    "DINGTALK_ROBOT_CODE": "dingtalk_robot_code",
}
ENV_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")
_STORE_LOCK = Lock()


class SecretStoreError(RuntimeError):
    pass


def load_encrypted_secret_fields(
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> dict[str, str]:
    secrets = load_encrypted_secrets(store_path=store_path, key_path=key_path)
    return {
        SECRET_FIELD_BY_ENV_KEY[key]: value
        for key, value in secrets.items()
        if key in SECRET_FIELD_BY_ENV_KEY
    }


def load_runtime_setting_fields(env_path: Path = LOCAL_RUNTIME_ENV_PATH) -> dict[str, str | int | bool]:
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    runtime_fields: dict[str, str | int | bool] = {}
    for env_key, field_name in RUNTIME_FIELD_BY_ENV_KEY.items():
        value = values.get(env_key)
        if not isinstance(value, str):
            continue
        if env_key in {"ENABLE_REAL_IM_ADAPTERS", "ENABLE_EXTERNAL_SEND"}:
            runtime_fields[field_name] = value.strip().lower() in {"1", "true", "yes", "on"}
        elif env_key == "LLM_TIMEOUT_SECONDS":
            try:
                runtime_fields[field_name] = int(value)
            except ValueError:
                continue
        else:
            runtime_fields[field_name] = value
    return runtime_fields


def load_encrypted_secrets(
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> dict[str, str]:
    if not store_path.exists():
        return {}
    if not key_path.exists():
        raise SecretStoreError("Encrypted secret store exists but its master key is missing.")

    payload = _read_store_payload(store_path)
    fernet = _load_fernet(key_path)
    decrypted: dict[str, str] = {}
    try:
        for key, token in payload.get("secrets", {}).items():
            if key in SECRET_ENV_KEYS and isinstance(token, str):
                decrypted[key] = fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise SecretStoreError("Encrypted secret store cannot be decrypted with the current master key.") from exc
    return decrypted


def save_encrypted_secrets(
    updates: Mapping[str, str],
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> list[str]:
    normalized = {
        key: str(value).replace("\n", "").replace("\r", "")
        for key, value in updates.items()
        if key in SECRET_ENV_KEYS and value != ""
    }
    if not normalized:
        return []

    with _STORE_LOCK:
        current = load_encrypted_secrets(store_path=store_path, key_path=key_path)
        current.update(normalized)
        key = _load_or_create_key(key_path)
        _write_encrypted_payload(current, Fernet(key), store_path)
    return list(normalized.keys())


def migrate_plaintext_secrets(
    env_path: Path = LOCAL_RUNTIME_ENV_PATH,
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> dict[str, object]:
    plaintext = read_plaintext_secrets(env_path)
    if not plaintext:
        return {
            "status": "no_plaintext_secrets",
            "migrated_keys": [],
            "backup_path": None,
        }

    with _STORE_LOCK:
        current = load_encrypted_secrets(store_path=store_path, key_path=key_path)
        current.update(plaintext)
        key = _load_or_create_key(key_path)
        _write_encrypted_payload(current, Fernet(key), store_path)

        backup_path = env_path.with_name(f"{env_path.name}.pre-secret-migration")
        shutil.copy2(env_path, backup_path)
        _chmod_private(backup_path)
        plaintext_env_keys = read_plaintext_secret_env_keys(env_path)
        remove_secret_lines(backup_path, plaintext_env_keys)
        remove_secret_lines(env_path, plaintext_env_keys)

    return {
        "status": "migrated",
        "migrated_keys": sorted(plaintext),
        "backup_path": str(backup_path),
    }


def rotate_master_key(
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> dict[str, object]:
    with _STORE_LOCK:
        current = load_encrypted_secrets(store_path=store_path, key_path=key_path)
        if not current:
            return {"status": "empty_store", "rotated_keys": []}

        old_key = key_path.read_bytes()
        old_store = store_path.read_bytes()
        new_key = Fernet.generate_key()
        try:
            _write_encrypted_payload(current, Fernet(new_key), store_path)
            _atomic_write_bytes(key_path, new_key + b"\n", mode=0o600)
            load_encrypted_secrets(store_path=store_path, key_path=key_path)
        except Exception:
            _atomic_write_bytes(key_path, old_key, mode=0o600)
            _atomic_write_bytes(store_path, old_store, mode=0o600)
            raise
    return {"status": "rotated", "rotated_keys": sorted(current)}


def secret_storage_status(
    env_path: Path = LOCAL_RUNTIME_ENV_PATH,
    store_path: Path = SECRET_STORE_PATH,
    key_path: Path = SECRET_KEY_PATH,
) -> dict[str, object]:
    plaintext_keys = sorted(read_plaintext_secret_env_keys(env_path))
    encrypted_keys: list[str] = []
    error: str | None = None
    try:
        encrypted_keys = sorted(load_encrypted_secrets(store_path=store_path, key_path=key_path))
    except SecretStoreError as exc:
        error = str(exc)

    key_mode = _permission_mode(key_path)
    return {
        "backend": "fernet_file",
        "store_path": str(store_path),
        "key_path": str(key_path),
        "store_exists": store_path.exists(),
        "key_exists": key_path.exists(),
        "key_file_mode": key_mode,
        "key_permissions_secure": key_mode in {None, "600"},
        "encrypted_key_count": len(encrypted_keys),
        "encrypted_keys": encrypted_keys,
        "plaintext_key_count": len(plaintext_keys),
        "plaintext_keys": plaintext_keys,
        "migration_required": bool(plaintext_keys),
        "healthy": error is None and (not store_path.exists() or key_path.exists()),
        "error": error,
    }


def read_plaintext_secrets(env_path: Path = LOCAL_RUNTIME_ENV_PATH) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    secrets: dict[str, str] = {}
    for key, value in values.items():
        canonical_key = SECRET_CANONICAL_BY_ENV_KEY.get(key)
        if canonical_key and isinstance(value, str) and value != "":
            secrets[canonical_key] = value
    return secrets


def read_plaintext_secret_env_keys(env_path: Path = LOCAL_RUNTIME_ENV_PATH) -> set[str]:
    if not env_path.exists():
        return set()
    values = dotenv_values(env_path)
    return {
        key
        for key, value in values.items()
        if key in SECRET_CANONICAL_BY_ENV_KEY and isinstance(value, str) and value != ""
    }


def env_keys_for_canonical_secrets(canonical_keys: set[str]) -> set[str]:
    return {
        env_key
        for env_key, canonical_key in SECRET_CANONICAL_BY_ENV_KEY.items()
        if canonical_key in canonical_keys
    }


def remove_secret_lines(env_path: Path, keys: set[str]) -> None:
    if not env_path.exists() or not keys:
        return
    retained: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE_RE.match(line)
        if match and match.group(1) in keys:
            continue
        retained.append(line)
    content = "\n".join(retained).rstrip()
    _atomic_write_bytes(env_path, (content + "\n" if content else "").encode("utf-8"), mode=0o600)


def _read_store_payload(store_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretStoreError("Encrypted secret store is unreadable or invalid.") from exc
    if payload.get("version") != 1 or not isinstance(payload.get("secrets"), dict):
        raise SecretStoreError("Encrypted secret store format is unsupported.")
    return payload


def _load_fernet(key_path: Path) -> Fernet:
    try:
        return Fernet(key_path.read_bytes().strip())
    except (OSError, ValueError) as exc:
        raise SecretStoreError("Secret master key is unreadable or invalid.") from exc


def _load_or_create_key(key_path: Path) -> bytes:
    if key_path.exists():
        try:
            return key_path.read_bytes().strip()
        except OSError as exc:
            raise SecretStoreError("Secret master key cannot be read.") from exc
    key = Fernet.generate_key()
    _atomic_write_bytes(key_path, key + b"\n", mode=0o600)
    return key


def _write_encrypted_payload(secrets: Mapping[str, str], fernet: Fernet, store_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    existing_created_at = now
    if store_path.exists():
        try:
            existing_created_at = str(_read_store_payload(store_path).get("created_at") or now)
        except SecretStoreError:
            existing_created_at = now
    payload = {
        "version": 1,
        "algorithm": "fernet",
        "created_at": existing_created_at,
        "updated_at": now,
        "secrets": {
            key: fernet.encrypt(value.encode("utf-8")).decode("ascii")
            for key, value in sorted(secrets.items())
            if key in SECRET_ENV_KEYS
        },
    }
    data = (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(store_path, data, mode=0o600)


def _atomic_write_bytes(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        _chmod_private(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _permission_mode(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return oct(path.stat().st_mode & 0o777)[2:]
    except OSError:
        return None
