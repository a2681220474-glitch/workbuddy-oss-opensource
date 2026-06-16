from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Callable

from sqlmodel import Session, select

from apps.api.models import (
    AgentRun,
    Approval,
    Channel,
    Conversation,
    FollowupTask,
    ImportBatch,
    Lead,
    MessageEvent,
    Tenant,
    Ticket,
    utc_now,
)
from apps.api.schemas import ImportRecord


SUPPORT_KEYWORDS = ("退款", "投诉", "报错", "坏了", "无法", "不能用", "故障", "售后", "客服", "问题", "登录失败")
SALES_KEYWORDS = ("价格", "报价", "多少钱", "试用", "演示", "方案", "购买", "合同", "采购", "咨询")


def import_records(
    session: Session,
    tenant: Tenant,
    records: list[ImportRecord],
    source: str,
    filename: str | None = None,
) -> tuple[ImportBatch, list[MessageEvent]]:
    batch = ImportBatch(
        tenant_id=tenant.id,
        source=source,
        filename=filename,
        status="running",
        total_rows=len(records),
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    imported: list[MessageEvent] = []
    skipped_count = 0
    error_count = 0

    for index, record in enumerate(records, start=1):
        try:
            message = normalize_record(session, tenant, record, batch.id or 0, index)
            if message is None:
                skipped_count += 1
                continue
            imported.append(message)
            orchestrate_message(session, message)
        except Exception as exc:  # noqa: BLE001 - import should keep processing remaining rows.
            error_count += 1
            failure = AgentRun(
                tenant_id=tenant.id,
                agent_type="import_pipeline",
                status="failed",
                prompt_json={"source": source, "row_index": index},
                model_output_json={},
                action_json={},
                error_message=str(exc),
            )
            session.add(failure)
            session.commit()

    batch.imported_count = len(imported)
    batch.skipped_count = skipped_count
    batch.error_count = error_count
    batch.status = "completed" if error_count == 0 else "completed_with_errors"
    batch.completed_at = utc_now()
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch, imported


def normalize_record(
    session: Session,
    tenant: Tenant,
    record: ImportRecord,
    batch_id: int,
    row_index: int,
) -> MessageEvent | None:
    enrich_channel_record(session, tenant, record)
    channel = get_or_create_channel(session, tenant, record.channel)
    conversation = get_or_create_conversation(session, tenant, channel, record)
    received_at = record.timestamp or utc_now()
    external_message_id = record.external_message_id or stable_message_id(tenant.key, record, batch_id, row_index)

    existing = session.exec(
        select(MessageEvent).where(
            MessageEvent.tenant_id == tenant.id,
            MessageEvent.external_message_id == external_message_id,
        )
    ).first()
    if existing is not None:
        return None

    normalized = {
        "event_id": f"evt_{external_message_id}",
        "tenant_id": tenant.key,
        "channel": record.channel,
        "conversation_id": conversation.external_conversation_id,
        "conversation_type": conversation.type,
        "sender_id": record.sender_external_id or record.sender_name,
        "sender_name": record.sender_name,
        "sender_display_name": record.sender_name,
        "message_id": external_message_id,
        "message_type": record.message_type,
        "text": record.text,
        "timestamp": received_at.isoformat(),
        "conversation_name": conversation.name,
        "conversation_display_name": conversation.name,
    }
    message = MessageEvent(
        event_id=normalized["event_id"],
        tenant_id=tenant.id,
        channel_id=channel.id,
        conversation_id=conversation.id,
        external_message_id=external_message_id,
        sender_external_id=record.sender_external_id or f"local:{record.sender_name}",
        sender_name=record.sender_name,
        message_type=record.message_type,
        text=record.text,
        normalized_json=normalized,
        raw_json=record.raw_payload,
        received_at=received_at,
    )
    conversation.last_message_at = received_at
    session.add(conversation)
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def enrich_channel_record(session: Session, tenant: Tenant, record: ImportRecord) -> None:
    if record.channel != "feishu":
        return
    try:
        from apps.api.modules.channels.feishu_directory import FeishuUserResolver

        FeishuUserResolver(session, tenant).enrich_record(record)
    except Exception as exc:  # noqa: BLE001 - external directory lookup must not block message import.
        record.raw_payload.setdefault("workbuddy_resolved", {})
        record.raw_payload["workbuddy_resolved"]["directory_error"] = str(exc)


def get_or_create_channel(session: Session, tenant: Tenant, channel_type: str) -> Channel:
    channel = session.exec(
        select(Channel).where(
            Channel.tenant_id == tenant.id,
            Channel.type == channel_type,
            Channel.account_id == channel_type,
        )
    ).first()
    if channel is not None:
        return channel

    channel = Channel(
        tenant_id=tenant.id,
        type=channel_type,
        name=f"{channel_type} import",
        account_id=channel_type,
    )
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


def get_or_create_conversation(
    session: Session,
    tenant: Tenant,
    channel: Channel,
    record: ImportRecord,
) -> Conversation:
    conversation = session.exec(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.channel_id == channel.id,
            Conversation.external_conversation_id == record.conversation_id,
        )
    ).first()
    if conversation is not None:
        if record.conversation_name and conversation.name == conversation.external_conversation_id and record.conversation_name != conversation.name:
            conversation.name = record.conversation_name
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
        return conversation

    conversation = Conversation(
        tenant_id=tenant.id,
        channel_id=channel.id,
        external_conversation_id=record.conversation_id,
        type=record.conversation_type,
        name=record.conversation_name,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def orchestrate_message(session: Session, message: MessageEvent) -> None:
    external_runtime = load_agent_b_runtime()
    if external_runtime is not None:
        external_runtime(session=session, message=message)
        return
    run_phase0_fallback(session, message)


def load_agent_b_runtime() -> Callable[..., object] | None:
    try:
        from apps.api.modules.routing.orchestrator import handle_message_event

        return handle_message_event
    except ImportError:
        return None


def run_phase0_fallback(session: Session, message: MessageEvent) -> None:
    text = message.text or ""
    support_score = keyword_score(text, SUPPORT_KEYWORDS)
    sales_score = keyword_score(text, SALES_KEYWORDS)

    if support_score == 0 and sales_score == 0:
        create_agent_run(
            session=session,
            message=message,
            agent_type="router",
            intent="manual_inbox",
            confidence=0.35,
            risk_level="low",
            actions=[],
            output={"reason": "未命中 Phase 0 客服/销售规则，暂不生成对外回复。"},
        )
        return

    if support_score >= sales_score:
        create_support_ticket_flow(session, message, support_score)
    else:
        create_sales_lead_flow(session, message, sales_score)


def create_support_ticket_flow(session: Session, message: MessageEvent, score: int) -> None:
    priority = "high" if any(word in message.text for word in ("投诉", "退款", "无法", "不能用")) else "medium"
    draft_reply = (
        f"{message.sender_name}您好，我们已经记录到您的问题，会优先排查并尽快同步处理进展。"
        "如果方便，请补充出现问题的时间、截图或订单信息。"
    )
    action = {
        "action_type": "create_ticket",
        "priority": priority,
        "requires_approval": True,
        "reason": "消息命中客服/售后关键词，需要生成工单并准备回复草稿。",
        "business_object": {
            "type": "ticket",
            "fields": {
                "title": truncate_title(message.text, "客户问题待处理"),
                "customer_name": message.sender_name,
                "category": "support",
                "priority": priority,
                "status": "open",
            },
        },
        "draft_reply": draft_reply,
    }
    run = create_agent_run(
        session=session,
        message=message,
        agent_type="support_ticket_agent",
        intent="support_issue",
        confidence=min(0.92, 0.62 + score * 0.1),
        risk_level="medium" if priority == "high" else "low",
        actions=[action],
        output={"intent": "support_issue", "matched_keywords": score},
    )
    ticket = Ticket(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=run.id,
        title=action["business_object"]["fields"]["title"],
        customer_name=message.sender_name,
        category="support",
        priority=priority,
        status="open",
        summary=message.text,
    )
    approval = Approval(tenant_id=message.tenant_id, agent_run_id=run.id, draft_content=draft_reply)
    session.add(ticket)
    session.add(approval)
    session.commit()


def create_sales_lead_flow(session: Session, message: MessageEvent, score: int) -> None:
    priority = "high" if any(word in message.text for word in ("报价", "采购", "合同", "购买")) else "medium"
    draft_reply = (
        f"{message.sender_name}您好，我可以先发您一版方案和报价说明。"
        "也想了解一下您的团队规模、使用场景和预期上线时间，方便推荐更合适的版本。"
    )
    action = {
        "action_type": "create_lead",
        "priority": priority,
        "requires_approval": True,
        "reason": "消息命中询价/试用/方案关键词，需要创建销售线索并准备跟进草稿。",
        "business_object": {
            "type": "lead",
            "fields": {
                "customer_name": message.sender_name,
                "interest": infer_interest(message.text),
                "stage": "qualified",
                "score": 70 if priority == "high" else 55,
            },
        },
        "draft_reply": draft_reply,
        "next_steps": ["确认客户规模", "发送方案资料", "预约演示或报价沟通"],
    }
    run = create_agent_run(
        session=session,
        message=message,
        agent_type="sales_lead_agent",
        intent="sales_inquiry",
        confidence=min(0.92, 0.62 + score * 0.1),
        risk_level="medium",
        actions=[action],
        output={"intent": "sales_inquiry", "matched_keywords": score},
    )
    lead = Lead(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=run.id,
        customer_name=message.sender_name,
        interest=action["business_object"]["fields"]["interest"],
        stage="qualified",
        score=action["business_object"]["fields"]["score"],
        priority=priority,
        summary=message.text,
        next_step="确认客户规模并发送方案资料",
    )
    approval = Approval(tenant_id=message.tenant_id, agent_run_id=run.id, draft_content=draft_reply)
    session.add(lead)
    session.flush()
    task = FollowupTask(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=run.id,
        title="确认客户规模并发送方案资料",
        priority=priority,
        status="todo",
        related_object_type="lead",
        related_object_id=lead.id,
        due_hint="尽快",
        summary=message.text,
    )
    session.add(task)
    session.add(approval)
    session.commit()


def create_agent_run(
    session: Session,
    message: MessageEvent,
    agent_type: str,
    intent: str,
    confidence: float,
    risk_level: str,
    actions: list[dict],
    output: dict,
) -> AgentRun:
    started = time.perf_counter()
    action_json = {"intent": intent, "actions": actions}
    run = AgentRun(
        tenant_id=message.tenant_id,
        message_id=message.id,
        agent_type=agent_type,
        status="success",
        prompt_json={"message_id": message.id, "text": message.text, "strategy": "phase0_keyword_rules"},
        model_output_json=output,
        action_json=action_json,
        confidence=confidence,
        risk_level=risk_level,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def stable_message_id(tenant_key: str, record: ImportRecord, batch_id: int, row_index: int) -> str:
    raw = "|".join(
        [
            tenant_key,
            record.conversation_id,
            record.sender_external_id or record.sender_name,
            record.timestamp.isoformat() if record.timestamp else "",
            record.text,
            str(batch_id),
            str(row_index),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"local_{digest}"


def truncate_title(text: str, fallback: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return fallback
    return clean[:80]


def infer_interest(text: str) -> str:
    if "客服" in text:
        return "AI 客服方案"
    if "销售" in text:
        return "销售线索跟进方案"
    if "私域" in text or "社群" in text:
        return "私域社群运营方案"
    return "WorkBuddy OSS 方案咨询"
