from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.models import AgentRun, Approval, utc_now
from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.approvals.delivery import delivery_runs_for_approval, preview_approval_delivery, send_approval_reply
from apps.api.modules.approvals.feishu_cards import approval_card_runs_for_approval, preview_approval_card, send_approval_card, serialize_card_run
from apps.api.modules.business_objects.router import build_business_object_detail
from apps.api.modules.display import enrich_approval
from apps.api.schemas import ApprovalEnrichedRead, ApprovalRead, ApprovalUpdate


router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    decision: str
    final_content: str | None = None
    reject_reason: str | None = None


class FeishuApprovalCardSendRequest(BaseModel):
    confirm_real_send: bool = False


@router.get("", response_model=list[ApprovalRead])
def list_approvals(session: SessionDep, tenant: TenantDep, status: str | None = None) -> list[Approval]:
    statement = select(Approval).where(Approval.tenant_id == tenant.id)
    if status:
        statement = statement.where(Approval.status == status)
    statement = statement.order_by(Approval.created_at.desc())
    return list(session.exec(statement).all())


@router.get("/enriched", response_model=list[ApprovalEnrichedRead])
def list_approvals_enriched(
    session: SessionDep,
    tenant: TenantDep,
    status: str | None = None,
    target_agent: str | None = None,
    business_object_type: str | None = None,
) -> list[ApprovalEnrichedRead]:
    statement = select(Approval).where(Approval.tenant_id == tenant.id)
    if status:
        statement = statement.where(Approval.status == status)
    statement = statement.order_by(Approval.created_at.desc(), Approval.id.desc())
    approvals = [enrich_approval(session, approval) for approval in session.exec(statement).all()]
    if target_agent:
        approvals = [approval for approval in approvals if approval.target_agent == target_agent]
    if business_object_type:
        approvals = [approval for approval in approvals if approval.business_object_type == business_object_type]
    return approvals


