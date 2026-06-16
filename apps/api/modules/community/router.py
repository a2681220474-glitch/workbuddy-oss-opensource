from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, Conversation, FollowupTask, KnowledgeGap, Lead, MessageEvent, utc_now
from apps.api.modules.audit.service import append_audit_log


router = APIRouter()

COMMUNITY_CONTEXT_KEYWORDS = ["社群", "群里", "群内", "直播", "体验课", "训练营", "活动", "课程", "报名"]
HIGH_INTENT_KEYWORDS = ["怎么买", "购买", "报名", "价格", "优惠", "名额", "试用", "采购"]
UNANSWERED_KEYWORDS = ["请问", "怎么", "能不能", "可以吗", "有人吗", "入口", "?"]
RISK_KEYWORDS = ["没人回复", "投诉", "退款", "退货", "太差", "不好用", "失望", "风险", "质量问题"]


class CommunityApprovalDraftCreate(BaseModel):
    draft_content: str | None = None


@router.get("/overview")
def community_overview(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    messages = community_messages(session, tenant.id)
    leads = session.exec(
        select(Lead).where(Lead.tenant_id == tenant.id, Lead.interest == "社群高意向用户").order_by(Lead.score.desc(), Lead.created_at.desc())
    ).all()
    gaps = session.exec(
        select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id, KnowledgeGap.category == "community").order_by(KnowledgeGap.created_at.desc())
    ).all()
    tasks = session.exec(
        select(FollowupTask)
        .where(
            FollowupTask.tenant_id == tenant.id,
            (FollowupTask.task_type == "community_followup") | (FollowupTask.related_object_type == "community"),
        )
        .order_by(FollowupTask.created_at.desc(), FollowupTask.id.desc())
    ).all()
    risk_messages = [message for message in messages if is_risk_message(message)]
    conversations = build_conversation_summaries(session, tenant.id, messages, leads, gaps, tasks, risk_messages)

    return {
        "summary": {
            "community_messages": len(messages),
            "community_conversations": len(conversations),
            "high_intent_users": len(leads),
            "unanswered_questions": sum(1 for gap in gaps if gap.status == "pending"),
            "risk_messages": len(risk_messages),
            "open_tasks": sum(1 for task in tasks if task.status == "todo"),
        },
        "conversations": conversations,
        "high_intent_users": [serialize_lead(lead) for lead in leads[:12]],
        "unanswered_questions": [serialize_gap(gap) for gap in gaps[:12]],
        "risk_messages": [serialize_message(session, message) for message in risk_messages[:12]],
        "tasks": [serialize_task(task) for task in tasks[:16]],
    }


@router.post("/tasks/{task_id}/complete")
def complete_community_task(
    task_id: int,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    task = session.get(FollowupTask, task_id)
    if task is None or task.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.task_type != "community_followup" and task.related_object_type != "community":
        raise HTTPException(status_code=400, detail="Task is not a community task")
    task.status = "done"
    task.completed_at = utc_now()
    task.updated_at = utc_now()
    session.add(task)
    append_audit_log(
        session,
        tenant.id,
        "community_task_completed",
        f"{current_user.display_name} 完成社群任务 #{task.id}",
        operator=current_user,
        scope_type="task",
        scope_id=task.id,
        object_type="task",
        object_id=task.id,
        status=task.status,
        detail_json={"title": task.title},
    )
    session.commit()
    return {"task_id": task.id, "status": task.status}


@router.post("/messages/{message_id}/approval-draft")
def create_community_approval_draft(
    message_id: int,
    payload: CommunityApprovalDraftCreate,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    message = session.get(MessageEvent, message_id)
    if message is None or message.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Message not found")
    draft = payload.draft_content or community_reply_draft(message)
    run = AgentRun(
        tenant_id=tenant.id,
        message_id=message.id,
        agent_type="community_ops_agent",
        status="success",
        prompt_version="v0.8-community-ops-rules",
        prompt_json={"message_id": message.id, "action_type": "send_community_draft_to_approval"},
        model_provider="local",
        model_name="rule-community-assistant",
        model_output_json={"draft_content": draft, "source_text": message.text},
        action_json={
            "actions": [
                {
                    "action_type": "send_draft_to_approval",
                    "business_object": {"type": "message", "id": message.id, "label": message.sender_name},
                }
            ]
        },
        confidence=0.9,
        risk_level="medium" if is_risk_message(message) else "low",
    )
    session.add(run)
    session.flush()
    approval = Approval(tenant_id=tenant.id, agent_run_id=run.id, draft_content=draft)
    session.add(approval)
    session.commit()
    return {"message_id": message.id, "approval_id": approval.id, "agent_run_id": run.id}


def community_messages(session, tenant_id: int) -> list[MessageEvent]:
    rows = session.exec(
        select(MessageEvent).where(MessageEvent.tenant_id == tenant_id).order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc()).limit(120)
    ).all()
    runs = session.exec(
        select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.agent_type == "community_ops_agent")
    ).all()
    community_message_ids = {run.message_id for run in runs if run.message_id is not None}
    return [message for message in rows if message.id in community_message_ids or has_community_context(message.text)]


