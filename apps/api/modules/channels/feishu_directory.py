from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from apps.api.core.config import get_settings
from apps.api.models import Conversation, ExternalUser, Tenant, utc_now
from apps.api.modules.adapters.feishu import FeishuAdapterError, FeishuClient
from apps.api.modules.channels.service import record_channel_event
from apps.api.schemas import ImportRecord


@dataclass
class FeishuResolvedContext:
    sender_name: str | None = None
    conversation_name: str | None = None
    user_error: str | None = None
    conversation_error: str | None = None


class FeishuUserResolver:
    def __init__(self, session: Session, tenant: Tenant):
        self.session = session
        self.tenant = tenant
        self.settings = get_settings()
        self.client = FeishuClient(self.settings)

    def enrich_record(self, record: ImportRecord) -> FeishuResolvedContext:
        if record.channel != "feishu":
            return FeishuResolvedContext()

        context = FeishuResolvedContext()
        if record.sender_external_id:
            user = self.resolve_user(record.sender_external_id, record.raw_payload)
            if user and user.name:
                record.sender_name = user.name
                context.sender_name = user.name
            else:
                context.user_error = "user_not_resolved"

        record.raw_payload.setdefault("workbuddy_resolved", {})
        record.raw_payload["workbuddy_resolved"].update({"sender_name": context.sender_name})
        if record.conversation_id:
            name = self.resolve_conversation_name(record.conversation_id, record.raw_payload)
            if name:
                record.conversation_name = name
                context.conversation_name = name
            else:
                context.conversation_error = "conversation_not_resolved"

        record.raw_payload["workbuddy_resolved"].update(
            {
                "sender_name": context.sender_name,
                "conversation_name": context.conversation_name,
                "user_error": context.user_error,
                "conversation_error": context.conversation_error,
            }
        )
        return context

    def resolve_user(self, open_id: str, payload: dict[str, Any]) -> ExternalUser | None:
        cached = self.session.exec(
            select(ExternalUser).where(
                ExternalUser.tenant_id == self.tenant.id,
                ExternalUser.channel == "feishu",
                ExternalUser.external_user_id == open_id,
            )
        ).first()
        if cached and cached.name and cached.name != open_id:
            return cached

        if not self.settings.feishu_configured:
            self.record_resolution_failure("feishu.user.resolve.skipped", open_id, "Feishu credentials are not configured.", payload)
            return cached

        try:
            body = self.client.get_user_by_open_id(open_id)
            user_data = body.get("data", {}).get("user") or body.get("data") or {}
            name = first_text(user_data, "name", "nickname", "en_name") or open_id
            user = cached or ExternalUser(tenant_id=self.tenant.id, channel="feishu", external_user_id=open_id)
            user.name = name
            user.avatar_url = first_text(user_data, "avatar_url", "avatar_thumb")
            user.email = first_text(user_data, "email")
            user.mobile = first_text(user_data, "mobile")
            user.raw_json = body
            user.last_synced_at = utc_now()
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
            return user
        except FeishuAdapterError as exc:
            self.record_resolution_failure("feishu.user.resolve.failed", open_id, str(exc), payload)
            return cached

    def resolve_conversation_name(self, chat_id: str, payload: dict[str, Any]) -> str | None:
        existing = self.session.exec(
            select(Conversation).where(
                Conversation.tenant_id == self.tenant.id,
                Conversation.external_conversation_id == chat_id,
            )
        ).first()
        if existing and existing.name and existing.name != chat_id:
            return existing.name

        if is_p2p_payload(payload):
            sender_name = (payload.get("workbuddy_resolved") or {}).get("sender_name")
            return f"与 {sender_name} 的私聊" if sender_name else "飞书私聊"

        if not self.settings.feishu_configured:
            self.record_resolution_failure("feishu.chat.resolve.skipped", chat_id, "Feishu credentials are not configured.", payload)
            return existing.name if existing else None

        try:
            body = self.client.get_chat(chat_id)
            chat_data = body.get("data", {}) or {}
            name = first_text(chat_data, "name", "description")
            return name or (existing.name if existing else None)
        except FeishuAdapterError as exc:
            self.record_resolution_failure("feishu.chat.resolve.failed", chat_id, str(exc), payload)
            return existing.name if existing else None

    def record_resolution_failure(self, event_type: str, external_id: str, error: str, payload: dict[str, Any]) -> None:
        record_channel_event(
            self.session,
            self.tenant,
            channel_type="feishu",
            event_type=event_type,
            status="failed",
            payload={
                "event_id": f"{event_type}:{external_id}",
                "external_id": external_id,
                "error": error,
                "source_event_id": (payload.get("header") or {}).get("event_id"),
                "source_message_id": ((payload.get("event") or {}).get("message") or {}).get("message_id"),
            },
        )


def first_text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def is_p2p_payload(payload: dict[str, Any]) -> bool:
    event = payload.get("event") or {}
    message = event.get("message") or {}
    return message.get("chat_type") == "p2p"
