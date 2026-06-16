from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, BEIJING_TZ, Lead, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.schemas import LeadApprovalDraftCreate, LeadRead, LeadUpdate


router = APIRouter()

LEAD_STAGES = [
    {"value": "new", "label": "新线索", "next": ["contacted", "proposal", "lost"]},
    {"value": "potential", "label": "潜在线索", "next": ["contacted", "proposal", "lost"]},
    {"value": "qualified", "label": "已确认", "next": ["contacted", "proposal", "negotiation", "lost"]},
    {"value": "contacted", "label": "已联系", "next": ["proposal", "negotiation", "lost"]},
    {"value": "proposal", "label": "已发方案", "next": ["negotiation", "won", "lost"]},
    {"value": "negotiation", "label": "谈判中", "next": ["won", "lost", "proposal"]},
    {"value": "won", "label": "赢单", "next": []},
    {"value": "lost", "label": "输单", "next": ["contacted"]},
]
LEAD_TRANSITIONS = {stage["value"]: stage["next"] for stage in LEAD_STAGES}


@router.get("", response_model=list[LeadRead])
def list_leads(
    session: SessionDep,
    tenant: TenantDep,
    stage: str | None = None,
    priority: str | None = None,
) -> list[Lead]:
    statement = select(Lead).where(Lead.tenant_id == tenant.id)
    if stage:
        statement = statement.where(Lead.stage == stage)
    if priority:
        statement = statement.where(Lead.priority == priority)
    statement = statement.order_by(Lead.score.desc(), Lead.created_at.desc(), Lead.id.desc())
    return list(session.exec(statement).all())


@router.get("/workflow")
def lead_workflow() -> dict[str, Any]:
    return {
        "stages": LEAD_STAGES,
        "transitions": LEAD_TRANSITIONS,
        "score_dimensions": ["budget", "timing", "need", "decision_role", "risk"],
    }


