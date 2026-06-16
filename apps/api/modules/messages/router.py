from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import MessageEvent
from apps.api.modules.display import enrich_message
from apps.api.modules.messages.replay import replay_message_route
from apps.api.schemas import MessageEventEnrichedRead, MessageEventRead


router = APIRouter()


@router.get("", response_model=list[MessageEventRead])
def list_messages(session: SessionDep, tenant: TenantDep, limit: int = 100, offset: int = 0) -> list[MessageEvent]:
    statement = (
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant.id)
        .order_by(MessageEvent.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.get("/enriched", response_model=list[MessageEventEnrichedRead])
def list_messages_enriched(
    session: SessionDep,
    tenant: TenantDep,
    limit: int = 100,
    offset: int = 0,
) -> list[MessageEventEnrichedRead]:
    statement = (
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant.id)
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [enrich_message(session, message) for message in session.exec(statement).all()]


@router.post("/{message_id}/rerun")
def rerun_message_route(message_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    message = session.get(MessageEvent, message_id)
    if message is None or message.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Message not found")

    return replay_message_route(session=session, tenant_id=tenant.id, message=message)
