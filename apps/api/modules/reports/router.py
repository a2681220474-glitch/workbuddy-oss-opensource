from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import func, select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import BEIJING_TZ, AgentRun, Candidate, FollowupTask, KnowledgeGap, Lead, MessageEvent, Report, RuntimeSetting, Ticket
from apps.api.schemas import ReportRead


router = APIRouter()


class ReportGenerateRequest(BaseModel):
    report_type: str = Field(default="operations_daily", pattern="^(operations_daily|community_daily|support_daily|sales_daily|recruiting_progress|knowledge_gap)$")
    scope_type: str = "tenant"
    scope_id: str | None = None


@router.get("", response_model=list[ReportRead])
def list_reports(session: SessionDep, tenant: TenantDep, report_type: str | None = None) -> list[Report]:
    statement = select(Report).where(Report.tenant_id == tenant.id)
    if report_type:
        statement = statement.where(Report.report_type == report_type)
    statement = statement.order_by(Report.created_at.desc(), Report.id.desc())
    return list(session.exec(statement).all())


@router.post("/generate", response_model=ReportRead)
def generate_report(payload: ReportGenerateRequest, session: SessionDep, tenant: TenantDep) -> Report:
    report = create_report(
        session=session,
        tenant_id=tenant.id,
        report_type=payload.report_type,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    session.commit()
    session.refresh(report)
    return report


def create_report(
    session,
    tenant_id: int,
    report_type: str,
    scope_type: str = "tenant",
    scope_id: str | None = None,
) -> Report:
    data = build_report_data(session, tenant_id, report_type)
    run = AgentRun(
        tenant_id=tenant_id,
        agent_type="report_agent",
        status="success",
        prompt_version=report_prompt_version(report_type),
        prompt_json={"report_type": report_type, "scope_type": scope_type, "scope_id": scope_id},
        model_provider="local",
        model_name="rule-report-generator",
        model_output_json=data,
        action_json={"actions": [{"action_type": "send_internal_report", "business_object": {"type": "report"}}]},
        confidence=1.0,
        risk_level="low",
    )
    session.add(run)
    session.flush()
    report = Report(
        tenant_id=tenant_id,
        agent_run_id=run.id,
        report_type=report_type,
        scope_type=scope_type,
        scope_id=scope_id,
        title=data["title"],
        summary=data["summary"],
        metrics_json=data["metrics"],
        sections_json=data["sections"],
        source_message_ids=data["source_message_ids"],
    )
    session.add(report)
    return report


def build_report_data(session, tenant_id: int, report_type: str) -> dict[str, Any]:
    messages = session.exec(
        select(MessageEvent).where(MessageEvent.tenant_id == tenant_id).order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc()).limit(80)
    ).all()
    tickets = session.exec(select(Ticket).where(Ticket.tenant_id == tenant_id).order_by(Ticket.created_at.desc()).limit(30)).all()
    leads = session.exec(select(Lead).where(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc()).limit(30)).all()
    tasks = session.exec(select(FollowupTask).where(FollowupTask.tenant_id == tenant_id).order_by(FollowupTask.created_at.desc()).limit(30)).all()
    candidates = session.exec(select(Candidate).where(Candidate.tenant_id == tenant_id).order_by(Candidate.created_at.desc()).limit(30)).all()
    gaps = session.exec(select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant_id).order_by(KnowledgeGap.created_at.desc()).limit(30)).all()
    channel_counter = Counter(str((message.normalized_json or {}).get("channel") or "local") for message in messages)
    metrics = {
        "messages": count_rows(session, MessageEvent, tenant_id),
        "tickets": count_rows(session, Ticket, tenant_id),
        "leads": count_rows(session, Lead, tenant_id),
        "tasks": count_rows(session, FollowupTask, tenant_id),
        "candidates": count_rows(session, Candidate, tenant_id),
        "knowledge_gaps": count_rows(session, KnowledgeGap, tenant_id),
        "channels": dict(channel_counter),
    }
    if report_type == "support_daily":
        metrics.update(support_metrics(session, tenant_id, tickets))
    if report_type == "sales_daily":
        metrics.update(sales_metrics(leads))
    if report_type == "community_daily":
        metrics.update(community_metrics(messages, leads, tasks, gaps))
    if report_type == "recruiting_progress":
        metrics.update(recruiting_metrics(candidates, tasks))
    report_labels = {
        "operations_daily": "业务运营日报",
        "community_daily": "社群运营日报",
        "support_daily": "客服日报",
        "sales_daily": "销售跟进日报",
        "recruiting_progress": "招聘进度报告",
        "knowledge_gap": "知识缺口报告",
    }
    if report_type == "support_daily":
        sections = support_sections(session, tenant_id, tickets, gaps)
    elif report_type == "sales_daily":
        sections = sales_sections(leads, tasks)
    elif report_type == "community_daily":
        sections = community_sections(messages, leads, tasks, gaps)
    elif report_type == "recruiting_progress":
        sections = recruiting_sections(candidates, tasks)
    else:
        sections = [
            {"title": "重点消息", "items": [message.text[:160] for message in messages[:8]]},
            {"title": "待处理工单", "items": [f"{ticket.priority} / {ticket.title}" for ticket in tickets[:6]]},
            {"title": "高意向线索", "items": [f"{lead.customer_name} / {lead.interest} / {lead.score}" for lead in leads[:6]]},
            {"title": "待办任务", "items": [f"{task.priority} / {task.title}" for task in tasks[:6]]},
            {"title": "候选人与入职", "items": [f"{candidate.name} / {candidate.role} / {candidate.match_score}" for candidate in candidates[:6]]},
            {"title": "知识缺口", "items": [gap.question[:160] for gap in gaps[:6]]},
        ]
    summary = (
        f"共处理 {metrics['messages']} 条消息，形成 {metrics['tickets']} 个工单、"
        f"{metrics['leads']} 条线索、{metrics['tasks']} 个任务、{metrics['candidates']} 个候选人，"
        f"当前知识缺口 {metrics['knowledge_gaps']} 条。"
    )
    return {
        "title": report_labels.get(report_type, report_type),
        "summary": summary,
        "metrics": metrics,
        "sections": sections,
        "source_message_ids": [message.id for message in messages[:30] if message.id is not None],
    }


