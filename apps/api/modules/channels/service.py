from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlmodel import Session, select

from apps.api.models import ChannelEvent, Tenant


def record_channel_event(
    session: Session,
    tenant: Tenant,
    *,
    channel_type: str,
    event_type: str,
    payload: dict[str, Any],
    status: str = "received",
) -> ChannelEvent:
    external_event_id = extract_event_id(payload) or stable_event_id(tenant.key, channel_type, event_type, payload)
    existing = session.exec(
        select(ChannelEvent).where(
            ChannelEvent.tenant_id == tenant.id,
            ChannelEvent.external_event_id == external_event_id,
        )
    ).first()
    if existing is not None:
        return existing

    event = ChannelEvent(
        tenant_id=tenant.id,
        channel_type=channel_type,
        event_type=event_type,
        external_event_id=external_event_id,
        conversation_external_id=extract_conversation_id(payload),
        actor_external_id=extract_actor_id(payload),
        status=status,
        raw_json=payload,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def extract_event_id(payload: dict[str, Any]) -> str | None:
    header = payload.get("header") or {}
    return value_as_string(header.get("event_id") or payload.get("event_id"))


def extract_conversation_id(payload: dict[str, Any]) -> str | None:
    event = payload.get("event") or payload
    message = event.get("message") or {}
    chat = event.get("chat") or {}
    return value_as_string(
        message.get("chat_id")
        or chat.get("chat_id")
        or payload.get("conversation_id")
        or event.get("conversation_id")
        or event.get("chat_id")
        or event.get("operator_id", {}).get("open_id")
    )


def extract_actor_id(payload: dict[str, Any]) -> str | None:
    event = payload.get("event") or payload
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    operator_id = event.get("operator_id") or {}
    user_id = event.get("user_id") or {}
    return value_as_string(
        sender_id.get("open_id")
        or payload.get("sender_id")
        or event.get("sender_id")
        or operator_id.get("open_id")
        or user_id.get("open_id")
        or event.get("open_id")
    )


def stable_event_id(tenant_key: str, channel_type: str, event_type: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(f"{tenant_key}:{event_type}:{raw}".encode("utf-8")).hexdigest()[:24]
    return f"{channel_type}_evt_{digest}"


def value_as_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
