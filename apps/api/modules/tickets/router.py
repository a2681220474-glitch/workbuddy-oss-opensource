from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import AgentRun, KnowledgeGap, KnowledgeHit, KnowledgeItem, RuntimeSetting, Ticket, utc_now
from apps.api.modules.knowledge.router import snapshot_knowledge_item_version
from apps.api.modules.audit.service import append_audit_log
from apps.api.schemas import KnowledgeGapRead, KnowledgeItemRead, SlaConfigUpdate, TicketKnowledgeCreate, TicketRead, TicketUpdate


router = APIRouter()

SLA_SETTING_KEY = "support.sla.hours"
DEFAULT_SLA_HOURS = {"critical": 2, "high": 4, "medium": 24, "low": 48}
STATUS_TRANSITIONS = {
    "open": ["in_progress", "waiting_customer", "resolved", "closed"],
    "in_progress": ["waiting_customer", "resolved", "closed"],
    "waiting_customer": ["in_progress", "resolved", "closed"],
    "resolved": ["closed", "in_progress"],
    "closed": [],
}
STATUS_LABELS = {
    "open": "待处理",
    "in_progress": "处理中",
    "waiting_customer": "等客户",
    "resolved": "已解决",
    "closed": "已关闭",
}


@router.get("", response_model=list[TicketRead])
def list_tickets(
    session: SessionDep,
    tenant: TenantDep,
    status: str | None = None,
    priority: str | None = None,
) -> list[Ticket]:
    statement = select(Ticket).where(Ticket.tenant_id == tenant.id)
    if status:
        statement = statement.where(Ticket.status == status)
    if priority:
        statement = statement.where(Ticket.priority == priority)
    statement = statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    return list(session.exec(statement).all())


@router.get("/workflow")
def ticket_workflow(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    return {
        "statuses": [{"value": key, "label": STATUS_LABELS[key], "next": STATUS_TRANSITIONS[key]} for key in STATUS_TRANSITIONS],
        "transitions": STATUS_TRANSITIONS,
        "sla_hours": get_sla_config(session, tenant.id),
    }


@router.get("/sla-config")
def read_sla_config(session: SessionDep, tenant: TenantDep) -> dict[str, int]:
    return get_sla_config(session, tenant.id)


@router.patch("/sla-config")
def update_sla_config(
    payload: SlaConfigUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, int]:
    current = get_sla_config(session, tenant.id)
    for key, value in payload.model_dump(exclude_none=True).items():
        current[key] = int(value)
    setting = session.exec(
        select(RuntimeSetting).where(RuntimeSetting.tenant_id == tenant.id, RuntimeSetting.key == SLA_SETTING_KEY)
    ).first()
    if setting is None:
        setting = RuntimeSetting(tenant_id=tenant.id, key=SLA_SETTING_KEY, value=json.dumps(current))
    else:
        setting.value = json.dumps(current)
        setting.updated_at = utc_now()
    session.add(setting)
    append_audit_log(
        session,
        tenant.id,
        "ticket_sla_updated",
        f"{current_user.display_name} 更新客服 SLA 配置",
        operator=current_user,
        scope_type="config",
        object_type="ticket_sla",
        status="saved",
        detail_json=current,
    )
    session.commit()
    return current


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if payload.status is not None:
        allowed_next = STATUS_TRANSITIONS.get(ticket.status, [])
        if payload.status != ticket.status and payload.status not in allowed_next:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ticket transition: {ticket.status} -> {payload.status}",
            )
        ticket.status = payload.status
    if payload.priority is not None:
        ticket.priority = payload.priority
    ticket.updated_at = utc_now()
    session.add(ticket)
    append_audit_log(
        session,
        tenant.id,
        "ticket_updated",
        f"{current_user.display_name} 更新工单 #{ticket.id}",
        operator=current_user,
        scope_type="ticket",
        scope_id=ticket.id,
        object_type="ticket",
        object_id=ticket.id,
        status=ticket.status,
        detail_json={"priority": ticket.priority},
    )
    session.commit()
    session.refresh(ticket)
    return ticket


@router.get("/{ticket_id}/knowledge-suggestions")
def ticket_knowledge_suggestions(ticket_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    ticket = get_ticket(session, tenant.id, ticket_id)
    items = session.exec(
        select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant.id, KnowledgeItem.status == "published")
    ).all()
    scored = []
    for item in items:
        score = knowledge_score(ticket, item)
        if score > 0:
            scored.append({
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "score": score,
                "answer": item.answer,
            })
    scored.sort(key=lambda row: row["score"], reverse=True)
    for row in scored[:5]:
        record_knowledge_hit(session, tenant.id, ticket, row)
    if scored:
        session.commit()
    return {
        "ticket_id": ticket.id,
        "status": "hit" if scored else "miss",
        "matches": scored[:5],
        "suggested_question": ticket.title,
        "suggested_answer": best_answer(ticket, scored),
    }


