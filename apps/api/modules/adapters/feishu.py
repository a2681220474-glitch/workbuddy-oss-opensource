from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apps.api.core.config import Settings
from apps.api.models import BEIJING_TZ
from apps.api.schemas import ImportRecord


class FeishuAdapterError(ValueError):
    """Raised when a Feishu callback or API request cannot be handled."""

    def __init__(self, message: str, *, code: int | None = None, body: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.body = body or {}
        self.advice = feishu_error_advice(code, message)


@dataclass
class FeishuWebhookResult:
    kind: str
    challenge: str | None = None
    record: ImportRecord | None = None
    reason: str | None = None


SUPPORTED_MESSAGE_EVENT = "im.message.receive_v1"
SUPPORTED_CHANNEL_EVENTS = {
    "im.chat.member.bot.added_v1",
    "im.chat.member.bot.deleted_v1",
    "im.chat.access_event.bot_p2p_chat_entered_v1",
}


def parse_feishu_webhook(payload: dict[str, Any], settings: Settings) -> FeishuWebhookResult:
    if "encrypt" in payload:
        payload = decrypt_feishu_callback_payload(payload, settings)

    if payload.get("type") == "url_verification":
        verify_callback_token(payload.get("token"), settings)
        return FeishuWebhookResult(kind="url_verification", challenge=str(payload.get("challenge") or ""))

    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("event", {}).get("type")
    if event_type != SUPPORTED_MESSAGE_EVENT:
        if event_type in SUPPORTED_CHANNEL_EVENTS:
            return FeishuWebhookResult(kind="channel_event", reason=str(event_type))
        return FeishuWebhookResult(kind="ignored", reason=f"Unsupported Feishu event: {event_type or 'unknown'}")

    verify_callback_token(header.get("token") or payload.get("token"), settings)
    return FeishuWebhookResult(kind="message", record=feishu_message_to_import_record(payload))


def decrypt_feishu_callback_payload(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    encrypted = payload.get("encrypt")
    if not encrypted:
        return payload
    if not settings.feishu_encrypt_key:
        raise FeishuAdapterError("Encrypted Feishu callback received, but FEISHU_ENCRYPT_KEY is not configured.")
    try:
        from lark_oapi.core.utils.decryptor import AESCipher

        decrypted = AESCipher(settings.feishu_encrypt_key).decrypt_str(str(encrypted))
    except Exception as exc:  # noqa: BLE001 - return a clear callback error instead of a traceback.
        raise FeishuAdapterError(f"Failed to decrypt Feishu callback payload: {exc}") from exc
    try:
        parsed = json.loads(decrypted)
    except json.JSONDecodeError as exc:
        raise FeishuAdapterError("Decrypted Feishu callback payload is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise FeishuAdapterError("Decrypted Feishu callback payload must be a JSON object.")
    parsed.setdefault("workbuddy_encrypted_callback", True)
    return parsed


def parse_feishu_stream_event(payload: dict[str, Any], event_type: str | None = None) -> FeishuWebhookResult:
    normalized_type = event_type or get_feishu_event_type(payload)
    if normalized_type == SUPPORTED_MESSAGE_EVENT:
        return FeishuWebhookResult(kind="message", record=feishu_message_to_import_record(payload))
    if normalized_type in SUPPORTED_CHANNEL_EVENTS:
        return FeishuWebhookResult(kind="channel_event", reason=normalized_type)
    return FeishuWebhookResult(kind="ignored", reason=f"Unsupported Feishu stream event: {normalized_type or 'unknown'}")


def get_feishu_event_type(payload: dict[str, Any]) -> str | None:
    header = payload.get("header") or {}
    event = payload.get("event") or {}
    return header.get("event_type") or event.get("type") or payload.get("event_type") or payload.get("type")


def verify_callback_token(token: Any, settings: Settings) -> None:
    if settings.feishu_verification_token and token != settings.feishu_verification_token:
        raise FeishuAdapterError("Feishu verification token mismatch.")


def feishu_message_to_import_record(payload: dict[str, Any]) -> ImportRecord:
    event = payload.get("event") or payload
    message = event.get("message") or event
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}

    chat_id = str(message.get("chat_id") or "feishu-unknown-chat")
    chat_type = str(message.get("chat_type") or "group")
    sender_external_id = first_value(sender_id, "open_id", "user_id", "union_id") or "feishu-unknown-user"
    sender_name = first_value(sender, "sender_name", "name") or sender_external_id
    message_type = str(message.get("message_type") or "text")
    text = extract_message_text(message)
    if message_type != "text":
        tracking = build_message_tracking(message_type, message)
        text = text or str(tracking.get("summary") or non_text_message_summary(message_type, message))
        payload.setdefault("workbuddy_message_tracking", {})
        payload["workbuddy_message_tracking"].update(tracking)

    return ImportRecord(
        text=text,
        sender_name=sender_name,
        sender_external_id=sender_external_id,
        timestamp=parse_feishu_timestamp(message.get("create_time") or payload.get("header", {}).get("create_time")),
        conversation_id=chat_id,
        conversation_name=chat_id,
        conversation_type="private" if chat_type == "p2p" else "group",
        channel="feishu",
        message_type=message_type,
        external_message_id=message.get("message_id"),
        raw_payload=payload,
    )


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, dict):
        return str(content.get("text") or content)
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return str(content)
    if isinstance(parsed, dict):
        return str(
            parsed.get("text")
            or parsed.get("title")
            or parsed.get("file_name")
            or parsed.get("name")
            or content_preview_text(parsed)
            or ""
        )
    return str(parsed)


def non_text_message_summary(message_type: str, message: dict[str, Any]) -> str:
    labels = {
        "image": "图片",
        "file": "文件",
        "audio": "语音",
        "media": "视频",
        "post": "富文本",
        "interactive": "互动卡片",
        "share_chat": "分享会话",
        "sticker": "表情",
    }
    content = parse_content_dict(message)
    filename = content.get("file_name") or content.get("name") or content.get("title")
    suffix = f"：{filename}" if filename else ""
    return f"[飞书{labels.get(message_type, message_type)}消息]{suffix}"


def build_message_tracking(message_type: str, message: dict[str, Any]) -> dict[str, Any]:
    content = parse_content_dict(message)
    preview = content_preview_text(content)
    title = first_non_empty(
        content.get("file_name"),
        content.get("name"),
        content.get("title"),
        preview,
    )
    details = {
        "title": title,
        "file_name": first_non_empty(content.get("file_name"), content.get("name")),
        "image_key": first_non_empty(content.get("image_key"), content.get("imageKey")),
        "file_key": first_non_empty(content.get("file_key"), content.get("fileKey"), content.get("media_key"), content.get("mediaKey")),
        "post_title": first_non_empty(post_title(content)),
        "content_preview": preview,
        "mentions": mention_names(content),
        "content_keys": content_keys(message),
    }
    return {
        "traceable_non_text": True,
        "message_type": message_type,
        "message_type_label": message_type_label(message_type),
        "summary": non_text_message_summary(message_type, message),
        "content_preview": preview,
        "content_keys": content_keys(message),
        "details": {key: value for key, value in details.items() if value not in (None, "", [], {})},
    }


def message_type_label(message_type: str) -> str:
    labels = {
        "text": "文本",
        "image": "图片",
        "file": "文件",
        "audio": "语音",
        "media": "视频",
        "post": "富文本",
        "interactive": "互动卡片",
        "share_chat": "分享会话",
        "sticker": "表情",
    }
    return labels.get(message_type, message_type)


def content_keys(message: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in parse_content_dict(message).keys())


def parse_content_dict(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, dict):
        return content
    try:
        parsed = json.loads(content) if content is not None else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def content_preview_text(content: dict[str, Any]) -> str | None:
    preview = flatten_text(content)
    if not preview:
        return None
    preview = " ".join(preview.split())
    return preview[:220]


def flatten_text(value: Any) -> str:
    parts: list[str] = []
    _append_text_parts(parts, value)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _append_text_parts(parts: list[str], value: Any) -> None:
    if value in (None, ""):
        return
    if isinstance(value, str):
        parts.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _append_text_parts(parts, item)
        return
    if isinstance(value, dict):
        preferred_keys = ["text", "title", "file_name", "name", "content", "tag"]
        for key in preferred_keys:
            if key in value:
                _append_text_parts(parts, value.get(key))
        for key, item in value.items():
            if key in preferred_keys:
                continue
            if key in {"image_key", "file_key", "media_key", "emoji_type", "at_user_id"}:
                continue
            _append_text_parts(parts, item)


def post_title(content: dict[str, Any]) -> str | None:
    if isinstance(content.get("title"), str) and content.get("title"):
        return str(content.get("title"))
    for locale in ["zh_cn", "en_us", "default"]:
        value = content.get(locale)
        if isinstance(value, dict) and value.get("title"):
            return str(value.get("title"))
    return None


def mention_names(content: dict[str, Any]) -> list[str]:
    names: list[str] = []
    _append_mentions(names, content)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered[:8]


def _append_mentions(names: list[str], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _append_mentions(names, item)
        return
    if not isinstance(value, dict):
        return
    tag = value.get("tag")
    if tag == "at":
        name = first_non_empty(value.get("user_name"), value.get("name"), value.get("text"))
        if name:
            names.append(str(name))
    for item in value.values():
        _append_mentions(names, item)


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value in (None, "", [], {}):
            continue
        return str(value)
    return None


def parse_feishu_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value)
    try:
        number = int(raw)
    except ValueError:
        return None
    seconds = number / 1000 if number > 10_000_000_000 else number
    return datetime.fromtimestamp(seconds, tz=BEIJING_TZ)


def first_value(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


class FeishuClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        configure_certificates()

    def get_tenant_access_token(self) -> str:
        if not self.settings.feishu_app_id or not self.settings.feishu_app_secret:
            raise FeishuAdapterError("FEISHU_APP_ID and FEISHU_APP_SECRET are required to fetch tenant_access_token.")
        payload = json.dumps(
            {
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.feishu_api_base_url.rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise FeishuAdapterError(f"Failed to fetch tenant_access_token: {exc}") from exc
        token = body.get("tenant_access_token")
        if not token:
            raise FeishuAdapterError(f"Feishu token response did not include tenant_access_token: {body}")
        return str(token)

    def get_user_by_open_id(self, open_id: str) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        request = urllib.request.Request(
            f"{self.settings.feishu_api_base_url.rstrip('/')}/open-apis/contact/v3/users/{open_id}?user_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        return self._read_json(request)

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        request = urllib.request.Request(
            f"{self.settings.feishu_api_base_url.rstrip('/')}/open-apis/im/v1/chats/{chat_id}",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        return self._read_json(request)

    def send_text_to_chat(self, chat_id: str, text: str, request_uuid: str | None = None) -> dict[str, Any]:
        if not self.settings.enable_external_send:
            return {
                "sent": False,
                "mode": "mock",
                "reason": "ENABLE_EXTERNAL_SEND=false, external Feishu send is disabled in Phase 0.2.",
                "chat_id": chat_id,
                "text": text,
            }

        token = self.get_tenant_access_token()
        payload = json.dumps(
            {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
                "uuid": request_uuid or str(uuid.uuid4()),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.feishu_api_base_url.rstrip('/')}/open-apis/im/v1/messages?receive_id_type=chat_id",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._read_json(request)

    def send_interactive_card_to_chat(self, chat_id: str, card: dict[str, Any], request_uuid: str | None = None) -> dict[str, Any]:
        if not self.settings.enable_external_send:
            return {
                "sent": False,
                "mode": "mock",
                "reason": "ENABLE_EXTERNAL_SEND=false, external Feishu card send is disabled.",
                "chat_id": chat_id,
                "card": card,
            }

        token = self.get_tenant_access_token()
        payload = json.dumps(
            {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
                "uuid": request_uuid or str(uuid.uuid4()),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.feishu_api_base_url.rstrip('/')}/open-apis/im/v1/messages?receive_id_type=chat_id",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._read_json(request)

    def _read_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
                code = body.get("code")
                if code not in (None, 0):
                    message = str(body.get("msg") or body.get("message") or "Feishu API returned an error.")
                    raise FeishuAdapterError(message, code=int(code), body=body)
                return body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = parse_error_body(body)
            raise FeishuAdapterError(
                f"Feishu API HTTP {exc.code}: {parsed.get('msg') or parsed.get('message') or body}",
                code=exc.code,
                body=parsed,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise FeishuAdapterError(f"Feishu API request failed: {exc}") from exc


def parse_error_body(body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def feishu_error_advice(code: int | None, message: str) -> str:
    text = message.lower()
    if code in {99991663, 99991664} or "token" in text:
        return "检查 FEISHU_APP_ID / FEISHU_APP_SECRET 是否正确，并确认应用已发布。"
    if code in {99991672, 99991673} or "permission" in text or "scope" in text:
        return "检查飞书应用权限范围，至少需要机器人发消息和相关 IM 权限，并在后台发布最新版本。"
    if "chat" in text or "receive" in text:
        return "检查机器人是否在该会话中、chat_id 是否来自飞书消息，以及应用可见范围是否包含测试人员。"
    return "查看飞书开放平台错误码，确认应用权限、发布状态和机器人所在会话。"


def configure_certificates() -> None:
    try:
        import certifi
    except ImportError:
        return
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
