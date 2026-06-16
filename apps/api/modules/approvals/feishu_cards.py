from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from apps.api.core.config import get_settings
from apps.api.models import AgentRun, Approval, MessageEvent, Tenant, utc_now
from apps.api.modules.adapters.feishu import FeishuAdapterError, FeishuClient
from apps.api.modules.approvals.delivery import preview_approval_delivery
from apps.api.modules.display import enrich_approval


CARD_PROMPT_VERSION = "v0.15.4-feishu-approval-card-v1"


def preview_approval_card(session: Session, approval: Approval) -> dict[str, Any]:
    settings = get_settings()
    enriched = enrich_approval(session, approval)
    config_ready = bool(settings.feishu_approval_chat_id and settings.feishu_configured)
    return {
        "sendable": bool(config_ready and settings.enable_external_send),
        "config_ready": config_ready,
        "mode": "real" if settings.enable_external_send else "mock",
        "target_chat_id": settings.feishu_approval_chat_id or None,
        "missing": missing_card_requirements(settings),
        "card": build_approval_card(enriched.model_dump(), approval_detail_url(settings.public_base_url, approval.id)),
        "send_preview": preview_approval_delivery(session, approval),
    }


def send_approval_card(session: Session, approval: Approval, confirm_real_send: bool = False) -> dict[str, Any]:
    settings = get_settings()
    preview = preview_approval_card(session, approval)
    target_chat_id = settings.feishu_approval_chat_id
    if not target_chat_id:
        output = {
            "channel": "feishu",
            "mode": "mock",
            "sent": False,
            "reason": "FEISHU_APPROVAL_CHAT_ID is not configured; approval card was generated but not sent.",
            "card": preview["card"],
        }
        run = record_card_run(session, approval, status="success", output=output)
        return {"status": "mocked", "agent_run_id": run.id, **output}
    if settings.enable_external_send and not confirm_real_send:
        raise HTTPException(status_code=400, detail="confirm_real_send=true is required to send an approval card to Feishu.")

    request_uuid = stable_card_uuid(approval)
    try:
        result = FeishuClient(settings).send_interactive_card_to_chat(
            chat_id=target_chat_id,
            card=preview["card"],
            request_uuid=request_uuid,
        )
    except FeishuAdapterError as exc:
        run = record_card_run(
            session,
            approval,
            status="failed",
            output={"error": str(exc), "code": exc.code, "advice": exc.advice, "body": exc.body, "chat_id": target_chat_id},
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "advice": exc.advice, "agent_run_id": run.id}) from exc

    output = {
        "channel": "feishu",
        "mode": "real" if settings.enable_external_send else "mock",
        "chat_id": target_chat_id,
        "request_uuid": request_uuid,
        "result": result,
        "card": preview["card"],
    }
    run = record_card_run(session, approval, status="success", output=output)
    return {"status": "sent" if settings.enable_external_send else "mocked", "agent_run_id": run.id, **output}


def handle_approval_card_callback(session: Session, tenant: Tenant, payload: dict[str, Any]) -> dict[str, Any]:
    action = extract_card_action(payload)
    approval_id = action.get("approval_id")
    decision = action.get("decision")
    payload_event_id = event_id_from_payload(payload)
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Unsupported Feishu approval card decision")
    if approval_id is None:
        raise HTTPException(status_code=400, detail="Feishu approval card callback missing approval_id")

    approval = approval_for_callback(session, tenant, approval_id)
    if approval.status in {"approved", "rejected", "sent"}:
        already_processed = approval.status == decision or (approval.status == "sent" and decision == "approved")
        run = record_card_run(
            session,
            approval,
            status="success" if already_processed else "failed",
            output={
                "callback": True,
                "decision": decision,
                "action": action,
                "payload_event_id": payload_event_id,
                "toast": "审批已处理，无需重复操作。" if already_processed else f"审批当前状态为 {approval.status}，不能再改为 {decision}。",
                "error": None if already_processed else f"Approval status {approval.status} cannot be changed from Feishu card",
            },
        )
        return callback_result(
            session,
            approval,
            run,
            decision,
            "审批已处理，无需重复操作。" if already_processed else f"审批当前状态为 {approval.status}，不能重复改动。",
            status="ok" if already_processed else "ignored",
        )
    if approval.status not in {"pending_review", "edited"}:
        raise HTTPException(status_code=400, detail=f"Approval status {approval.status} cannot be changed from Feishu card")

    approval.status = decision
    approval.final_content = approval.draft_content if decision == "approved" else approval.final_content
    approval.reject_reason = "Rejected from Feishu approval card." if decision == "rejected" else None
    approval.operated_at = utc_now()
    session.add(approval)
    session.commit()
    session.refresh(approval)

    run = record_card_run(
        session,
        approval,
        status="success",
        output={"callback": True, "decision": decision, "action": action, "payload_event_id": payload_event_id},
    )
    toast = "审批已通过。" if decision == "approved" else "审批已拒绝。"
    return callback_result(session, approval, run, decision, toast)


