from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Mapping
from xml.etree import ElementTree

from Crypto.Cipher import AES

from apps.api.core.config import Settings
from apps.api.models import BEIJING_TZ
from apps.api.modules.adapters.base import AdapterCapabilities, AdapterResult, ChannelAdapter
from apps.api.schemas import ImportRecord


class WeComAdapterError(ValueError):
    def __init__(self, message: str, *, code: int | None = None, body: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.body = body or {}
        self.advice = wecom_error_advice(code, message)


@dataclass
class WeComWebhookResult:
    kind: str
    challenge: str | None = None
    record: ImportRecord | None = None
    reason: str | None = None
    event_type: str | None = None
    raw_payload: dict[str, Any] | None = None


class WeComAdapter(ChannelAdapter):
    channel = "wecom"
    label = "企业微信"
    capabilities = AdapterCapabilities(receive_event=True, normalize_message=True, send_message=True)

    def receive_event(self, payload: dict[str, Any]) -> AdapterResult:
        record = wecom_payload_to_import_record(payload)
        return AdapterResult(
            kind="message",
            reason="企业微信 payload 已按真实字段标准化，可直接进入 MessageEvent 与 Agent 流水线。",
            raw=record.raw_payload,
        )

    def send_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        raise NotImplementedError("Use WeComClient with a resolved delivery target.")


_TOKEN_CACHE_LOCK = Lock()
_TOKEN_CACHE: dict[str, dict[str, Any]] = {}


def verify_wecom_callback_url(
    *,
    msg_signature: str | None,
    timestamp: str | None,
    nonce: str | None,
    echostr: str | None,
    settings: Settings,
) -> str:
    if not echostr:
        raise WeComAdapterError("Missing echostr in WeCom callback verification request.")
    if settings.wecom_encoding_aes_key:
        if not settings.wecom_token:
            raise WeComAdapterError("WECOM_TOKEN is required before verifying encrypted WeCom callbacks.")
        verify_wecom_signature(
            token=settings.wecom_token,
            timestamp=timestamp,
            nonce=nonce,
            encrypted=echostr,
            expected_signature=msg_signature,
        )
        return decrypt_wecom_payload(echostr, settings)
    if settings.wecom_token and msg_signature:
        verify_wecom_signature(
            token=settings.wecom_token,
            timestamp=timestamp,
            nonce=nonce,
            encrypted=echostr,
            expected_signature=msg_signature,
        )
    return echostr


def parse_wecom_webhook(body: bytes, query_params: Mapping[str, str], settings: Settings) -> WeComWebhookResult:
    payload = parse_wecom_xml(body)
    encrypted = string_value(payload.get("Encrypt"))
    if encrypted:
        token = settings.wecom_token
        if not token:
            raise WeComAdapterError("Encrypted WeCom callback received, but WECOM_TOKEN is not configured.")
        verify_wecom_signature(
            token=token,
            timestamp=query_params.get("timestamp"),
            nonce=query_params.get("nonce"),
            encrypted=encrypted,
            expected_signature=query_params.get("msg_signature"),
        )
        decrypted_xml = decrypt_wecom_payload(encrypted, settings)
        message = parse_wecom_xml(decrypted_xml.encode("utf-8"))
        raw_payload = {
            "encrypted": True,
            "query": dict(query_params),
            "outer_xml": payload,
            "decrypted_xml": message,
        }
    else:
        if settings.wecom_token and query_params.get("msg_signature"):
            verify_wecom_signature(
                token=settings.wecom_token,
                timestamp=query_params.get("timestamp"),
                nonce=query_params.get("nonce"),
                encrypted=body.decode("utf-8", errors="ignore"),
                expected_signature=query_params.get("msg_signature"),
            )
        message = payload
        raw_payload = {
            "encrypted": False,
            "query": dict(query_params),
            "xml": message,
        }

    msg_type = string_value(message.get("MsgType")) or "unknown"
    if msg_type == "event":
        event_type = string_value(message.get("Event")) or "event"
        raw_payload["workbuddy_event_type"] = f"wecom.event.{event_type.lower()}"
        return WeComWebhookResult(
            kind="channel_event",
            reason=event_type,
            event_type=f"wecom.event.{event_type.lower()}",
            raw_payload=raw_payload,
        )

    record = wecom_xml_message_to_import_record(message, raw_payload=raw_payload)
    return WeComWebhookResult(
        kind="message",
        record=record,
        event_type=f"wecom.message.{record.message_type}",
        raw_payload=raw_payload,
    )


def wecom_payload_to_import_record(payload: dict[str, Any]) -> ImportRecord:
    xml = payload.get("xml")
    if isinstance(xml, dict):
        return wecom_xml_message_to_import_record(xml, raw_payload=payload)
    if "MsgType" in payload or "FromUserName" in payload:
        return wecom_xml_message_to_import_record(payload, raw_payload={"xml": payload})
    return record_from_mapping(payload)


def wecom_xml_message_to_import_record(message: Mapping[str, Any], *, raw_payload: dict[str, Any]) -> ImportRecord:
    sender_id = string_value(message.get("FromUserName")) or "wecom-unknown-user"
    chat_id = string_value(message.get("ChatId"))
    message_type = (string_value(message.get("MsgType")) or "text").lower()
    text = extract_wecom_text(message_type, message)
    timestamp = parse_wecom_timestamp(message.get("CreateTime"))
    conversation_id = chat_id or sender_id
    conversation_type = "group" if chat_id else "private"
    conversation_name = chat_id or sender_id
    external_message_id = string_value(message.get("MsgId")) or fallback_message_id(message)
    delivery_target_type = "chat" if chat_id else "user"
    delivery_target_id = chat_id or sender_id
    summary = non_text_wecom_summary(message_type, message)
    tracking = build_wecom_tracking(message_type, message)
    if message_type != "text":
        text = text or tracking.get("summary") or summary

    raw_payload.setdefault("workbuddy_message_tracking", {})
    raw_payload["workbuddy_message_tracking"].update(tracking)
    raw_payload["workbuddy_wecom"] = {
        "delivery_target_type": delivery_target_type,
        "delivery_target_id": delivery_target_id,
        "conversation_type": conversation_type,
        "chat_id": chat_id,
        "sender_userid": sender_id,
        "source_agent_id": string_value(message.get("AgentID")),
    }

    return ImportRecord(
        text=text or summary,
        sender_name=sender_id,
        sender_external_id=sender_id,
        timestamp=timestamp,
        conversation_id=conversation_id,
        conversation_name=conversation_name,
        conversation_type=conversation_type,
        channel="wecom",
        message_type=message_type,
        external_message_id=external_message_id,
        raw_payload=raw_payload,
    )


def record_from_mapping(payload: dict[str, Any]) -> ImportRecord:
    channel = str(payload.get("channel") or "wecom")
    text = str(payload.get("text") or payload.get("content") or payload.get("message") or "")
    sender_external_id = string_value(payload.get("sender_external_id")) or string_value(payload.get("user_id")) or "wecom-demo-user"
    sender_name = string_value(payload.get("sender_name")) or sender_external_id
    conversation_id = string_value(payload.get("conversation_id")) or string_value(payload.get("chat_id")) or sender_external_id
    conversation_name = string_value(payload.get("conversation_name")) or string_value(payload.get("chat_name")) or conversation_id
    conversation_type = string_value(payload.get("conversation_type")) or string_value(payload.get("chat_type")) or ("group" if payload.get("chat_id") else "private")
    message_type = string_value(payload.get("message_type")) or "text"
    timestamp = parse_wecom_timestamp(payload.get("timestamp") or payload.get("create_time"))
    raw_payload = dict(payload)
    raw_payload.setdefault("workbuddy_wecom", {})
    raw_payload["workbuddy_wecom"].update(
        {
            "delivery_target_type": "chat" if conversation_type == "group" else "user",
            "delivery_target_id": conversation_id,
        }
    )
    return ImportRecord(
        text=text,
        sender_name=sender_name,
        sender_external_id=sender_external_id,
        timestamp=timestamp,
        conversation_id=conversation_id,
        conversation_name=conversation_name,
        conversation_type=conversation_type,
        channel=channel,
        message_type=message_type,
        external_message_id=string_value(payload.get("external_message_id")) or string_value(payload.get("message_id")) or fallback_mapping_message_id(payload),
        raw_payload=raw_payload,
    )


def parse_wecom_xml(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="ignore").strip()
    if not text:
        raise WeComAdapterError("WeCom callback body is empty.")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise WeComAdapterError(f"WeCom callback XML is invalid: {exc}") from exc
    result: dict[str, Any] = {}
    for child in root:
        result[child.tag] = child.text or ""
    return result


def verify_wecom_signature(
    *,
    token: str,
    timestamp: str | None,
    nonce: str | None,
    encrypted: str,
    expected_signature: str | None,
) -> None:
    if not expected_signature:
        raise WeComAdapterError("Missing msg_signature for WeCom callback verification.")
    values = sorted([token, timestamp or "", nonce or "", encrypted])
    digest = hashlib.sha1("".join(values).encode("utf-8")).hexdigest()
    if digest != expected_signature:
        raise WeComAdapterError("WeCom callback signature mismatch.")


def decrypt_wecom_payload(encrypted: str, settings: Settings) -> str:
    aes_key = settings.wecom_encoding_aes_key
    if not aes_key:
        raise WeComAdapterError("WECOM_ENCODING_AES_KEY is required before decrypting WeCom callbacks.")
    try:
        key = base64.b64decode(f"{aes_key}=")
    except binascii.Error as exc:
        raise WeComAdapterError("WECOM_ENCODING_AES_KEY is not a valid 43-char base64 string.") from exc
    try:
        cipher = AES.new(key, AES.MODE_CBC, iv=key[:16])
        decrypted = cipher.decrypt(base64.b64decode(encrypted))
    except Exception as exc:  # noqa: BLE001 - convert crypto failures to a user-facing callback error.
        raise WeComAdapterError(f"Failed to decrypt WeCom callback payload: {exc}") from exc

    padded = pkcs7_unpad(decrypted)
    if len(padded) < 20:
        raise WeComAdapterError("Decrypted WeCom callback payload is too short.")
    xml_length = struct.unpack("!I", padded[16:20])[0]
    xml_bytes = padded[20:20 + xml_length]
    receiver_id = padded[20 + xml_length:].decode("utf-8", errors="ignore")
    xml_text = xml_bytes.decode("utf-8", errors="ignore")
    if settings.wecom_corp_id and receiver_id and receiver_id != settings.wecom_corp_id:
        raise WeComAdapterError("WeCom callback receiver mismatch. Please check Corp ID and callback settings.")
    return xml_text


def pkcs7_unpad(value: bytes) -> bytes:
    if not value:
        return value
    pad = value[-1]
    if pad < 1 or pad > 32:
        raise WeComAdapterError("Invalid WeCom callback padding.")
    return value[:-pad]


def extract_wecom_text(message_type: str, message: Mapping[str, Any]) -> str:
    if message_type == "text":
        return string_value(message.get("Content")) or ""
    if message_type in {"image", "voice", "video", "file"}:
        return string_value(message.get("MediaId")) or ""
    if message_type == "location":
        label = string_value(message.get("Label")) or ""
        return label
    if message_type == "link":
        return string_value(message.get("Title")) or string_value(message.get("Description")) or ""
    return string_value(message.get("Content")) or ""


def non_text_wecom_summary(message_type: str, message: Mapping[str, Any]) -> str:
    labels = {
        "image": "图片",
        "voice": "语音",
        "video": "视频",
        "file": "文件",
        "location": "位置",
        "link": "链接",
    }
    suffix = string_value(message.get("Title")) or string_value(message.get("Label")) or string_value(message.get("MediaId")) or ""
    return f"[企微{labels.get(message_type, message_type)}消息]{f'：{suffix}' if suffix else ''}"


def build_wecom_tracking(message_type: str, message: Mapping[str, Any]) -> dict[str, Any]:
    details = {
        "title": string_value(message.get("Title")),
        "description": string_value(message.get("Description")),
        "media_id": string_value(message.get("MediaId")),
        "label": string_value(message.get("Label")),
        "url": string_value(message.get("Url")),
        "chat_id": string_value(message.get("ChatId")),
    }
    return {
        "traceable_non_text": message_type != "text",
        "message_type": message_type,
        "message_type_label": wecom_message_type_label(message_type),
        "summary": non_text_wecom_summary(message_type, message),
        "details": {key: value for key, value in details.items() if value not in (None, "")},
    }


def parse_wecom_timestamp(value: Any) -> datetime | None:
    raw = string_value(value)
    if not raw:
        return None
    try:
        number = int(raw)
    except ValueError:
        return None
    seconds = number / 1000 if number > 10_000_000_000 else number
    return datetime.fromtimestamp(seconds, tz=BEIJING_TZ)


def fallback_message_id(message: Mapping[str, Any]) -> str:
    parts = [
        string_value(message.get("FromUserName")) or "wecom-user",
        string_value(message.get("ChatId")) or "direct",
        string_value(message.get("CreateTime")) or str(int(time.time())),
        string_value(message.get("Content")) or string_value(message.get("MediaId")) or string_value(message.get("Event")) or "message",
    ]
    digest = hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"wecom_msg_{digest}"


def fallback_mapping_message_id(payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]
    return f"wecom_mock_{digest}"


def string_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def wecom_message_type_label(message_type: str) -> str:
    labels = {
        "text": "文本",
        "image": "图片",
        "voice": "语音",
        "video": "视频",
        "file": "文件",
        "location": "位置",
        "link": "链接",
        "event": "事件",
    }
    return labels.get(message_type, message_type)


class WeComClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        configure_certificates()

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        corp_id = self.settings.wecom_corp_id.strip()
        secret = self.settings.wecom_secret.strip()
        if not corp_id or not secret:
            raise WeComAdapterError("WECOM_CORP_ID and WECOM_SECRET are required to fetch access_token.")
        cache_key = f"{corp_id}:{secret}"
        now = time.time()
        with _TOKEN_CACHE_LOCK:
            cached = _TOKEN_CACHE.get(cache_key)
            if cached and not force_refresh and float(cached.get("expires_at") or 0) > now + 60:
                return str(cached["token"])

        query = urllib.parse.urlencode({"corpid": corp_id, "corpsecret": secret})
        request = urllib.request.Request(
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?{query}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        body = self._read_json(request)
        token = string_value(body.get("access_token"))
        if not token:
            raise WeComAdapterError("WeCom token response did not include access_token.", body=body)
        expires_in = int(body.get("expires_in") or 7200)
        with _TOKEN_CACHE_LOCK:
            _TOKEN_CACHE[cache_key] = {
                "token": token,
                "expires_at": now + max(300, expires_in - 120),
            }
        return token

    def send_text_to_user(self, user_id: str, text: str, request_uuid: str | None = None) -> dict[str, Any]:
        agent_id = self._agent_id_value()
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": agent_id,
            "text": {"content": text},
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 1,
            "duplicate_check_interval": 1800,
        }
        return self._post_json("/cgi-bin/message/send", payload, request_uuid=request_uuid)

    def send_text_to_chat(self, chat_id: str, text: str, request_uuid: str | None = None) -> dict[str, Any]:
        payload = {
            "chatid": chat_id,
            "msgtype": "text",
            "text": {"content": text},
            "safe": 0,
        }
        return self._post_json("/cgi-bin/appchat/send", payload, request_uuid=request_uuid)

    def _agent_id_value(self) -> int | str:
        raw = self.settings.wecom_agent_id.strip()
        if not raw:
            raise WeComAdapterError("WECOM_AGENT_ID is required before sending WeCom application messages.")
        return int(raw) if raw.isdigit() else raw

    def _post_json(self, path: str, payload: dict[str, Any], *, request_uuid: str | None = None) -> dict[str, Any]:
        token = self.get_access_token()
        body = dict(payload)
        if request_uuid and path == "/cgi-bin/message/send":
            body["clientmsgid"] = request_uuid
        request = urllib.request.Request(
            f"https://qyapi.weixin.qq.com{path}?access_token={urllib.parse.quote(token)}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        return self._read_json(request)

    def _read_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            parsed = parse_error_body(body_text)
            errcode = parsed.get("errcode") if isinstance(parsed, dict) else exc.code
            errmsg = parsed.get("errmsg") if isinstance(parsed, dict) else body_text
            raise WeComAdapterError(f"WeCom API HTTP {exc.code}: {errmsg}", code=int(errcode or exc.code), body=parsed if isinstance(parsed, dict) else {"raw": body_text}) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WeComAdapterError(f"WeCom API request failed: {exc}") from exc

        errcode = int(body.get("errcode") or 0)
        if errcode != 0:
            errmsg = string_value(body.get("errmsg")) or "WeCom API returned an error."
            raise WeComAdapterError(errmsg, code=errcode, body=body)
        return body


def parse_error_body(body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def wecom_error_advice(code: int | None, message: str) -> str:
    text = message.lower()
    if code == 60020 or "not allow to access from your ip" in text:
        return "企业微信限制了调用接口的来源 IP。请在企业微信后台的可信 IP / IP 白名单中加入当前出口 IP，或先关闭该限制后再重试发送。"
    if code in {40013, 42001} or "token" in text:
        return "检查 Corp ID / Secret 是否正确，并确认企业微信应用已可用。"
    if code in {48001, 48002, 60011} or "permission" in text or "agent" in text:
        return "检查企业微信应用权限、可见范围，以及 Agent ID 是否和当前 Secret 对应。"
    if "signature" in text or "decrypt" in text or "callback" in text:
        return "检查 Token、EncodingAESKey、回调 URL 模式，以及企业微信后台保存的参数是否一致。"
    if "chat" in text:
        return "检查 ChatId 是否来自企业微信应用会话；如果不是应用会话群，建议先用单聊消息做正式验收。"
    return "查看企业微信开放平台错误码，确认凭证、权限、应用可见范围和回调配置。"


def configure_certificates() -> None:
    try:
        import certifi
    except ImportError:
        return
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