def has_community_context(text: str) -> bool:
    return any(keyword in text for keyword in COMMUNITY_CONTEXT_KEYWORDS)


def is_high_intent_message(message: MessageEvent) -> bool:
    return any(keyword in message.text for keyword in HIGH_INTENT_KEYWORDS)


def is_unanswered_message(message: MessageEvent) -> bool:
    return any(keyword in message.text for keyword in UNANSWERED_KEYWORDS)


def is_risk_message(message: MessageEvent) -> bool:
    return any(keyword in message.text for keyword in RISK_KEYWORDS)


def build_conversation_summaries(
    session,
    tenant_id: int,
    messages: list[MessageEvent],
    leads: list[Lead],
    gaps: list[KnowledgeGap],
    tasks: list[FollowupTask],
    risk_messages: list[MessageEvent],
) -> list[dict[str, Any]]:
    grouped: dict[int, list[MessageEvent]] = defaultdict(list)
    for message in messages:
        grouped[message.conversation_id].append(message)
    message_by_id = {message.id: message for message in messages}
    lead_counts = count_by_conversation(leads, message_by_id)
    gap_counts = count_by_conversation(gaps, message_by_id)
    risk_counts = Counter(message.conversation_id for message in risk_messages)
    task_counts = count_tasks_by_conversation(tasks, message_by_id)
    summaries = []
    for conversation_id, conversation_messages in grouped.items():
        conversation = session.get(Conversation, conversation_id)
        latest = max(conversation_messages, key=lambda message: message.received_at)
        summaries.append(
            {
                "conversation_id": conversation_id,
                "name": conversation.name if conversation else f"会话#{conversation_id}",
                "message_count": len(conversation_messages),
                "high_intent_count": lead_counts[conversation_id],
                "unanswered_count": gap_counts[conversation_id],
                "risk_count": risk_counts[conversation_id],
                "open_task_count": task_counts[conversation_id],
                "latest_message": latest.text[:160],
                "latest_at": latest.received_at.isoformat(),
                "activity_score": len(conversation_messages) * 2 + lead_counts[conversation_id] * 8 + gap_counts[conversation_id] * 5 + risk_counts[conversation_id] * 10,
            }
        )
    return sorted(summaries, key=lambda row: (row["risk_count"], row["high_intent_count"], row["activity_score"]), reverse=True)


def count_by_conversation(rows: list[Any], message_by_id: dict[int | None, MessageEvent]) -> Counter:
    counter: Counter = Counter()
    for row in rows:
        message = message_by_id.get(getattr(row, "source_message_id", None))
        if message is not None:
            counter[message.conversation_id] += 1
    return counter


def count_tasks_by_conversation(tasks: list[FollowupTask], message_by_id: dict[int | None, MessageEvent]) -> Counter:
    counter: Counter = Counter()
    for task in tasks:
        message = message_by_id.get(task.source_message_id)
        if message is not None:
            counter[message.conversation_id] += 1
    return counter


def serialize_lead(lead: Lead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "customer_name": lead.customer_name,
        "interest": lead.interest,
        "score": lead.score,
        "stage": lead.stage,
        "next_step": lead.next_step,
        "source_message_id": lead.source_message_id,
    }


def serialize_gap(gap: KnowledgeGap) -> dict[str, Any]:
    return {
        "id": gap.id,
        "question": gap.question,
        "suggested_answer": gap.suggested_answer,
        "status": gap.status,
        "occurrence_count": gap.occurrence_count,
        "source_message_id": gap.source_message_id,
    }


def serialize_task(task: FollowupTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_hint": task.due_hint,
        "summary": task.summary,
        "source_message_id": task.source_message_id,
        "related_object_type": task.related_object_type,
        "related_object_id": task.related_object_id,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def serialize_message(session, message: MessageEvent) -> dict[str, Any]:
    conversation = session.get(Conversation, message.conversation_id)
    return {
        "id": message.id,
        "sender_name": message.sender_name,
        "text": message.text,
        "conversation_id": message.conversation_id,
        "conversation_name": conversation.name if conversation else f"会话#{message.conversation_id}",
        "received_at": message.received_at.isoformat(),
        "risk_level": "high" if is_risk_message(message) else "low",
    }


def community_reply_draft(message: MessageEvent) -> str:
    if is_risk_message(message):
        return "您好，已收到您的反馈。我们会由人工同事优先核实，并尽快给出明确处理结果。"
    if is_high_intent_message(message):
        return "您好，看到您对这个方向比较感兴趣。我先帮您记录需求，人工确认后补充报名/购买方式和下一步建议。"
    if is_unanswered_message(message):
        return "您好，刚看到您的问题。我们先确认准确答案，稍后给您回复。"
    return "您好，消息已收到。我先帮您记录，确认后给您回复。"