def build_approval_card(approval: dict[str, Any], detail_url: str | None = None) -> dict[str, Any]:
    approval_id = approval.get("id")
    target_agent = approval.get("target_agent") or "unknown_agent"
    risk_level = approval.get("risk_level") or "-"
    draft = str(approval.get("final_content") or approval.get("draft_content") or "")
    source = str(approval.get("original_message") or "")
    status = str(approval.get("status") or "pending_review")
    actions = approval_card_actions(approval_id, status, detail_url)
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "orange", "title": {"tag": "plain_text", "content": f"WorkBuddy 审批 #{approval_id}"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**来源消息**\n{truncate(source, 220)}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**AI 草稿**\n{truncate(draft, 500)}"}},
            {"tag": "hr"},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Agent**\n{target_agent}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**风险**\n{risk_level}"}},
            ]},
            {
                "tag": "action",
                "actions": actions,
            },
        ],
    }


def card_button(text: str, button_type: str, approval_id: Any, decision: str) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": button_type,
        "value": {
            "source": "workbuddy_approval_card",
            "approval_id": approval_id,
            "decision": decision,
        },
    }


def link_button(text: str, url: str) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": "default",
        "url": url,
    }


def status_button(status: str) -> dict[str, Any]:
    labels = {
        "approved": ("已通过", "primary"),
        "rejected": ("已拒绝", "danger"),
        "sent": ("已发送", "primary"),
    }
    text, button_type = labels.get(status, ("已处理", "default"))
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": button_type,
        "disabled": True,
    }


def approval_card_actions(approval_id: Any, status: str, detail_url: str | None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if status in {"pending_review", "edited"}:
        actions.extend(
            [
                card_button("通过", "primary", approval_id, "approved"),
                card_button("拒绝", "danger", approval_id, "rejected"),
            ]
        )
    else:
        actions.append(status_button(status))
    if detail_url:
        actions.append(link_button("查看详情", detail_url))
    return actions


def extract_card_action(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action.get("value"), dict) else {}
    if not value:
        value = event.get("value") if isinstance(event.get("value"), dict) else {}
    return {
        "approval_id": value.get("approval_id") or event.get("approval_id"),
        "decision": value.get("decision") or value.get("action") or event.get("decision"),
        "operator": event.get("operator") or event.get("user_id") or {},
        "raw_value": value,
    }


def is_approval_card_callback(payload: dict[str, Any]) -> bool:
    action = extract_card_action(payload)
    value = action.get("raw_value")
    return isinstance(value, dict) and value.get("source") == "workbuddy_approval_card"


def approval_card_runs_for_approval(session: Session, approval: Approval) -> list[AgentRun]:
    if approval.id is None:
        return []
    original_message = source_message_for_approval(session, approval)
    source_message_id = original_message.id if original_message else None
    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == approval.tenant_id, AgentRun.agent_type == "feishu_approval_card_adapter")
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    matched: list[AgentRun] = []
    for run in runs:
        if (run.action_json or {}).get("approval_id") != approval.id:
            continue
        prompt_source = (run.prompt_json or {}).get("source_message_id")
        if source_message_id is not None and run.message_id != source_message_id and str(prompt_source) != str(source_message_id):
            continue
        if run.created_at < approval.created_at:
            continue
        matched.append(run)
    return matched


