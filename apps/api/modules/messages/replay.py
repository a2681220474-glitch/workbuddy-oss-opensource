from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from apps.api.models import AgentRun, Approval, Candidate, FollowupTask, KnowledgeGap, Lead, MessageEvent, Ticket
from apps.api.modules.display import enrich_message, latest_run_for_message, related_objects_for_message, route_from_run
from apps.api.modules.routing.orchestrator import handle_message_event


def replay_message_route(
    session: Session,
    tenant_id: int,
    message: MessageEvent,
    source_run: AgentRun | None = None,
) -> dict[str, Any]:
    before_run = source_run or latest_run_for_message(session, message.id)
    before = replay_snapshot(session, message, before_run)
    cleaned = cleanup_generated_objects(session, tenant_id, message.id or 0)
    result = handle_message_event(session=session, message=message)
    new_run_id = result.get("persisted", {}).get("agent_run_id")
    after_run = session.get(AgentRun, new_run_id) if new_run_id else latest_run_for_message(session, message.id)
    after = replay_snapshot(session, message, after_run)
    enriched = enrich_message(session, message)

    return {
        "message_id": message.id,
        "replayed_from_run_id": before_run.id if before_run else None,
        "agent_run_id": new_run_id,
        "approval_count": result.get("persisted", {}).get("approval_count", 0),
        "target_agent": enriched.target_agent,
        "intent": enriched.intent,
        "confidence": enriched.confidence,
        "risk_level": enriched.risk_level,
        "cleaned": cleaned,
        "related_objects": [item.model_dump() for item in enriched.related_objects],
        "before": before,
        "after": after,
        "changed": replay_changes(before, after),
    }


def replay_snapshot(session: Session, message: MessageEvent, run: AgentRun | None) -> dict[str, Any]:
    route = route_from_run(run)
    objects = related_objects_for_message(session, message)
    return {
        "agent_run_id": run.id if run else None,
        "target_agent": route.get("target_agent") or (run.agent_type if run else None),
        "intent": route.get("intent"),
        "confidence": route.get("confidence") if route.get("confidence") is not None else (run.confidence if run else None),
        "risk_level": route.get("risk_level") or (run.risk_level if run else None),
        "reason": route.get("reason"),
        "related_objects": [item.model_dump() for item in objects],
    }


def replay_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    return {
        "target_agent": before.get("target_agent") != after.get("target_agent"),
        "intent": before.get("intent") != after.get("intent"),
        "risk_level": before.get("risk_level") != after.get("risk_level"),
        "confidence": before.get("confidence") != after.get("confidence"),
        "related_objects": before.get("related_objects") != after.get("related_objects"),
    }


def cleanup_generated_objects(session: Session, tenant_id: int, message_id: int) -> dict[str, int]:
    if message_id <= 0:
        raise HTTPException(status_code=400, detail="Message id is required for replay")

    run_ids = [
        run.id
        for run in session.exec(
            select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.message_id == message_id)
        ).all()
        if run.id is not None
    ]

    cleaned: dict[str, int] = {}
    for model, key in [
        (Ticket, "tickets"),
        (Lead, "leads"),
        (FollowupTask, "tasks"),
        (Candidate, "candidates"),
        (KnowledgeGap, "knowledge_gaps"),
    ]:
        rows = session.exec(
            select(model).where(model.tenant_id == tenant_id, model.source_message_id == message_id)
        ).all()
        for row in rows:
            session.delete(row)
        cleaned[key] = len(rows)

    if run_ids:
        approvals = session.exec(
            select(Approval).where(
                Approval.tenant_id == tenant_id,
                Approval.agent_run_id.in_(run_ids),  # type: ignore[attr-defined]
                Approval.status == "pending_review",
            )
        ).all()
        for approval in approvals:
            session.delete(approval)
        cleaned["pending_approvals"] = len(approvals)
    else:
        cleaned["pending_approvals"] = 0

    session.commit()
    return cleaned
