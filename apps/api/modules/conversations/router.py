from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import func, select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import Channel, Conversation, MessageEvent


router = APIRouter()

VALID_BOUND_AGENTS = {
    None,
    "",
    "auto",
    "support_ticket_agent",
    "sales_lead_agent",
    "community_ops_agent",
    "recruiting_hr_agent",
}
VALID_SEND_MODES = {"inherit", "mock", "real", "disabled"}


class ConversationPolicyUpdate(BaseModel):
    bound_agent: str | None = Field(default=None)
    send_mode: str | None = Field(default=None)


class BulkConversationPolicyUpdate(ConversationPolicyUpdate):
    channel: str | None = Field(default=None)
    ids: list[int] | None = Field(default=None)


@router.get("")
def list_conversations(session: SessionDep, tenant: TenantDep, channel: str | None = None) -> dict[str, Any]:
    channel_filter = channel if channel and channel != "all" else None
    statement = (
        select(Conversation, Channel)
        .join(Channel, Conversation.channel_id == Channel.id)
        .where(Conversation.tenant_id == tenant.id)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    )
    if channel_filter:
        statement = statement.where(Channel.type == channel_filter)
    rows = session.exec(statement).all()
    return {
        "items": [serialize_conversation(session, conversation, channel) for conversation, channel in rows],
        "total": len(rows),
    }


@router.get("/feishu")
def list_feishu_conversations(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    return list_conversations(session, tenant, channel="feishu")


@router.patch("/policy/bulk")
def bulk_update_conversation_policy(
    payload: BulkConversationPolicyUpdate,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    validate_policy_payload(payload)
    statement = (
        select(Conversation, Channel)
        .join(Channel, Conversation.channel_id == Channel.id)
        .where(Conversation.tenant_id == tenant.id)
    )
    if payload.channel and payload.channel != "all":
        statement = statement.where(Channel.type == payload.channel)
    if payload.ids:
        statement = statement.where(Conversation.id.in_(payload.ids))
    rows = session.exec(statement).all()
    updated = []
    for conversation, channel in rows:
        apply_policy(conversation, payload)
        session.add(conversation)
        updated.append(serialize_conversation(session, conversation, channel))
    session.commit()
    return {"updated_count": len(updated), "items": updated}


@router.patch("/{conversation_id}/policy")
def update_conversation_policy(
    conversation_id: int,
    payload: ConversationPolicyUpdate,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    validate_policy_payload(payload)
    apply_policy(conversation, payload)

    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    channel = session.get(Channel, conversation.channel_id)
    return serialize_conversation(session, conversation, channel)


def validate_policy_payload(payload: ConversationPolicyUpdate) -> None:
    if payload.bound_agent is not None and payload.bound_agent not in VALID_BOUND_AGENTS:
        raise HTTPException(status_code=400, detail="Unsupported bound_agent")
    if payload.send_mode is not None and payload.send_mode not in VALID_SEND_MODES:
        raise HTTPException(status_code=400, detail="Unsupported send_mode")


def apply_policy(conversation: Conversation, payload: ConversationPolicyUpdate) -> None:
    if payload.bound_agent is not None:
        conversation.bound_agent = None if payload.bound_agent in {"", "auto"} else payload.bound_agent
    if payload.send_mode is not None:
        conversation.send_mode = payload.send_mode


def serialize_conversation(session, conversation: Conversation, channel: Channel | None) -> dict[str, Any]:
    message_count = session.exec(
        select(func.count())
        .select_from(MessageEvent)
        .where(MessageEvent.tenant_id == conversation.tenant_id, MessageEvent.conversation_id == conversation.id)
    ).one()
    latest_message = session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == conversation.tenant_id, MessageEvent.conversation_id == conversation.id)
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
    ).first()
    return {
        "id": conversation.id,
        "channel": channel.type if channel else "feishu",
        "name": conversation.name,
        "type": conversation.type,
        "external_conversation_id": conversation.external_conversation_id,
        "short_id": short_external_id(conversation.external_conversation_id),
        "bound_agent": conversation.bound_agent or "auto",
        "send_mode": conversation.send_mode or "inherit",
        "last_message_at": iso(conversation.last_message_at),
        "created_at": conversation.created_at.isoformat(),
        "message_count": message_count,
        "latest_message": {
            "id": latest_message.id,
            "text": latest_message.text,
            "sender_name": latest_message.sender_name,
            "received_at": latest_message.received_at.isoformat(),
        }
        if latest_message
        else None,
    }


def short_external_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 14:
        return value
    return f"{value[:6]}...{value[-4:]}"


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