def serialize_card_run(run: AgentRun) -> dict[str, Any]:
    output = run.model_output_json or {}
    action = run.action_json or {}
    return {
        "id": run.id,
        "status": run.status,
        "mode": output.get("mode"),
        "chat_id": action.get("chat_id") or output.get("chat_id"),
        "request_uuid": action.get("request_uuid") or output.get("request_uuid"),
        "decision": action.get("decision") or output.get("decision"),
        "callback": bool(action.get("callback") or output.get("callback")),
        "event_id": action.get("payload_event_id") or output.get("payload_event_id"),
        "toast": output.get("toast"),
        "error": run.error_message,
        "created_at": run.created_at.isoformat(),
    }


def record_card_run(session: Session, approval: Approval, status: str, output: dict[str, Any]) -> AgentRun:
    started = time.perf_counter()
    original_message = source_message_for_approval(session, approval)
    action = output.get("action") if isinstance(output.get("action"), dict) else {}
    operator = action.get("operator") if isinstance(action.get("operator"), dict) else {}
    run = AgentRun(
        tenant_id=approval.tenant_id,
        message_id=original_message.id if original_message else None,
        agent_type="feishu_approval_card_adapter",
        status=status,
        prompt_version=CARD_PROMPT_VERSION,
        prompt_json={"approval_id": approval.id, "source_message_id": original_message.id if original_message else None},
        model_provider="local",
        model_name="feishu-approval-card",
        model_output_json=output,
        action_json={
            "action_type": "feishu_approval_card",
            "approval_id": approval.id,
            "chat_id": output.get("chat_id"),
            "decision": output.get("decision"),
            "callback": bool(output.get("callback")),
            "payload_event_id": output.get("payload_event_id"),
            "request_uuid": output.get("request_uuid"),
            "operator_open_id": operator.get("open_id"),
            "operator_user_id": operator.get("user_id"),
            "operator_name": operator.get("name"),
        },
        confidence=1.0 if status == "success" else 0.0,
        risk_level="medium",
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_message=output.get("error"),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def source_message_for_approval(session: Session, approval: Approval) -> MessageEvent | None:
    original_run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    return session.get(MessageEvent, original_run.message_id) if original_run and original_run.message_id else None


def approval_for_callback(session: Session, tenant: Tenant, approval_id: Any) -> Approval:
    if approval_id in (None, ""):
        raise HTTPException(status_code=400, detail="Feishu approval card callback missing approval_id")
    try:
        normalized_id = int(approval_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid approval_id in Feishu approval card callback") from exc
    approval = session.get(Approval, normalized_id)
    if approval is None or approval.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


def missing_card_requirements(settings) -> list[str]:
    missing = []
    if not settings.feishu_configured:
        missing.append("FEISHU_APP_ID / FEISHU_APP_SECRET")
    if not settings.feishu_approval_chat_id:
        missing.append("FEISHU_APPROVAL_CHAT_ID")
    return missing


def stable_card_uuid(approval: Approval) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"workbuddy:approval-card:{approval.tenant_id}:{approval.id}:{approval.created_at.isoformat()}"))


def approval_detail_url(public_base_url: str, approval_id: Any) -> str | None:
    base_url = str(public_base_url or "").strip().rstrip("/")
    if not base_url or approval_id in (None, ""):
        return None
    return f"{base_url}/#approvals?id={approval_id}"


def callback_result(
    session: Session,
    approval: Approval,
    run: AgentRun,
    decision: str,
    toast: str,
    *,
    status: str = "ok",
) -> dict[str, Any]:
    settings = get_settings()
    enriched = enrich_approval(session, approval)
    card_data = enriched.model_dump()
    card_data["status"] = approval.status
    card = build_approval_card(
        card_data,
        approval_detail_url(settings.public_base_url, approval.id),
    )
    return {
        "status": status,
        "action": decision,
        "approval_id": approval.id,
        "agent_run_id": run.id,
        "approval_status": approval.status,
        "toast": {"type": "success" if status == "ok" else "warning", "content": toast},
        "callback_response": {
            "toast": {"type": "success" if status == "ok" else "warning", "content": toast},
            "card": {"type": "raw", "data": card},
        },
    }


def event_id_from_payload(payload: dict[str, Any]) -> str | None:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    return header.get("event_id") or payload.get("event_id")


def truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
