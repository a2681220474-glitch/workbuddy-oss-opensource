from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.core.config import get_settings
from apps.api.models import AgentRun, Channel, ChannelEvent, Conversation, MessageEvent
from apps.api.modules.adapters.feishu import FeishuAdapterError, parse_feishu_stream_event, parse_feishu_webhook
from apps.api.modules.channels.service import record_channel_event
from apps.api.modules.imports.service import import_records


router = APIRouter()
RETRYABLE_FEISHU_FAILURE_EVENTS = {"feishu.webhook.parse.failed", "feishu.stream.process.failed"}


@router.get("")
def list_channel_events(
    session: SessionDep,
    tenant: TenantDep,
    channel: str | None = None,
    status: str | None = None,
    relation: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    bounded_limit = min(max(limit, 1), 300)
    statement = select(ChannelEvent).where(ChannelEvent.tenant_id == tenant.id)
    if channel and channel != "all":
        statement = statement.where(ChannelEvent.channel_type == channel)
    if status and status != "all":
        statement = statement.where(ChannelEvent.status == status)
    statement = statement.order_by(ChannelEvent.created_at.desc(), ChannelEvent.id.desc()).limit(bounded_limit)
    items = [serialize_channel_event(session, event) for event in session.exec(statement).all()]
    if relation and relation != "all":
        items = [item for item in items if relation_matches(item, relation)]
    return {"items": items, "total": len(items)}


@router.post("/{event_id}/retry")
def retry_channel_event(event_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    event = session.get(ChannelEvent, event_id)
    if event is None or event.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Channel event not found")
    if event.channel_type != "feishu" or event.event_type not in RETRYABLE_FEISHU_FAILURE_EVENTS:
        raise HTTPException(status_code=400, detail="Only failed Feishu receive events can be retried in v0.15.2")
    if event.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed channel events can be retried")

    retry_source = retry_payload_for_event(event)
    if retry_source is None:
        run = record_retry_run(
            session,
            tenant.id,
            event,
            status="failed",
            output={"error": "No retryable raw payload found on this channel event."},
        )
        raise HTTPException(status_code=400, detail={"message": "No retryable raw payload found on this channel event.", "agent_run_id": run.id})

    try:
        if event.event_type == "feishu.webhook.parse.failed":
            result = parse_feishu_webhook(retry_source, get_settings())
        else:
            source_event_type = str((event.raw_json or {}).get("source_event_type") or "")
            result = parse_feishu_stream_event(retry_source, source_event_type or None)
    except FeishuAdapterError as exc:
        retry_event = record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="feishu",
            event_type="feishu.receive.retry.failed",
            status="failed",
            payload={
                "event_id": f"feishu.receive.retry.failed:{event.id}:{retry_attempt_count(session, event) + 1}",
                "source_channel_event_id": event.id,
                "error": str(exc),
                "advice": exc.advice,
                "raw_payload": retry_source,
            },
        )
        run = record_retry_run(session, tenant.id, event, status="failed", output={"error": str(exc), "retry_channel_event_id": retry_event.id})
        raise HTTPException(status_code=400, detail={"message": str(exc), "advice": exc.advice, "agent_run_id": run.id}) from exc

    if result.kind == "message" and result.record is not None:
        batch, messages = import_records(
            session=session,
            tenant=tenant,
            records=[result.record],
            source="feishu_retry",
            filename=f"channel-event-{event.id}",
        )
        event.status = "retried"
        session.add(event)
        session.commit()
        run = record_retry_run(
            session,
            tenant.id,
            event,
            status="success",
            output={"batch_id": batch.id, "message_ids": [message.id for message in messages], "message_count": len(messages)},
            message_id=messages[0].id if messages else None,
        )
        return {"status": "success", "kind": "message", "agent_run_id": run.id, "batch_id": batch.id, "message_ids": [message.id for message in messages]}

    if result.kind == "channel_event":
        retried = record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="feishu",
            event_type=result.reason or "feishu.receive.retry.channel_event",
            payload=retry_source,
        )
        event.status = "retried"
        session.add(event)
        session.commit()
        run = record_retry_run(session, tenant.id, event, status="success", output={"channel_event_id": retried.id})
        return {"status": "success", "kind": "channel_event", "agent_run_id": run.id, "channel_event_id": retried.id}

    event.status = "retried"
    session.add(event)
    session.commit()
    run = record_retry_run(session, tenant.id, event, status="ignored", output={"reason": result.reason})
    return {"status": "ignored", "kind": result.kind, "agent_run_id": run.id, "reason": result.reason}


