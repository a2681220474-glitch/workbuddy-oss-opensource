from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import (
    BEIJING_TZ,
    AgentRun,
    Approval,
    Candidate,
    FollowupTask,
    KnowledgeGap,
    KnowledgeItem,
    Lead,
    MessageEvent,
    ProcessingRecord,
    Report,
    Ticket,
    utc_now,
)
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.display import enrich_approval, related_objects_for_message, route_from_run
from apps.api.modules.users.service import (
    apply_assignee_user,
    get_local_user,
    get_local_user_map,
    serialize_processing_record,
    serialize_task,
)
from apps.api.schemas import ProcessingRecordCreate, ProcessingRecordRead


router = APIRouter()

OBJECT_MODELS = {
    "ticket": Ticket,
    "lead": Lead,
    "task": FollowupTask,
    "candidate": Candidate,
    "knowledge_gap": KnowledgeGap,
    "knowledge_item": KnowledgeItem,
    "report": Report,
}

OBJECT_ALIASES = {
    "tickets": "ticket",
    "leads": "lead",
    "tasks": "task",
    "candidates": "candidate",
    "knowledge_gaps": "knowledge_gap",
    "knowledge_items": "knowledge_item",
    "reports": "report",
}


@router.get("")
def business_object_center(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    return {
        "counts": {
            "tickets": count_rows(session, Ticket, tenant.id),
            "leads": count_rows(session, Lead, tenant.id),
            "tasks": count_rows(session, FollowupTask, tenant.id),
            "candidates": count_rows(session, Candidate, tenant.id),
            "knowledge_gaps": count_rows(session, KnowledgeGap, tenant.id),
            "knowledge_items": count_rows(session, KnowledgeItem, tenant.id),
            "reports": count_rows(session, Report, tenant.id),
            "pending_approvals": session.exec(
                select(func.count()).select_from(Approval).where(Approval.tenant_id == tenant.id, Approval.status == "pending_review")
            ).one(),
        },
        "recent": {
            "tickets": recent(session, Ticket, tenant.id, "title"),
            "leads": recent(session, Lead, tenant.id, "customer_name"),
            "tasks": recent(session, FollowupTask, tenant.id, "title"),
            "candidates": recent(session, Candidate, tenant.id, "name"),
            "knowledge_gaps": recent(session, KnowledgeGap, tenant.id, "question"),
            "reports": recent(session, Report, tenant.id, "title"),
        },
    }


@router.get("/operations-summary")
def operations_summary(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    tickets = session.exec(select(Ticket).where(Ticket.tenant_id == tenant.id)).all()
    leads = session.exec(select(Lead).where(Lead.tenant_id == tenant.id)).all()
    tasks = session.exec(select(FollowupTask).where(FollowupTask.tenant_id == tenant.id)).all()
    candidates = session.exec(select(Candidate).where(Candidate.tenant_id == tenant.id)).all()
    gaps = session.exec(select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id)).all()
    reports = session.exec(select(Report).where(Report.tenant_id == tenant.id)).all()
    approvals = session.exec(select(Approval).where(Approval.tenant_id == tenant.id)).all()
    runs = session.exec(select(AgentRun).where(AgentRun.tenant_id == tenant.id)).all()

    open_tickets = [ticket for ticket in tickets if ticket.status in {"open", "in_progress", "waiting_customer"}]
    now = datetime.now(BEIJING_TZ)
    high_priority_open_tickets = [
        ticket for ticket in open_tickets if ticket.priority in {"high", "critical"}
    ]
    stale_open_tickets = [
        ticket
        for ticket in open_tickets
        if (now - ticket.created_at.replace(tzinfo=ticket.created_at.tzinfo or BEIJING_TZ)).total_seconds() >= 24 * 60 * 60
    ]
    lead_funnel = {
        stage: sum(1 for lead in leads if lead.stage == stage)
        for stage in ["new", "potential", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
    }
    top_leads = sorted(leads, key=lambda lead: (lead.score, lead.created_at), reverse=True)[:5]
    return {
        "support": {
            "open_tickets": len(open_tickets),
            "high_priority_open_tickets": len(high_priority_open_tickets),
            "stale_open_tickets": len(stale_open_tickets),
            "next_ticket_ids": [ticket.id for ticket in high_priority_open_tickets[:5]],
        },
        "sales": {
            "funnel": lead_funnel,
            "top_leads": [
                {
                    "id": lead.id,
                    "customer_name": lead.customer_name,
                    "stage": lead.stage,
                    "score": lead.score,
                    "next_step": lead.next_step,
                }
                for lead in top_leads
            ],
        },
        "knowledge": {
            "pending_gaps": sum(1 for gap in gaps if gap.status == "pending"),
            "accepted_gaps": sum(1 for gap in gaps if gap.status == "accepted"),
            "ignored_gaps": sum(1 for gap in gaps if gap.status == "ignored"),
        },
        "reports": {
            "total": len(reports),
            "latest": [
                {"id": report.id, "title": report.title, "report_type": report.report_type}
                for report in sorted(reports, key=lambda report: report.created_at, reverse=True)[:3]
            ],
        },
        "tasks": {
            "todo": sum(1 for task in tasks if task.status == "todo"),
            "done": sum(1 for task in tasks if task.status == "done"),
        },
        "agent_overview": build_agent_overview(tickets, leads, tasks, candidates=candidates, gaps=gaps, reports=reports, approvals=approvals, runs=runs),
        "risk_inbox": build_risk_inbox(tickets, leads, gaps, approvals, runs),
    }


@router.get("/{object_type}/{object_id}")
def business_object_detail(object_type: str, object_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    return build_business_object_detail(session, tenant.id, object_type, object_id)


@router.post("/{object_type}/{object_id}/records", response_model=ProcessingRecordRead)
def create_processing_record(
    object_type: str,
    object_id: int,
    payload: ProcessingRecordCreate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> ProcessingRecord:
    ensure_processing_access(current_user.role)
    normalized_type = normalize_object_type(object_type)
    obj = get_business_object(session, tenant.id, normalized_type, object_id)
    record = ProcessingRecord(
        tenant_id=tenant.id,
        object_type=normalized_type,
        object_id=object_id,
        action_type=payload.action_type,
        status=payload.status,
        due_hint=payload.due_hint,
        due_at=payload.due_at,
        next_step=payload.next_step,
        note=payload.note,
        operator_user_id=current_user.id,
        operator_username=current_user.username,
        operator_name=current_user.display_name,
    )
    if payload.assignee_user_id is not None:
        assignee_user = get_local_user(session, tenant.id, payload.assignee_user_id)
        if assignee_user is None:
            raise HTTPException(status_code=404, detail="Assignee user not found")
        apply_assignee_user(record, assignee_user)
    else:
        record.assignee_name = payload.assignee_name
    apply_processing_record(obj, normalized_type, record)
    session.add(record)
    session.add(obj)
    append_audit_log(
        session,
        tenant.id,
        "processing_record_created",
        f"新增{object_type_label(normalized_type)}处理记录 #{object_id}",
        operator=current_user,
        scope_type=normalized_type,
        scope_id=object_id,
        object_type=normalized_type,
        object_id=object_id,
        status=record.status,
        detail_json={
            "action_type": record.action_type,
            "assignee_user_id": record.assignee_user_id,
            "assignee_name": record.assignee_name,
            "next_step": record.next_step,
            "note": record.note,
        },
    )
    session.commit()
    session.refresh(record)
    assignee_map = get_local_user_map(session, tenant.id, [record.assignee_user_id])
    operator_map = get_local_user_map(session, tenant.id, [record.operator_user_id])
    return serialize_processing_record(record, assignee_map, operator_map)


def ensure_processing_access(role: str) -> None:
    if role == "readonly":
        raise HTTPException(status_code=403, detail="Readonly user cannot write processing records")


def count_rows(session, model, tenant_id: int) -> int:
    return session.exec(select(func.count()).select_from(model).where(model.tenant_id == tenant_id)).one()


def recent(session, model, tenant_id: int, label_field: str) -> list[dict[str, Any]]:
    rows = session.exec(
        select(model).where(model.tenant_id == tenant_id).order_by(model.created_at.desc(), model.id.desc()).limit(5)
    ).all()
    return [
        {
            "id": row.id,
            "label": getattr(row, label_field, f"#{row.id}"),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def build_agent_overview(
    tickets: list[Ticket],
    leads: list[Lead],
    tasks: list[FollowupTask],
    candidates: list[Candidate],
    gaps: list[KnowledgeGap],
    reports: list[Report],
    approvals: list[Approval],
    runs: list[AgentRun],
) -> list[dict[str, Any]]:
    report_counts = {
        "support_ticket_agent": sum(1 for report in reports if report.report_type == "support_daily"),
        "sales_lead_agent": sum(1 for report in reports if report.report_type == "sales_daily"),
        "community_ops_agent": sum(1 for report in reports if report.report_type == "community_daily"),
        "recruiting_hr_agent": sum(1 for report in reports if report.report_type == "recruiting_progress"),
    }
    return [
        {
            "agent_type": "support_ticket_agent",
            "label": "客服工单知识",
            "object_count": len(tickets),
            "pending_count": sum(1 for ticket in tickets if ticket.status in {"open", "in_progress", "waiting_customer"}),
            "risk_count": sum(1 for ticket in tickets if ticket.priority in {"high", "critical"} and ticket.status not in {"resolved", "closed"}),
            "approval_count": count_approvals_for_agent(approvals, runs, "support_ticket_agent"),
            "report_count": report_counts["support_ticket_agent"],
            "entry": "#tickets",
        },
        {
            "agent_type": "sales_lead_agent",
            "label": "销售线索跟进",
            "object_count": len(leads),
            "pending_count": sum(1 for lead in leads if lead.stage in {"new", "potential", "qualified", "contacted"}),
            "risk_count": sum(1 for lead in leads if lead.score >= 70 and lead.stage not in {"won", "lost"}),
            "approval_count": count_approvals_for_agent(approvals, runs, "sales_lead_agent"),
            "report_count": report_counts["sales_lead_agent"],
            "entry": "#leads",
        },
        {
            "agent_type": "community_ops_agent",
            "label": "私域社群运营",
            "object_count": sum(1 for task in tasks if task.task_type == "community_followup" or task.related_object_type == "community"),
            "pending_count": sum(1 for task in tasks if (task.task_type == "community_followup" or task.related_object_type == "community") and task.status == "todo"),
            "risk_count": sum(1 for gap in gaps if gap.category == "community" and gap.status == "pending"),
            "approval_count": count_approvals_for_agent(approvals, runs, "community_ops_agent"),
            "report_count": report_counts["community_ops_agent"],
            "entry": "#community",
        },
        {
            "agent_type": "recruiting_hr_agent",
            "label": "招聘与入职",
            "object_count": len(candidates),
            "pending_count": sum(1 for candidate in candidates if candidate.stage in {"screening", "interview", "offer", "onboarding"}),
            "risk_count": sum(1 for candidate in candidates if candidate.match_score < 60 or candidate.role == "待确认岗位"),
            "approval_count": count_approvals_for_agent(approvals, runs, "recruiting_hr_agent"),
            "report_count": report_counts["recruiting_hr_agent"],
            "entry": "#candidates",
        },
    ]


def build_risk_inbox(tickets: list[Ticket], leads: list[Lead], gaps: list[KnowledgeGap], approvals: list[Approval], runs: list[AgentRun]) -> dict[str, Any]:
    run_by_id = {run.id: run for run in runs}
    high_risk_approvals = [
        approval for approval in approvals
        if approval.status == "pending_review" and run_by_id.get(approval.agent_run_id) and run_by_id[approval.agent_run_id].risk_level in {"high", "critical"}
    ]
    return {
        "total": (
            sum(1 for ticket in tickets if ticket.priority in {"high", "critical"} and ticket.status not in {"resolved", "closed"})
            + sum(1 for lead in leads if lead.score >= 70 and lead.stage not in {"won", "lost"})
            + sum(1 for gap in gaps if gap.status == "pending")
            + len(high_risk_approvals)
        ),
        "support_risks": [ticket.id for ticket in tickets if ticket.priority in {"high", "critical"} and ticket.status not in {"resolved", "closed"}][:5],
        "sales_risks": [lead.id for lead in leads if lead.score >= 70 and lead.stage not in {"won", "lost"}][:5],
        "knowledge_risks": [gap.id for gap in gaps if gap.status == "pending"][:5],
        "approval_risks": [approval.id for approval in high_risk_approvals[:5]],
    }


def count_approvals_for_agent(approvals: list[Approval], runs: list[AgentRun], agent_type: str) -> int:
    run_ids = {run.id for run in runs if run.agent_type == agent_type}
    return sum(1 for approval in approvals if approval.agent_run_id in run_ids)


def build_business_object_detail(session, tenant_id: int, object_type: str, object_id: int) -> dict[str, Any]:
    normalized_type = normalize_object_type(object_type)
    obj = get_business_object(session, tenant_id, normalized_type, object_id)
    run = session.get(AgentRun, obj.agent_run_id) if getattr(obj, "agent_run_id", None) else None
    message = session.get(MessageEvent, obj.source_message_id) if getattr(obj, "source_message_id", None) else None
    approvals = session.exec(
        select(Approval)
        .where(Approval.tenant_id == tenant_id, Approval.agent_run_id == getattr(obj, "agent_run_id", None))
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    ).all() if getattr(obj, "agent_run_id", None) else []
    records = session.exec(
        select(ProcessingRecord)
        .where(
            ProcessingRecord.tenant_id == tenant_id,
            ProcessingRecord.object_type == normalized_type,
            ProcessingRecord.object_id == object_id,
        )
        .order_by(ProcessingRecord.created_at.desc(), ProcessingRecord.id.desc())
    ).all()
    related = related_objects_for_message(session, message) if message else []
    related = [item for item in related if not (item.type == normalized_type and item.id == object_id)]
    route = route_from_run(run)
    return {
        "object_type": normalized_type,
        "object_id": object_id,
        "label": object_label(normalized_type, obj),
        "object": serialize_business_object(normalized_type, obj),
        "source_message": message.model_dump() if message else None,
        "agent_run": run.model_dump() if run else None,
        "agent_definition": agent_definition(route.get("target_agent") or (run.agent_type if run else agent_for_object(normalized_type))),
        "approvals": [enrich_approval(session, approval).model_dump() for approval in approvals],
        "processing_records": serialize_processing_records(session, tenant_id, records),
        "related_objects": [item.model_dump() for item in related],
        "timeline": build_timeline(obj, normalized_type, message, run, approvals, records),
    }


def normalize_object_type(object_type: str) -> str:
    normalized = OBJECT_ALIASES.get(object_type, object_type)
    if normalized not in OBJECT_MODELS:
        raise HTTPException(status_code=404, detail=f"Unsupported business object type: {object_type}")
    return normalized


def get_business_object(session, tenant_id: int, object_type: str, object_id: int):
    model = OBJECT_MODELS[object_type]
    obj = session.get(model, object_id)
    if obj is None or obj.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Business object not found")
    return obj


def serialize_business_object(object_type: str, obj: Any) -> dict[str, Any]:
    if object_type == "task":
        return serialize_task(obj).model_dump()
    data = obj.model_dump()
    if hasattr(obj, "assignee_user_id"):
        data["assignee_user_id"] = getattr(obj, "assignee_user_id", None)
        data["assignee_username"] = getattr(obj, "assignee_username", None)
    return data


def apply_processing_record(obj: Any, object_type: str, record: ProcessingRecord) -> None:
    now = utc_now()
    if object_type == "ticket":
        if record.status:
            if record.status not in {"open", "in_progress", "waiting_customer", "resolved", "closed"}:
                raise HTTPException(status_code=400, detail="Invalid ticket status")
            obj.status = record.status
        obj.updated_at = now
        return
    if object_type == "lead":
        if record.status:
            if record.status not in {"new", "potential", "contacted", "qualified", "proposal", "negotiation", "won", "lost"}:
                raise HTTPException(status_code=400, detail="Invalid lead stage")
            obj.stage = record.status
        if record.next_step:
            obj.next_step = record.next_step
        obj.updated_at = now
        return
    if object_type == "task":
        if record.status:
            if record.status not in {"todo", "in_progress", "waiting", "done", "cancelled"}:
                raise HTTPException(status_code=400, detail="Invalid task status")
            obj.status = record.status
            obj.completed_at = now if record.status == "done" else None
        if record.assignee_user_id is not None:
            obj.assignee_user_id = record.assignee_user_id
            obj.assignee_username = record.assignee_username
            obj.assignee_name = record.assignee_name
        elif record.assignee_name is not None:
            obj.assignee_name = record.assignee_name or None
            if not record.assignee_name:
                obj.assignee_user_id = None
                obj.assignee_username = None
        if record.due_hint is not None:
            obj.due_hint = record.due_hint or None
        if record.due_at is not None:
            obj.due_at = record.due_at
        if record.note:
            obj.summary = record.note
        obj.updated_at = now
        return
    if object_type == "candidate":
        if record.status:
            if record.status not in {"screening", "interview", "offer", "onboarding", "hired", "rejected"}:
                raise HTTPException(status_code=400, detail="Invalid candidate stage")
            obj.stage = record.status
        if record.note:
            obj.summary = record.note
        obj.updated_at = now
        return
    if object_type == "knowledge_gap":
        if record.status:
            if record.status not in {"pending", "accepted", "ignored"}:
                raise HTTPException(status_code=400, detail="Invalid knowledge gap status")
            obj.status = record.status
        obj.updated_at = now
        return
    if object_type == "knowledge_item":
        if record.status:
            if record.status not in {"draft", "pending_review", "published", "archived"}:
                raise HTTPException(status_code=400, detail="Invalid knowledge item status")
            obj.status = record.status
        obj.updated_at = now


def build_timeline(
    obj: Any,
    object_type: str,
    message: MessageEvent | None,
    run: AgentRun | None,
    approvals: list[Approval],
    records: list[ProcessingRecord],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if message:
        events.append({
            "key": f"message-{message.id}",
            "type": "message",
            "title": "收到来源消息",
            "description": message.text,
            "created_at": message.received_at.isoformat(),
            "target": {"type": "message", "id": message.id},
        })
    if run:
        route = route_from_run(run)
        events.append({
            "key": f"run-{run.id}",
            "type": "agent_run",
            "title": "Agent Router 生成运行记录",
            "description": route.get("reason") or f"{run.agent_type} / {route.get('intent') or '未标注意图'}",
            "created_at": run.created_at.isoformat(),
            "target": {"type": "agent_run", "id": run.id},
            "metadata": {
                "agent_type": run.agent_type,
                "intent": route.get("intent"),
                "confidence": route.get("confidence", run.confidence),
                "risk_level": route.get("risk_level", run.risk_level),
            },
        })
    events.append({
        "key": f"object-{object_type}-{obj.id}",
        "type": "business_object",
        "title": f"生成{object_type_label(object_type)}",
        "description": object_label(object_type, obj),
        "created_at": obj.created_at.isoformat(),
        "target": {"type": object_type, "id": obj.id},
    })
    for approval in approvals:
        events.append({
            "key": f"approval-{approval.id}",
            "type": "approval",
            "title": approval_title(approval),
            "description": approval.final_content or approval.draft_content,
            "created_at": (approval.operated_at or approval.created_at).isoformat(),
            "target": {"type": "approval", "id": approval.id},
            "metadata": {"status": approval.status, "sent_at": approval.sent_at.isoformat() if approval.sent_at else None},
        })
    for record in records:
        events.append({
            "key": f"record-{record.id}",
            "type": "processing_record",
            "title": record_title(record),
            "description": record.note or record.next_step or "",
            "created_at": record.created_at.isoformat(),
            "metadata": {
                "status": record.status,
                "assignee_name": record.assignee_name,
                "assignee_username": record.assignee_username,
                "due_hint": record.due_hint,
                "due_at": record.due_at.isoformat() if record.due_at else None,
                "operator_name": record.operator_name,
                "operator_username": record.operator_username,
            },
        })
    return sorted(events, key=lambda item: item.get("created_at") or "")


def approval_title(approval: Approval) -> str:
    labels = {
        "pending_review": "审批草稿待处理",
        "approved": "审批已通过",
        "edited": "审批编辑后通过",
        "rejected": "审批已拒绝",
        "sent": "审批回复已发送",
    }
    return labels.get(approval.status, f"审批状态：{approval.status}")


def record_title(record: ProcessingRecord) -> str:
    labels = {
        "note": "新增处理记录",
        "assign": "分配负责人",
        "status_change": "更新处理状态",
        "next_step": "更新下一步",
        "complete": "完成处理",
        "cancel": "取消处理",
    }
    return labels.get(record.action_type, record.action_type)


def object_label(object_type: str, obj: Any) -> str:
    if object_type == "ticket":
        return obj.title
    if object_type == "lead":
        return obj.customer_name
    if object_type == "task":
        return obj.title
    if object_type == "candidate":
        return obj.name
    if object_type == "knowledge_gap":
        return obj.question[:80]
    if object_type == "knowledge_item":
        return obj.title
    if object_type == "report":
        return obj.title
    return f"{object_type}#{obj.id}"


def serialize_processing_records(session, tenant_id: int, records: list[ProcessingRecord]) -> list[dict[str, Any]]:
    assignee_map = get_local_user_map(session, tenant_id, [record.assignee_user_id for record in records])
    operator_map = get_local_user_map(session, tenant_id, [record.operator_user_id for record in records])
    return [
        serialize_processing_record(record, assignee_map, operator_map).model_dump()
        for record in records
    ]


def object_type_label(object_type: str) -> str:
    labels = {
        "ticket": "工单",
        "lead": "线索",
        "task": "任务",
        "candidate": "候选人",
        "knowledge_gap": "知识缺口",
        "knowledge_item": "知识条目",
        "report": "报告",
    }
    return labels.get(object_type, object_type)


def agent_for_object(object_type: str) -> str:
    mapping = {
        "ticket": "support_ticket_agent",
        "lead": "sales_lead_agent",
        "task": "community_ops_agent",
        "candidate": "recruiting_hr_agent",
        "knowledge_gap": "support_ticket_agent",
        "knowledge_item": "support_ticket_agent",
        "report": "report_agent",
    }
    return mapping.get(object_type, "manual_inbox_agent")


def agent_definition(agent_type: str | None) -> dict[str, Any]:
    definitions = {
        "support_ticket_agent": {
            "name": "客服工单知识 Agent",
            "responsibility": "把客户问题、投诉、故障和知识缺口转成可跟踪工单，并推动知识沉淀。",
            "inputs": ["MessageEvent", "工单状态", "知识库条目", "SLA 配置"],
            "outputs": ["Ticket", "KnowledgeGap", "KnowledgeItem", "Approval"],
            "llm_usage": "规则能识别时优先走规则；低置信度分类、回复草稿和知识建议可调用配置中心的大模型。",
            "failure_handling": "模型失败时保留 AgentRun 错误，并把消息转入人工收件箱或待处理工单。",
            "approval_policy": "对外回复、投诉/退款/高风险内容默认进入审批队列。",
        },
        "sales_lead_agent": {
            "name": "销售线索跟进 Agent",
            "responsibility": "从询价、方案、预算和购买意向消息里生成线索、评分和下一步跟进动作。",
            "inputs": ["MessageEvent", "Lead", "销售阶段", "跟进任务"],
            "outputs": ["Lead", "FollowupTask", "Approval", "Report"],
            "llm_usage": "关键词先路由；线索评分、话术草稿和不确定意图可调用大模型辅助。",
            "failure_handling": "分类失败时降低置信度，进入人工复核；不会自动承诺价格。",
            "approval_policy": "报价、折扣、方案承诺和对外话术默认审批。",
        },
        "community_ops_agent": {
            "name": "私域社群运营 Agent",
            "responsibility": "识别群里的高意向、未回复问题和风险消息，生成社群任务和回复草稿。",
            "inputs": ["MessageEvent", "Conversation", "KnowledgeGap", "FollowupTask"],
            "outputs": ["FollowupTask", "KnowledgeGap", "Approval", "Report"],
            "llm_usage": "社群高意向和风险优先规则判断；总结、回复草稿和低置信度分类可用大模型。",
            "failure_handling": "不能判断时创建人工跟进任务，并保留原始消息上下文。",
            "approval_policy": "群内对外回复、敏感风险消息和低置信度草稿默认审批。",
        },
        "recruiting_hr_agent": {
            "name": "招聘入职 Agent",
            "responsibility": "把 JD、简历、候选人沟通转成候选人档案、匹配分析、面试问题和入职清单。",
            "inputs": ["MessageEvent", "JD 文本", "简历文本", "Candidate"],
            "outputs": ["Candidate", "FollowupTask", "Approval", "Report"],
            "llm_usage": "结构化 JD/简历、匹配分析和面试题生成可调用大模型；阶段推进由人工确认。",
            "failure_handling": "解析失败时保留原文和缺失项，交给 HR 手工补充。",
            "approval_policy": "Offer、薪资、录用/拒绝等外发内容必须审批。",
        },
        "report_agent": {
            "name": "报告 Agent",
            "responsibility": "汇总业务对象、审批、任务和知识缺口，生成日报或进度报告。",
            "inputs": ["Ticket", "Lead", "FollowupTask", "Candidate", "KnowledgeGap"],
            "outputs": ["Report"],
            "llm_usage": "当前以规则汇总为主，后续可用大模型润色和提炼风险。",
            "failure_handling": "数据不足时生成带缺口提示的报告。",
            "approval_policy": "内部报告可自动生成；对外推送前需按渠道策略确认。",
        },
        "manual_inbox_agent": {
            "name": "人工收件箱 Agent",
            "responsibility": "承接低置信度、未知意图或暂不适合自动处理的消息。",
            "inputs": ["MessageEvent", "AgentRun"],
            "outputs": ["FollowupTask", "Approval"],
            "llm_usage": "只在需要辅助分类或总结上下文时调用大模型。",
            "failure_handling": "保留原始消息和错误原因，等待人工处理。",
            "approval_policy": "人工确认后再进入外发流程。",
        },
    }
    return definitions.get(agent_type or "", definitions["manual_inbox_agent"])