@router.post("/{ticket_id}/knowledge", response_model=KnowledgeItemRead | KnowledgeGapRead)
def create_knowledge_from_ticket(
    ticket_id: int,
    payload: TicketKnowledgeCreate,
    session: SessionDep,
    tenant: TenantDep,
) -> KnowledgeItem | KnowledgeGap:
    ticket = get_ticket(session, tenant.id, ticket_id)
    source = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "summary": ticket.summary,
        "source_message_id": ticket.source_message_id,
    }
    if payload.mode == "item":
        item = KnowledgeItem(
            tenant_id=tenant.id,
            title=ticket.title[:240],
            answer=payload.answer or ticket.summary or "待补充标准答案。",
            category=payload.category[:80],
            status="published" if payload.publish else "draft",
        )
        session.add(item)
        session.flush()
        snapshot_knowledge_item_version(session, item, "ticket_publish", f"从工单#{ticket.id}沉淀知识")
        record_knowledge_action(session, tenant.id, ticket, "create_knowledge_item", {"item_id": item.id, **source})
        session.commit()
        session.refresh(item)
        return item

    gap = KnowledgeGap(
        tenant_id=tenant.id,
        source_message_id=ticket.source_message_id,
        agent_run_id=ticket.agent_run_id,
        question=ticket.title[:500],
        suggested_answer=payload.answer or ticket.summary or "",
        category=payload.category[:80],
        occurrence_count=1,
        status="pending",
        examples_json=[source],
    )
    session.add(gap)
    session.flush()
    record_knowledge_action(session, tenant.id, ticket, "create_knowledge_gap", {"gap_id": gap.id, **source})
    session.commit()
    session.refresh(gap)
    return gap


def get_ticket(session, tenant_id: int, ticket_id: int) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def get_sla_config(session, tenant_id: int) -> dict[str, int]:
    setting = session.exec(
        select(RuntimeSetting).where(RuntimeSetting.tenant_id == tenant_id, RuntimeSetting.key == SLA_SETTING_KEY)
    ).first()
    if setting is None:
        return dict(DEFAULT_SLA_HOURS)
    try:
        parsed = json.loads(setting.value)
    except json.JSONDecodeError:
        return dict(DEFAULT_SLA_HOURS)
    return {key: int(parsed.get(key, value)) for key, value in DEFAULT_SLA_HOURS.items()}


def knowledge_score(ticket: Ticket, item: KnowledgeItem) -> int:
    ticket_tokens = tokens(f"{ticket.title} {ticket.summary} {ticket.category}")
    item_tokens = tokens(f"{item.title} {item.answer} {item.category}")
    return len(ticket_tokens & item_tokens)


def tokens(value: str) -> set[str]:
    normalized = value.lower()
    words = {word for word in normalized.replace("/", " ").replace(":", " ").split() if len(word) >= 2}
    chinese_keywords = {
        keyword
        for keyword in ["退款", "登录", "发票", "导入", "报错", "失败", "账号", "权限", "知识库", "价格", "报价"]
        if keyword in value
    }
    return words | chinese_keywords


def best_answer(ticket: Ticket, scored: list[dict[str, Any]]) -> str:
    if scored:
        return str(scored[0].get("answer") or "")
    return ticket.summary or "当前知识库未命中，建议沉淀为知识缺口。"


def record_knowledge_hit(session, tenant_id: int, ticket: Ticket, match: dict[str, Any]) -> None:
    item_id = int(match.get("id") or 0)
    if not item_id or ticket.id is None:
        return
    existing = session.exec(
        select(KnowledgeHit).where(
            KnowledgeHit.tenant_id == tenant_id,
            KnowledgeHit.item_id == item_id,
            KnowledgeHit.source_object_type == "ticket",
            KnowledgeHit.source_object_id == ticket.id,
        )
    ).first()
    query_text = f"{ticket.title}\n{ticket.summary}".strip()
    if existing:
        existing.query_text = query_text
        existing.score = int(match.get("score") or 0)
        existing.answer_snapshot = str(match.get("answer") or "")
        existing.status = "suggested"
        session.add(existing)
        return
    session.add(
        KnowledgeHit(
            tenant_id=tenant_id,
            item_id=item_id,
            source_object_type="ticket",
            source_object_id=ticket.id,
            query_text=query_text,
            score=int(match.get("score") or 0),
            answer_snapshot=str(match.get("answer") or ""),
            status="suggested",
        )
    )


def record_knowledge_action(session, tenant_id: int, ticket: Ticket, action_type: str, payload: dict[str, Any]) -> None:
    session.add(
        AgentRun(
            tenant_id=tenant_id,
            message_id=ticket.source_message_id,
            agent_type="support_ticket_knowledge_agent",
            status="success",
            prompt_version="v0.6-support-knowledge-rules",
            prompt_json={"ticket_id": ticket.id, "action_type": action_type},
            model_provider="local",
            model_name="rule-knowledge-workflow",
            model_output_json=payload,
            action_json={"actions": [{"action_type": action_type, "business_object": {"type": "knowledge"}}]},
            confidence=1.0,
            risk_level="low",
        )
    )
