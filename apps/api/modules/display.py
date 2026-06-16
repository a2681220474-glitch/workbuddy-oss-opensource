from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from apps.api.models import AgentRun, Approval, Candidate, Channel, Conversation, FollowupTask, KnowledgeGap, Lead, MessageEvent, Ticket
from apps.api.modules.approvals.delivery import delivery_runs_for_approval, latest_delivery_run_for_approval
from apps.api.schemas import ApprovalEnrichedRead, MessageEventEnrichedRead, RelatedObjectRead


def enrich_message(session: Session, message: MessageEvent) -> MessageEventEnrichedRead:
    run = latest_run_for_message(session, message.id)
    route = route_from_run(run)
    related_objects = related_objects_for_message(session, message)
    channel = session.get(Channel, message.channel_id)
    conversation = session.get(Conversation, message.conversation_id)
    tracking = message_tracking(message)
    return MessageEventEnrichedRead(
        **message.model_dump(),
        channel_label=channel_label(channel.type if channel else None),
        sender_display_name=display_name(message.sender_name, message.sender_external_id),
        sender_short_id=short_external_id(message.sender_external_id),
        conversation_display_name=display_name(conversation.name if conversation else None, conversation.external_conversation_id if conversation else None),
        conversation_short_id=short_external_id(conversation.external_conversation_id if conversation else None),
        message_type_label=tracking.get("message_type_label") or message_type_label(message.message_type),
        traceable_non_text=bool(tracking.get("traceable_non_text")),
        non_text_summary=tracking.get("summary"),
        message_tracking=tracking,
        intent=route.get("intent"),
        target_agent=route.get("target_agent") or (run.agent_type if run else None),
        risk_level=route.get("risk_level") or (run.risk_level if run else None),
        confidence=route.get("confidence") if route.get("confidence") is not None else (run.confidence if run else None),
        agent_run_id=run.id if run else None,
        has_related_objects=bool(related_objects),
        related_objects=related_objects,
    )


def enrich_approval(session: Session, approval: Approval) -> ApprovalEnrichedRead:
    run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    message = session.get(MessageEvent, run.message_id) if run and run.message_id else None
    route = route_from_run(run)
    related = related_object_for_run(session, run)
    delivery_run = latest_delivery_run_for_approval(session, approval)
    delivery_runs = delivery_runs_for_approval(session, approval)
    delivery_output = delivery_run.model_output_json if delivery_run else {}
    delivery_result = delivery_output.get("result") if isinstance(delivery_output, dict) else {}
    approval_data = approval.model_dump()
    if delivery_run and delivery_run.status == "success":
        approval_data["status"] = "sent"
    return ApprovalEnrichedRead(
        **approval_data,
        original_message=message.text if message else None,
        original_sender_name=message.sender_name if message else None,
        original_sender_display_name=display_name(message.sender_name, message.sender_external_id) if message else None,
        original_conversation_display_name=conversation_name_for_message(session, message) if message else None,
        intent=route.get("intent"),
        target_agent=route.get("target_agent") or (run.agent_type if run else None),
        risk_level=route.get("risk_level") or (run.risk_level if run else None),
        confidence=route.get("confidence") if route.get("confidence") is not None else (run.confidence if run else None),
        action_type="send_draft_to_approval",
        business_object_type=related.type if related else None,
        business_object_id=related.id if related else None,
        business_object_label=related.label if related else None,
        delivery_status=delivery_run.status if delivery_run else None,
        delivery_channel=delivery_output.get("channel") if isinstance(delivery_output, dict) else None,
        delivery_mode=delivery_output.get("mode") or (delivery_result.get("mode") if isinstance(delivery_result, dict) else None),
        delivery_error=delivery_run.error_message if delivery_run else None,
        delivery_advice=delivery_output.get("advice") if isinstance(delivery_output, dict) else None,
        delivery_chat_id=delivery_output.get("chat_id") if isinstance(delivery_output, dict) else None,
        delivery_feishu_message_id=delivery_output.get("feishu_message_id") if isinstance(delivery_output, dict) else None,
        delivery_request_uuid=delivery_output.get("request_uuid") if isinstance(delivery_output, dict) else None,
        delivery_attempts=len(delivery_runs),
        last_delivery_at=delivery_run.created_at if delivery_run else None,
    )


def channel_label(value: str | None) -> str:
    labels = {
        "feishu": "飞书",
        "csv": "CSV",
        "local_json": "JSON",
        "json": "JSON",
        "local": "本地",
        "wecom": "企业微信",
        "dingtalk": "钉钉",
    }
    return labels.get(value or "", value or "-")