@router.get("/{lead_id}/scorecard")
def lead_scorecard(lead_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    lead = get_lead(session, tenant.id, lead_id)
    return build_scorecard(lead)


@router.get("/{lead_id}/draft")
def lead_draft(lead_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    lead = get_lead(session, tenant.id, lead_id)
    scorecard = build_scorecard(lead)
    return {
        "lead_id": lead.id,
        "draft_content": sales_reply_draft(lead, scorecard),
        "next_step": suggested_next_step(lead, scorecard),
        "requires_approval": True,
        "recommended_stage": recommended_stage(lead),
        "scorecard": scorecard,
    }


@router.post("/{lead_id}/approval-draft")
def create_lead_approval_draft(
    lead_id: int,
    payload: LeadApprovalDraftCreate,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    lead = get_lead(session, tenant.id, lead_id)
    draft = payload.draft_content or sales_reply_draft(lead, build_scorecard(lead))
    next_step = payload.next_step or suggested_next_step(lead, build_scorecard(lead))
    run = AgentRun(
        tenant_id=tenant.id,
        message_id=lead.source_message_id,
        agent_type="sales_lead_agent",
        status="success",
        prompt_version="v0.7-sales-lead-rules",
        prompt_json={"lead_id": lead.id, "action_type": "send_sales_draft_to_approval"},
        model_provider="local",
        model_name="rule-sales-assistant",
        model_output_json={"draft_content": draft, "next_step": next_step},
        action_json={
            "actions": [
                {
                    "action_type": "send_draft_to_approval",
                    "business_object": {"type": "lead", "id": lead.id, "label": lead.customer_name},
                }
            ]
        },
        confidence=0.92,
        risk_level="medium",
    )
    session.add(run)
    session.flush()
    approval = Approval(tenant_id=tenant.id, agent_run_id=run.id, draft_content=draft)
    lead.next_step = next_step[:500]
    lead.updated_at = utc_now()
    session.add(lead)
    session.add(approval)
    session.commit()
    return {"lead_id": lead.id, "approval_id": approval.id, "agent_run_id": run.id, "next_step": lead.next_step}


@router.patch("/{lead_id}", response_model=LeadRead)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Lead:
    lead = get_lead(session, tenant.id, lead_id)
    if payload.stage is not None:
        allowed_next = LEAD_TRANSITIONS.get(lead.stage, [])
        if payload.stage != lead.stage and payload.stage not in allowed_next:
            raise HTTPException(status_code=400, detail=f"Invalid lead transition: {lead.stage} -> {payload.stage}")
        lead.stage = payload.stage
    if payload.priority is not None:
        lead.priority = payload.priority
    if payload.next_step is not None:
        lead.next_step = payload.next_step[:500]
    lead.updated_at = utc_now()
    session.add(lead)
    append_audit_log(
        session,
        tenant.id,
        "lead_updated",
        f"{current_user.display_name} 更新线索 #{lead.id}",
        operator=current_user,
        scope_type="lead",
        scope_id=lead.id,
        object_type="lead",
        object_id=lead.id,
        status=lead.stage,
        detail_json={"priority": lead.priority, "next_step": lead.next_step},
    )
    session.commit()
    session.refresh(lead)
    return lead


def get_lead(session, tenant_id: int, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def build_scorecard(lead: Lead) -> dict[str, Any]:
    text = f"{lead.customer_name} {lead.company or ''} {lead.interest} {lead.summary} {lead.next_step}".lower()
    budget = dimension_score(text, ["预算", "万", "报价", "价格", "合同"], 20)
    timing = dimension_score(text, ["今天", "明天", "下周", "月底", "尽快", "下午"], 20)
    need = dimension_score(text, ["试用", "演示", "demo", "采购", "购买", "方案", "资料", "客服", "企微"], 25)
    decision_role = 15 if lead.customer_name.endswith("总") else 10 if lead.company else 5
    risk_penalty = dimension_score(text, ["太贵", "没预算", "暂时不用", "竞品", "对比"], 15)
    positive_score = budget + timing + need + decision_role
    computed_score = max(0, min(100, positive_score - risk_penalty + 25))
    return {
        "lead_id": lead.id,
        "score": lead.score,
        "computed_score": computed_score,
        "dimensions": {
            "budget": budget,
            "timing": timing,
            "need": need,
            "decision_role": decision_role,
            "risk": -risk_penalty,
        },
        "reasons": score_reasons(lead, budget, timing, need, decision_role, risk_penalty),
        "priority": priority_for_score(max(lead.score, computed_score)),
        "stalled": is_stalled(lead),
    }


def dimension_score(text: str, keywords: list[str], score: int) -> int:
    return score if any(keyword.lower() in text for keyword in keywords) else 0


def score_reasons(lead: Lead, budget: int, timing: int, need: int, decision_role: int, risk_penalty: int) -> list[str]:
    reasons = []
    if budget:
        reasons.append("提到预算、价格、报价或合同")
    if timing:
        reasons.append("提到明确跟进时间")
    if need:
        reasons.append("表达试用、演示、采购、方案或业务痛点")
    if decision_role >= 15:
        reasons.append("客户称呼疑似决策人")
    elif decision_role >= 10:
        reasons.append("已识别公司信息")
    if risk_penalty:
        reasons.append("存在价格、预算或竞品异议")
    if not reasons:
        reasons.append(f"当前阶段为 {lead.stage}，需继续补充预算、时机和决策角色")
    return reasons


def priority_for_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def is_stalled(lead: Lead) -> bool:
    if lead.stage in {"proposal", "negotiation", "won", "lost"}:
        return False
    updated = lead.updated_at.replace(tzinfo=lead.updated_at.tzinfo or BEIJING_TZ)
    return (datetime.now(BEIJING_TZ) - updated).total_seconds() >= 24 * 60 * 60


def suggested_next_step(lead: Lead, scorecard: dict[str, Any]) -> str:
    if lead.stage in {"new", "potential", "qualified"}:
        return f"联系 {lead.customer_name}，补充预算、团队规模和预计上线时间"
    if lead.stage == "contacted":
        return f"基于 {lead.interest} 准备方案/案例并推进到已发方案"
    if lead.stage == "proposal":
        return "确认方案反馈、预算口径和决策流程，准备进入谈判"
    if lead.stage == "negotiation":
        return "确认成交阻塞点、合同信息和最终决策时间"
    if scorecard.get("stalled"):
        return "线索已停滞，今天需要重新触达"
    return lead.next_step or "补充下一步跟进动作"


def sales_reply_draft(lead: Lead, scorecard: dict[str, Any]) -> str:
    if lead.stage in {"proposal", "negotiation"}:
        return f"{lead.customer_name}您好，我这边继续跟进{lead.interest}，想确认一下方案里是否还有需要补充的场景、预算或上线时间。"
    if scorecard["priority"] in {"critical", "high"}:
        return f"{lead.customer_name}您好，看到您对{lead.interest}比较明确。我可以先整理一版方案和报价说明，人工确认后发您，同时想补充了解团队规模和预计上线时间。"
    return f"{lead.customer_name}您好，已收到您关于{lead.interest}的咨询。我先记录需求，确认后给您回复更贴近场景的下一步建议。"


def recommended_stage(lead: Lead) -> str:
    if lead.stage in {"new", "potential", "qualified"} and lead.score >= 60:
        return "contacted"
    if lead.stage == "contacted" and lead.score >= 70:
        return "proposal"
    return lead.stage