def count_rows(session, model, tenant_id: int) -> int:
    return session.exec(select(func.count()).select_from(model).where(model.tenant_id == tenant_id)).one()


def report_prompt_version(report_type: str) -> str:
    if report_type == "community_daily":
        return "v0.8-community-report-rules"
    if report_type == "recruiting_progress":
        return "v0.9-recruiting-report-rules"
    return "v0.6-report-rules"


def support_metrics(session, tenant_id: int, tickets: list[Ticket]) -> dict[str, Any]:
    sla = support_sla_config(session, tenant_id)
    open_statuses = {"open", "in_progress", "waiting_customer"}
    open_tickets = [ticket for ticket in tickets if ticket.status in open_statuses]
    breached = [ticket for ticket in open_tickets if ticket_wait_hours(ticket) >= sla.get(ticket.priority, sla["medium"])]
    return {
        "support_open_tickets": len(open_tickets),
        "support_resolved_tickets": sum(1 for ticket in tickets if ticket.status == "resolved"),
        "support_closed_tickets": sum(1 for ticket in tickets if ticket.status == "closed"),
        "support_sla_breached": len(breached),
        "support_sla_config": sla,
        "support_by_status": {status: sum(1 for ticket in tickets if ticket.status == status) for status in ["open", "in_progress", "waiting_customer", "resolved", "closed"]},
        "support_by_priority": {priority: sum(1 for ticket in tickets if ticket.priority == priority) for priority in ["critical", "high", "medium", "low"]},
    }


def support_sections(session, tenant_id: int, tickets: list[Ticket], gaps: list[KnowledgeGap]) -> list[dict[str, Any]]:
    sla = support_sla_config(session, tenant_id)
    open_tickets = [ticket for ticket in tickets if ticket.status in {"open", "in_progress", "waiting_customer"}]
    breached = [ticket for ticket in open_tickets if ticket_wait_hours(ticket) >= sla.get(ticket.priority, sla["medium"])]
    return [
        {"title": "SLA 风险工单", "items": [f"{ticket.priority} / {ticket_wait_hours(ticket)}h / {ticket.title}" for ticket in breached[:8]]},
        {"title": "待处理工单", "items": [f"{ticket.status} / {ticket.priority} / {ticket.title}" for ticket in open_tickets[:8]]},
        {"title": "已解决或关闭", "items": [f"{ticket.status} / {ticket.customer_name} / {ticket.title}" for ticket in tickets if ticket.status in {"resolved", "closed"}][:8]},
        {"title": "知识缺口", "items": [f"{gap.category} / {gap.question[:140]}" for gap in gaps[:8]]},
        {"title": "SLA 配置", "items": [f"{priority}: {hours}h" for priority, hours in sla.items()]},
    ]