@router.patch("/{approval_id}", response_model=ApprovalRead)
def update_approval(
    approval_id: int,
    payload: ApprovalUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Approval:
    ensure_approval_operator(current_user.role)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")

    approval.status = payload.status
    approval.final_content = payload.final_content or approval.final_content or approval.draft_content
    approval.operator_id = current_user.id
    approval.reject_reason = payload.reject_reason
    approval.operated_at = utc_now()
    if payload.status == "sent":
        approval.sent_at = approval.operated_at
    session.add(approval)
    append_audit_log(
        session,
        tenant.id,
        "approval_updated",
        f"更新审批 #{approval.id} 状态为 {approval.status}",
        operator=current_user,
        scope_type="approval",
        scope_id=approval.id,
        object_type="approval",
        object_id=approval.id,
        status=approval.status,
        detail_json={"agent_run_id": approval.agent_run_id, "reject_reason": approval.reject_reason},
    )
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/{approval_id}/decision", response_model=ApprovalRead)
def decide_approval(
    approval_id: int,
    payload: ApprovalDecisionRequest,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Approval:
    ensure_approval_operator(current_user.role)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")

    decision = payload.decision
    if decision not in {"approved", "edited", "rejected"}:
        raise HTTPException(status_code=400, detail="decision must be approved, edited, or rejected")

    approval.status = decision
    approval.final_content = approval.draft_content if decision == "approved" else payload.final_content or approval.final_content or approval.draft_content
    approval.reject_reason = payload.reject_reason if decision == "rejected" else None
    approval.operator_id = current_user.id
    approval.operated_at = utc_now()
    session.add(approval)
    append_audit_log(
        session,
        tenant.id,
        "approval_decided",
        f"{current_user.display_name} {decision} 审批 #{approval.id}",
        operator=current_user,
        scope_type="approval",
        scope_id=approval.id,
        object_type="approval",
        object_id=approval.id,
        status=approval.status,
        detail_json={"decision": decision, "agent_run_id": approval.agent_run_id},
    )
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/{approval_id}/send", response_model=ApprovalRead)
def send_approval(
    approval_id: int,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Approval:
    ensure_approval_operator(current_user.role)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = send_approval_reply(session, approval)
    append_audit_log(
        session,
        tenant.id,
        "approval_sent",
        f"{current_user.display_name} 发送审批回复 #{approval.id}",
        operator=current_user,
        scope_type="approval",
        scope_id=approval.id,
        object_type="approval",
        object_id=approval.id,
        status=result.status,
        detail_json={"agent_run_id": approval.agent_run_id, "sent_at": result.sent_at.isoformat() if result.sent_at else None},
    )
    session.commit()
    session.refresh(result)
    return result


@router.get("/{approval_id}/send-preview")
def preview_send_approval(
    approval_id: int,
    session: SessionDep,
    tenant: TenantDep,
) -> dict:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return preview_approval_delivery(session, approval)


@router.get("/{approval_id}/feishu-card-preview")
def preview_feishu_approval_card(
    approval_id: int,
    session: SessionDep,
    tenant: TenantDep,
) -> dict:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return preview_approval_card(session, approval)


@router.post("/{approval_id}/feishu-card")
def send_feishu_approval_card(
    approval_id: int,
    payload: FeishuApprovalCardSendRequest,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict:
    ensure_approval_operator(current_user.role)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = send_approval_card(session, approval, confirm_real_send=payload.confirm_real_send)
    append_audit_log(
        session,
        tenant.id,
        "approval_card_sent",
        f"{current_user.display_name} 发送飞书审批卡片 #{approval.id}",
        operator=current_user,
        scope_type="approval",
        scope_id=approval.id,
        object_type="approval",
        object_id=approval.id,
        status="card_sent",
        detail_json={"confirm_real_send": payload.confirm_real_send, "result": result},
    )
    session.commit()
    return result


@router.get("/{approval_id}/context")
def approval_context(approval_id: int, session: SessionDep, tenant: TenantDep) -> dict:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    enriched = enrich_approval(session, approval)
    business_detail = None
    if enriched.business_object_type and enriched.business_object_id:
        business_detail = build_business_object_detail(
            session,
            tenant.id,
            enriched.business_object_type,
            int(enriched.business_object_id),
        )
    knowledge_references = []
    if approval.agent_run_id:
        run = session.get(AgentRun, approval.agent_run_id)
        if run is not None and run.tenant_id == tenant.id:
            knowledge_references = (run.model_output_json or {}).get("knowledge_references") or []
    return {
        "approval": enriched.model_dump(),
        "business_object": business_detail,
        "knowledge_references": knowledge_references,
        "send_preview": preview_approval_delivery(session, approval),
        "delivery_history": [serialize_delivery_run(run) for run in delivery_runs_for_approval(session, approval)],
        "card_preview": preview_approval_card(session, approval),
        "card_history": [serialize_card_run(run) for run in approval_card_runs_for_approval(session, approval)],
    }


@router.post("/{approval_id}/mock-send", response_model=ApprovalRead)
def mock_send_approval(
    approval_id: int,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Approval:
    ensure_approval_operator(current_user.role)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = send_approval_reply(session, approval)
    append_audit_log(
        session,
        tenant.id,
        "approval_mock_sent",
        f"{current_user.display_name} 执行审批发送 #{approval.id}",
        operator=current_user,
        scope_type="approval",
        scope_id=approval.id,
        object_type="approval",
        object_id=approval.id,
        status=result.status,
        detail_json={"agent_run_id": approval.agent_run_id},
    )
    session.commit()
    session.refresh(result)
    return result


def serialize_delivery_run(run) -> dict:
    output = run.model_output_json or {}
    action = run.action_json or {}
    return {
        "id": run.id,
        "status": run.status,
        "channel": (output.get("channel") or action.get("delivery_channel")) if isinstance(output, dict) else action.get("delivery_channel"),
        "mode": (output.get("mode") or action.get("delivery_mode")) if isinstance(output, dict) else action.get("delivery_mode"),
        "chat_id": output.get("chat_id") if isinstance(output, dict) else None,
        "target_type": output.get("target_type") if isinstance(output, dict) else None,
        "target_id": output.get("target_id") if isinstance(output, dict) else None,
        "feishu_message_id": output.get("feishu_message_id") if isinstance(output, dict) else None,
        "request_uuid": output.get("request_uuid") if isinstance(output, dict) else None,
        "error": run.error_message,
        "advice": output.get("advice") if isinstance(output, dict) else None,
        "attempt": action.get("delivery_attempt") or (run.prompt_json or {}).get("delivery_attempt"),
        "created_at": run.created_at.isoformat(),
    }


def ensure_approval_operator(role: str) -> None:
    if role not in {"admin", "approver"}:
        raise HTTPException(status_code=403, detail="Only admin or approver can operate approvals in v0.16.0")