def display_name(name: str | None, fallback_id: str | None) -> str:
    if name and name != fallback_id:
        return name
    return fallback_id or name or "-"


def short_external_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 14:
        return value
    return f"{value[:6]}...{value[-4:]}"


def conversation_name_for_message(session: Session, message: MessageEvent | None) -> str | None:
    if message is None:
        return None
    conversation = session.get(Conversation, message.conversation_id)
    if conversation is None:
        return None
    return display_name(conversation.name, conversation.external_conversation_id)


def latest_run_for_message(session: Session, message_id: int | None) -> AgentRun | None:
    if message_id is None:
        return None
    return session.exec(
        select(AgentRun)
        .where(
            AgentRun.message_id == message_id,
            AgentRun.agent_type.notin_(["feishu_send_adapter", "feishu_stream_worker"]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()


def route_from_run(run: AgentRun | None) -> dict[str, Any]:
    if run is None:
        return {}
    prompt_route = (run.prompt_json or {}).get("route")
    if isinstance(prompt_route, dict):
        return prompt_route
    action_intent = (run.action_json or {}).get("intent")
    return {
        "intent": action_intent,
        "target_agent": run.agent_type,
        "risk_level": run.risk_level,
        "confidence": run.confidence,
    }


def related_objects_for_message(session: Session, message: MessageEvent) -> list[RelatedObjectRead]:
    objects: list[RelatedObjectRead] = []
    for ticket in session.exec(select(Ticket).where(Ticket.source_message_id == message.id)).all():
        objects.append(RelatedObjectRead(type="ticket", id=ticket.id or 0, label=ticket.title))
    for lead in session.exec(select(Lead).where(Lead.source_message_id == message.id)).all():
        objects.append(RelatedObjectRead(type="lead", id=lead.id or 0, label=lead.customer_name))
    for task in session.exec(select(FollowupTask).where(FollowupTask.source_message_id == message.id)).all():
        objects.append(RelatedObjectRead(type="task", id=task.id or 0, label=task.title))
    for candidate in session.exec(select(Candidate).where(Candidate.source_message_id == message.id)).all():
        objects.append(RelatedObjectRead(type="candidate", id=candidate.id or 0, label=candidate.name))
    for gap in session.exec(select(KnowledgeGap).where(KnowledgeGap.source_message_id == message.id)).all():
        objects.append(RelatedObjectRead(type="knowledge_gap", id=gap.id or 0, label=gap.question[:80]))
    return objects


def related_object_for_run(session: Session, run: AgentRun | None) -> RelatedObjectRead | None:
    if run is None or run.id is None:
        return None
    ticket = session.exec(select(Ticket).where(Ticket.agent_run_id == run.id)).first()
    if ticket is not None:
        return RelatedObjectRead(type="ticket", id=ticket.id or 0, label=ticket.title)
    lead = session.exec(select(Lead).where(Lead.agent_run_id == run.id)).first()
    if lead is not None:
        return RelatedObjectRead(type="lead", id=lead.id or 0, label=lead.customer_name)
    task = session.exec(select(FollowupTask).where(FollowupTask.agent_run_id == run.id)).first()
    if task is not None:
        return RelatedObjectRead(type="task", id=task.id or 0, label=task.title)
    candidate = session.exec(select(Candidate).where(Candidate.agent_run_id == run.id)).first()
    if candidate is not None:
        return RelatedObjectRead(type="candidate", id=candidate.id or 0, label=candidate.name)
    gap = session.exec(select(KnowledgeGap).where(KnowledgeGap.agent_run_id == run.id)).first()
    if gap is not None:
        return RelatedObjectRead(type="knowledge_gap", id=gap.id or 0, label=gap.question[:80])
    return None


def message_tracking(message: MessageEvent | None) -> dict[str, Any]:
    if message is None:
        return {}
    raw = message.raw_json or {}
    tracking = raw.get("workbuddy_message_tracking") if isinstance(raw.get("workbuddy_message_tracking"), dict) else {}
    if tracking:
        return dict(tracking)
    if message.message_type != "text":
        return {
            "traceable_non_text": True,
            "message_type": message.message_type,
            "message_type_label": message_type_label(message.message_type),
            "summary": message.text,
        }
    return {}


def message_type_label(message_type: str | None) -> str:
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
    return labels.get(message_type or "", message_type or "-")