def support_sla_config(session, tenant_id: int) -> dict[str, int]:
    defaults = {"critical": 2, "high": 4, "medium": 24, "low": 48}
    setting = session.exec(
        select(RuntimeSetting).where(RuntimeSetting.tenant_id == tenant_id, RuntimeSetting.key == "support.sla.hours")
    ).first()
    if setting is None:
        return defaults
    try:
        import json

        parsed = json.loads(setting.value)
    except json.JSONDecodeError:
        return defaults
    return {key: int(parsed.get(key, value)) for key, value in defaults.items()}


def ticket_wait_hours(ticket: Ticket) -> int:
    created = ticket.created_at.replace(tzinfo=ticket.created_at.tzinfo or BEIJING_TZ)
    return int((datetime.now(BEIJING_TZ) - created).total_seconds() // 3600)


def sales_metrics(leads: list[Lead]) -> dict[str, Any]:
    return {
        "sales_high_intent": sum(1 for lead in leads if lead.score >= 70),
        "sales_stalled": sum(1 for lead in leads if lead_is_stalled(lead)),
        "sales_need_followup_today": sum(1 for lead in leads if lead.stage in {"new", "potential", "qualified", "contacted"}),
        "sales_won": sum(1 for lead in leads if lead.stage == "won"),
        "sales_lost": sum(1 for lead in leads if lead.stage == "lost"),
        "sales_by_stage": {
            stage: sum(1 for lead in leads if lead.stage == stage)
            for stage in ["new", "potential", "qualified", "contacted", "proposal", "negotiation", "won", "lost"]
        },
        "sales_by_priority": {
            priority: sum(1 for lead in leads if lead.priority == priority)
            for priority in ["critical", "high", "medium", "low"]
        },
    }


def sales_sections(leads: list[Lead], tasks: list[FollowupTask]) -> list[dict[str, Any]]:
    high_intent = sorted([lead for lead in leads if lead.score >= 70], key=lambda lead: lead.score, reverse=True)
    stalled = [lead for lead in leads if lead_is_stalled(lead)]
    today_followup = [lead for lead in leads if lead.stage in {"new", "potential", "qualified", "contacted"}]
    return [
        {"title": "高意向线索", "items": [format_lead(lead) for lead in high_intent[:8]]},
        {"title": "今日应跟进", "items": [f"{lead.stage} / {lead.customer_name} / {lead.next_step or '补充下一步'}" for lead in today_followup[:8]]},
        {"title": "停滞线索", "items": [f"{lead.customer_name} / {lead.stage} / {lead_wait_hours(lead)}h 未更新" for lead in stalled[:8]]},
        {"title": "方案与谈判", "items": [format_lead(lead) for lead in leads if lead.stage in {"proposal", "negotiation"}][:8]},
        {"title": "赢单与输单", "items": [format_lead(lead) for lead in leads if lead.stage in {"won", "lost"}][:8]},
        {"title": "销售待办", "items": [f"{task.priority} / {task.title}" for task in tasks if task.related_object_type == "lead" and task.status == "todo"][:8]},
    ]


def format_lead(lead: Lead) -> str:
    return f"{lead.customer_name} / {lead.interest} / {lead.stage} / {lead.score}"


def lead_is_stalled(lead: Lead) -> bool:
    if lead.stage in {"proposal", "negotiation", "won", "lost"}:
        return False
    return lead_wait_hours(lead) >= 24


def lead_wait_hours(lead: Lead) -> int:
    updated = lead.updated_at.replace(tzinfo=lead.updated_at.tzinfo or BEIJING_TZ)
    return int((datetime.now(BEIJING_TZ) - updated).total_seconds() // 3600)


def community_metrics(messages: list[MessageEvent], leads: list[Lead], tasks: list[FollowupTask], gaps: list[KnowledgeGap]) -> dict[str, Any]:
    community_messages = [message for message in messages if is_community_message(message)]
    community_conversations = {message.conversation_id for message in community_messages}
    community_leads = [lead for lead in leads if lead.interest == "社群高意向用户"]
    community_tasks = [task for task in tasks if task.task_type == "community_followup" or task.related_object_type == "community"]
    community_gaps = [gap for gap in gaps if gap.category == "community"]
    return {
        "community_messages": len(community_messages),
        "community_conversations": len(community_conversations),
        "community_high_intent_users": len(community_leads),
        "community_unanswered_questions": sum(1 for gap in community_gaps if gap.status == "pending"),
        "community_risk_messages": sum(1 for message in community_messages if is_community_risk(message)),
        "community_open_tasks": sum(1 for task in community_tasks if task.status == "todo"),
    }


def community_sections(messages: list[MessageEvent], leads: list[Lead], tasks: list[FollowupTask], gaps: list[KnowledgeGap]) -> list[dict[str, Any]]:
    community_messages = [message for message in messages if is_community_message(message)]
    community_leads = [lead for lead in leads if lead.interest == "社群高意向用户"]
    community_tasks = [task for task in tasks if task.task_type == "community_followup" or task.related_object_type == "community"]
    community_gaps = [gap for gap in gaps if gap.category == "community"]
    risk_messages = [message for message in community_messages if is_community_risk(message)]
    return [
        {"title": "高意向用户", "items": [f"{lead.customer_name} / {lead.score} / {lead.next_step or '待跟进'}" for lead in community_leads[:8]]},
        {"title": "未回复问题", "items": [f"{gap.status} / {gap.question[:140]}" for gap in community_gaps[:8]]},
        {"title": "风险消息", "items": [f"{message.sender_name} / {message.text[:140]}" for message in risk_messages[:8]]},
        {"title": "社群任务", "items": [f"{task.status} / {task.priority} / {task.title}" for task in community_tasks[:8]]},
        {"title": "群活跃概览", "items": format_community_activity(community_messages)},
    ]


def is_community_message(message: MessageEvent) -> bool:
    text = message.text
    return any(keyword in text for keyword in ["社群", "群里", "群内", "直播", "体验课", "训练营", "活动", "课程", "报名"])


def is_community_risk(message: MessageEvent) -> bool:
    return any(keyword in message.text for keyword in ["没人回复", "投诉", "退款", "退货", "太差", "不好用", "失望", "质量问题"])


def format_community_activity(messages: list[MessageEvent]) -> list[str]:
    counter = Counter(message.conversation_id for message in messages)
    return [f"会话#{conversation_id}: {count} 条社群相关消息" for conversation_id, count in counter.most_common(8)]


def recruiting_metrics(candidates: list[Candidate], tasks: list[FollowupTask]) -> dict[str, Any]:
    recruiting_tasks = [task for task in tasks if task.task_type == "recruiting_followup" or task.related_object_type == "candidate"]
    return {
        "recruiting_candidates": len(candidates),
        "recruiting_high_match": sum(1 for candidate in candidates if candidate.match_score >= 70),
        "recruiting_need_interview": sum(1 for candidate in candidates if candidate.stage in {"screening", "interview"}),
        "recruiting_offer": sum(1 for candidate in candidates if candidate.stage == "offer"),
        "recruiting_onboarding": sum(1 for candidate in candidates if candidate.stage == "onboarding"),
        "recruiting_hired": sum(1 for candidate in candidates if candidate.stage == "hired"),
        "recruiting_rejected": sum(1 for candidate in candidates if candidate.stage == "rejected"),
        "recruiting_open_tasks": sum(1 for task in recruiting_tasks if task.status == "todo"),
        "recruiting_by_stage": {
            stage: sum(1 for candidate in candidates if candidate.stage == stage)
            for stage in ["screening", "interview", "offer", "onboarding", "hired", "rejected"]
        },
    }


def recruiting_sections(candidates: list[Candidate], tasks: list[FollowupTask]) -> list[dict[str, Any]]:
    recruiting_tasks = [task for task in tasks if task.task_type == "recruiting_followup" or task.related_object_type == "candidate"]
    high_match = sorted(candidates, key=lambda candidate: candidate.match_score, reverse=True)
    onboarding = [candidate for candidate in candidates if candidate.stage in {"offer", "onboarding", "hired"}]
    risks = [candidate for candidate in candidates if candidate.match_score < 60 or candidate.role == "待确认岗位" or candidate.stage == "rejected"]
    return [
        {"title": "候选人漏斗", "items": format_candidate_funnel(candidates)},
        {"title": "高匹配候选人", "items": [format_candidate(candidate) for candidate in high_match[:8]]},
        {"title": "待面试/待推进", "items": [format_candidate(candidate) for candidate in candidates if candidate.stage in {"screening", "interview"}][:8]},
        {"title": "Offer 与入职准备", "items": [format_candidate(candidate) for candidate in onboarding[:8]]},
        {"title": "风险候选人", "items": [format_candidate(candidate) for candidate in risks[:8]]},
        {"title": "招聘待办", "items": [f"{task.status} / {task.priority} / {task.title}" for task in recruiting_tasks[:8]]},
    ]


def format_candidate(candidate: Candidate) -> str:
    return f"{candidate.name} / {candidate.role} / {candidate.stage} / {candidate.match_score}"


def format_candidate_funnel(candidates: list[Candidate]) -> list[str]:
    labels = {
        "screening": "筛选",
        "interview": "面试",
        "offer": "Offer",
        "onboarding": "入职",
        "hired": "已入职",
        "rejected": "淘汰",
    }
    return [f"{label}: {sum(1 for candidate in candidates if candidate.stage == stage)}" for stage, label in labels.items()]