def serialize_channel_event(session, event: ChannelEvent) -> dict[str, Any]:
    conversation = find_conversation(session, event)
    message = find_message(session, event, conversation)
    runs = find_agent_runs(session, event, message)
    return {
        "id": event.id,
        "channel_type": event.channel_type,
        "channel_label": channel_label(event.channel_type),
        "event_type": event.event_type,
        "external_event_id": event.external_event_id,
        "conversation_external_id": event.conversation_external_id,
        "actor_external_id": event.actor_external_id,
        "status": event.status,
        "raw_json": event.raw_json,
        "created_at": event.created_at.isoformat(),
        "links": {
            "message_id": message.id if message else None,
            "conversation_id": conversation.id if conversation else None,
            "agent_run_ids": [run.id for run in runs if run.id is not None],
        },
        "related_message": {
            "id": message.id,
            "text": message.text,
            "sender_name": message.sender_name,
            "received_at": message.received_at.isoformat(),
        }
        if message
        else None,
        "related_conversation": {
            "id": conversation.id,
            "name": conversation.name,
            "external_conversation_id": conversation.external_conversation_id,
        }
        if conversation
        else None,
        "related_agent_runs": [
            {
                "id": run.id,
                "agent_type": run.agent_type,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ],
        "retry": retry_metadata(session, event),
    }


def retry_metadata(session, event: ChannelEvent) -> dict[str, Any]:
    is_retry_candidate = event.channel_type == "feishu" and event.event_type in RETRYABLE_FEISHU_FAILURE_EVENTS and event.status == "failed"
    retryable = is_retry_candidate and retry_payload_for_event(event) is not None
    attempts = retry_attempt_count(session, event)
    return {
        "retryable": retryable,
        "attempts": attempts,
        "next_attempt": attempts + 1,
        "reason": retry_reason(event) if retryable else "缺少可回放的原始 payload，不能自动重试。" if is_retry_candidate else None,
    }


def retry_reason(event: ChannelEvent) -> str:
    raw = event.raw_json or {}
    if raw.get("error"):
        return str(raw.get("error"))
    return "Failed receive event can be retried from the stored raw payload."


def retry_attempt_count(session, event: ChannelEvent) -> int:
    if event.id is None:
        return 0
    runs = session.exec(
        select(AgentRun).where(
            AgentRun.tenant_id == event.tenant_id,
            AgentRun.agent_type == "feishu_receive_retry",
        )
    ).all()
    return sum(1 for run in runs if (run.action_json or {}).get("channel_event_id") == event.id)


def retry_payload_for_event(event: ChannelEvent) -> dict[str, Any] | None:
    raw = event.raw_json or {}
    candidate = raw.get("raw_payload") if isinstance(raw.get("raw_payload"), dict) else raw
    if not isinstance(candidate, dict):
        return None
    if not candidate:
        return None
    return candidate


def record_retry_run(
    session,
    tenant_id: int,
    event: ChannelEvent,
    *,
    status: str,
    output: dict[str, Any],
    message_id: int | None = None,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        message_id=message_id,
        agent_type="feishu_receive_retry",
        status=status,
        prompt_version="v0.15.2-feishu-retry-v1",
        prompt_json={"channel_event_id": event.id, "event_type": event.event_type},
        model_provider="local",
        model_name="receive-retry",
        model_output_json=output,
        action_json={"action_type": "retry_channel_event", "channel_event_id": event.id, "event_type": event.event_type},
        confidence=1.0 if status == "success" else 0.0,
        risk_level="medium" if status == "failed" else "low",
        error_message=output.get("error"),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def find_conversation(session, event: ChannelEvent) -> Conversation | None:
    if not event.conversation_external_id:
        return None
    return session.exec(
        select(Conversation)
        .join(Channel, Conversation.channel_id == Channel.id)
        .where(
            Conversation.tenant_id == event.tenant_id,
            Conversation.external_conversation_id == event.conversation_external_id,
            Channel.type == event.channel_type,
        )
    ).first()


def find_message(session, event: ChannelEvent, conversation: Conversation | None) -> MessageEvent | None:
    external_message_id = extract_message_id(event.raw_json)
    if external_message_id:
        message = session.exec(
            select(MessageEvent).where(
                MessageEvent.tenant_id == event.tenant_id,
                MessageEvent.external_message_id == external_message_id,
            )
        ).first()
        if message:
            return message
    if conversation is None:
        return None
    return session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == event.tenant_id, MessageEvent.conversation_id == conversation.id)
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
    ).first()


def find_agent_runs(session, event: ChannelEvent, message: MessageEvent | None) -> list[AgentRun]:
    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == event.tenant_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(100)
    ).all()
    matched = []
    for run in runs:
        if message and run.message_id == message.id:
            matched.append(run)
            continue
        model_output = run.model_output_json or {}
        action = run.action_json or {}
        if model_output.get("channel_event_id") == event.id or action.get("event_type") == event.event_type:
            matched.append(run)
    return matched[:6]


def extract_message_id(payload: dict[str, Any]) -> str | None:
    event = payload.get("event") or payload
    message = event.get("message") or {}
    value = message.get("message_id") or event.get("message_id") or payload.get("message_id")
    return str(value) if value else None


def relation_matches(item: dict[str, Any], relation: str) -> bool:
    links = item.get("links") or {}
    has_message = bool(links.get("message_id"))
    has_conversation = bool(links.get("conversation_id"))
    has_agent_run = bool(links.get("agent_run_ids"))
    if relation == "has_message":
        return has_message
    if relation == "has_conversation":
        return has_conversation
    if relation == "has_agent_run":
        return has_agent_run
    if relation == "unlinked":
        return not (has_message or has_conversation or has_agent_run)
    return True


def channel_label(value: str) -> str:
    labels = {
        "feishu": "飞书",
        "wecom": "企业微信",
        "dingtalk": "钉钉",
        "local": "本地",
    }
    return labels.get(value, value)
