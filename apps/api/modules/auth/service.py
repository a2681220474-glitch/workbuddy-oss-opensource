from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Response

from apps.api.core.config import get_settings
from apps.api.models import LocalUser, Tenant


PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    normalized = validate_password_strength(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    try:
        algorithm, iteration_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def validate_password_strength(password: str) -> str:
    normalized = password.strip()
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    return normalized


def active_password_user_count(users: list[LocalUser]) -> int:
    return sum(1 for user in users if user.status == "active" and bool(user.password_hash))


def set_session_cookie(response: Response, tenant: Tenant, user: LocalUser) -> None:
    settings = get_settings()
    payload = {
        "tenant_id": tenant.id,
        "user_id": user.id,
        "username": user.username,
        "exp": int(time.time()) + settings.auth_session_ttl_hours * 3600,
    }
    token = sign_session_payload(payload)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.auth_cookie_name, path="/")


def read_session_payload(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload_bytes = base64.urlsafe_b64decode(pad_base64(encoded_payload))
        signature = base64.urlsafe_b64decode(pad_base64(encoded_signature))
        expected = hmac.new(get_auth_secret(), payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def sign_session_payload(payload: dict[str, Any]) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = hmac.new(get_auth_secret(), payload_bytes, hashlib.sha256).digest()
    return "{}.{}".format(
        base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    )


def get_auth_secret() -> bytes:
    settings = get_settings()
    if settings.auth_secret:
        return settings.auth_secret.encode("utf-8")
    path = Path(settings.auth_secret_path)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    path.write_text(value + "\n", encoding="utf-8")
    return value.encode("utf-8")


def pad_base64(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return (value + padding).encode("ascii")
