"""Public orchestration contract for AgentRun and Approval creation."""

from __future__ import annotations

import time
from typing import Any, Mapping
from uuid import uuid4

from apps.api.models import utc_now

from ...shared.llm import LLMProvider, get_llm_provider
from ..actions import ActionEngine

from .router import route_message


RUNTIME_VERSION = "v0.16.0-team-workbench-foundations-v1"


def run_agent_runtime(
    message: Mapping[str, Any],
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Route one normalized message and return audit-ready structured output.

    Agent A can call this after persisting/importing a MessageEvent. The return
    value contains everything needed to create AgentRun rows, business objects,
    and Approval rows without this module touching the database.
    """

    provider = llm_provider or get_llm_provider()
    route = route_message(message, llm_provider=provider)
    action_result = ActionEngine().build(message, route)
    actions = action_result["actions"]
    approval_items = _approval_items(message, route, action_result)
    now = utc_now().isoformat()

    return {
        "runtime_version": RUNTIME_VERSION,
        "run_id": str(uuid4()),
        "created_at": now,
        "message": {
            "id": message.get("id") or message.get("message_id"),
            "source_platform": message.get("source_platform") or message.get("channel") or "local_import",
            "conversation_id": message.get("conversation_id"),
            "sender_name": message.get("sender_name") or message.get("sender"),
            "text": message.get("text") or message.get("content") or message.get("message_text") or "",
        },
        "route": route,
        "analysis": action_result.get("analysis", {}),
        "actions": actions,
        "approval_items": approval_items,
        "agent_run": {
            "agent_name": action_result["agent_name"],
            "agent_version": RUNTIME_VERSION,
            "status": "completed",
            "input": {"message": dict(message)},
            "output": {
                "route": route,
                "analysis": action_result.get("analysis", {}),
                "actions": actions,
                "approval_items": approval_items,
            },
            "model_provider": route.get("classifier", {}).get("provider") or provider.name,
            "model_name": route.get("classifier", {}).get("model") or provider.model,
            "prompt": action_result.get("prompt") or route.get("classifier", {}).get("prompt"),
            "classifier": route.get("classifier", {}),
            "requires_approval": bool(approval_items),
            "risk_level": route.get("risk_level"),
            "confidence": route.get("confidence"),
            "started_at": now,
            "finished_at": now,
        },
        "metadata": {
            "mode": "local_alpha",
            "llm_provider": provider.name,
            "llm_model": provider.model,
            "external_replies_require_approval": True,
        },
    }


def handle_message_event(session: Any, message: Any) -> dict[str, Any]:
    """Persist runtime output for Agent A's import pipeline.

    This adapter intentionally lives in Agent B's routing module because Agent A
    already calls it dynamically after creating a MessageEvent. The pure runtime
    remains ``run_agent_runtime``; this function is only the SQLModel bridge.
    """

    started = time.perf_counter()
    normalized = _message_to_dict(message)
    attach_conversation_policy(session, message, normalized)
    result = run_agent_runtime(normalized)

    from apps.api.models import AgentRun, Approval, Candidate, FollowupTask, KnowledgeGap, Lead, Ticket
    from apps.api.modules.knowledge.router import knowledge_search_score, record_search_hit

    agent_run_payload = result["agent_run"]
    knowledge_references = retrieve_knowledge_references(session, message, knowledge_search_score, record_search_hit)
    result["knowledge_references"] = knowledge_references
    for approval_item in result.get("approval_items", []):
        approval_item["knowledge_references"] = knowledge_references
    prompt_meta = agent_run_payload.get("prompt") or {}
    classifier_meta = agent_run_payload.get("classifier") or {}
    usage_meta = classifier_meta.get("usage") if isinstance(classifier_meta, dict) else {}
    run = AgentRun(
        tenant_id=message.tenant_id,
        message_id=message.id,
        agent_type=agent_run_payload["agent_name"],
        status="success",
        prompt_version=prompt_meta.get("version") or RUNTIME_VERSION,
        prompt_json={
            "runtime_version": RUNTIME_VERSION,
            "prompt": prompt_meta,
            "llm_request": classifier_meta.get("request") if isinstance(classifier_meta, dict) else None,
            "route": result["route"],
        },
        model_provider=agent_run_payload.get("model_provider") or "local",
        model_name=agent_run_payload.get("model_name") or "rule-engine",
        model_output_json={
            "route": result["route"],
            "classifier": classifier_meta,
            "analysis": result.get("analysis", {}),
            "approval_items": result.get("approval_items", []),
            "knowledge_references": knowledge_references,
        },
        action_json={"actions": result["actions"]},
        confidence=float(result["route"].get("confidence") or 0.0),
        risk_level=str(result["route"].get("risk_level") or "low"),
        latency_ms=int((time.perf_counter() - started) * 1000),
        tokens_used=int((usage_meta or {}).get("total_tokens") or 0) if isinstance(usage_meta, dict) else 0,
        error_message=classifier_meta.get("error") if isinstance(classifier_meta, dict) else None,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    created_objects: dict[str, Any] = {}
    for action in result["actions"]:
        business_object = action.get("business_object") or {}
        object_type = business_object.get("type")
        fields = business_object.get("fields") or {}
        if object_type == "ticket":
            ticket = _ticket_from_action(Ticket, message, run.id, fields)
            session.add(ticket)
            session.flush()
            created_objects["ticket"] = ticket
        elif object_type == "lead":
            lead = _lead_from_action(Lead, message, run.id, fields, action)
            session.add(lead)
            session.flush()
            created_objects["lead"] = lead
        elif object_type == "task":
            task = _task_from_action(FollowupTask, message, run.id, fields, action, created_objects)
            session.add(task)
            session.flush()
            created_objects["task"] = task
        elif object_type == "candidate":
            candidate = _candidate_from_action(Candidate, message, run.id, fields)
            session.add(candidate)
            session.flush()
            created_objects["candidate"] = candidate
        elif object_type == "knowledge_gap":
            gap = _knowledge_gap_from_action(KnowledgeGap, message, run.id, fields)
            session.add(gap)
            session.flush()
            created_objects["knowledge_gap"] = gap

    for approval_item in result["approval_items"]:
        session.add(
            Approval(
                tenant_id=message.tenant_id,
                agent_run_id=run.id,
                status="pending_review",
                draft_content=approval_item.get("draft_reply") or "",
            )
        )

    session.commit()
    result["persisted"] = {
        "agent_run_id": run.id,
        "approval_count": len(result["approval_items"]),
    }
    return result


def retrieve_knowledge_references(
    session: Any,
    message: Any,
    score_fn: Any,
    record_hit_fn: Any,
) -> list[dict[str, Any]]:
    text = getattr(message, "text", "") or ""
    if not text.strip():
        return []
    from apps.api.modules.knowledge.retrieval import retrieve_knowledge

    _, matches = retrieve_knowledge(
        session,
        message.tenant_id,
        text,
        limit=3,
        keyword_score_fn=score_fn,
    )
    references = []
    for match in matches:
        item = match.item
        if item.id is None:
            continue
        hit = record_hit_fn(
            session,
            message.tenant_id,
            item,
            text,
            match.score,
            "message",
            message.id or 0,
        )
        references.append(
            {
                "type": "knowledge_item",
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "score": match.score,
                "keyword_score": match.keyword_score,
                "semantic_score": match.semantic_score,
                "reasons": match.reasons,
                "snippet": match.snippet,
                "citation": match.citation,
                "hit_id": hit.id,
            }
        )
    return references


def _approval_items(
    message: Mapping[str, Any],
    route: Mapping[str, Any],
    action_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for action in action_result.get("actions", []):
        if action.get("action_type") != "send_draft_to_approval":
            continue
        fields = ((action.get("business_object") or {}).get("fields") or {}).copy()
        draft_reply = action.get("draft_reply") or fields.get("draft_reply") or ""
        items.append(
            {
                "approval_type": fields.get("approval_type") or "external_reply",
                "status": "pending",
                "requires_approval": True,
                "risk_level": route.get("risk_level"),
                "priority": action.get("priority"),
                "channel": fields.get("channel") or message.get("source_platform") or "local_import",
                "conversation_id": fields.get("conversation_id") or message.get("conversation_id"),
                "source_message_id": message.get("id") or message.get("message_id"),
                "target_agent": route.get("target_agent"),
                "intent": route.get("intent"),
                "draft_reply": draft_reply,
                "reason": action.get("reason"),
                "related_object_type": fields.get("related_object_type"),
                "related_object_hint": fields.get("related_object_hint"),
            }
        )
    return items


def _message_to_dict(message: Any) -> dict[str, Any]:
    return {
        "id": getattr(message, "id", None),
        "message_id": getattr(message, "id", None),
        "source_platform": "local_import",
        "channel_id": getattr(message, "channel_id", None),
        "conversation_id": getattr(message, "conversation_id", None),
        "sender_external_id": getattr(message, "sender_external_id", None),
        "sender_name": getattr(message, "sender_name", None),
        "message_type": getattr(message, "message_type", "text"),
        "text": getattr(message, "text", "") or "",
        "normalized_json": getattr(message, "normalized_json", {}) or {},
        "raw_payload": getattr(message, "raw_json", {}) or {},
    }


def attach_conversation_policy(session: Any, message: Any, normalized: dict[str, Any]) -> None:
    try:
        from apps.api.models import Conversation

        conversation = session.get(Conversation, getattr(message, "conversation_id", None))
    except Exception:
        conversation = None
    if conversation is None:
        return
    normalized["conversation_title"] = getattr(conversation, "name", None)
    normalized["conversation_external_id"] = getattr(conversation, "external_conversation_id", None)
    normalized["conversation_bound_agent"] = getattr(conversation, "bound_agent", None)
    normalized["conversation_send_mode"] = getattr(conversation, "send_mode", "inherit")


def _ticket_from_action(model: Any, message: Any, agent_run_id: int, fields: Mapping[str, Any]) -> Any:
    return model(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=agent_run_id,
        title=str(fields.get("title") or "客户问题待处理")[:240],
        customer_name=str(fields.get("customer_name") or message.sender_name or "未知客户")[:200],
        category=str(fields.get("category") or "support")[:80],
        priority=_db_priority(str(fields.get("priority") or "medium")),
        status=str(fields.get("status") or "open")[:30],
        summary=str(fields.get("description") or fields.get("source_excerpt") or message.text or ""),
    )


def _lead_from_action(
    model: Any,
    message: Any,
    agent_run_id: int,
    fields: Mapping[str, Any],
    action: Mapping[str, Any],
) -> Any:
    return model(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=agent_run_id,
        customer_name=str(fields.get("customer_name") or message.sender_name or "未知客户")[:200],
        company=fields.get("company"),
        interest=str(fields.get("interest") or "业务咨询")[:240],
        stage=str(fields.get("stage") or "qualified")[:50],
        score=int(fields.get("score") or 50),
        priority=_db_priority(str(action.get("priority") or "medium")),
        summary=str(fields.get("source_excerpt") or message.text or ""),
        next_step=str(fields.get("suggested_next_action") or "")[:500],
    )


def _task_from_action(
    model: Any,
    message: Any,
    agent_run_id: int,
    fields: Mapping[str, Any],
    action: Mapping[str, Any],
    created_objects: Mapping[str, Any],
) -> Any:
    related_type = fields.get("related_object_type")
    related = created_objects.get(str(related_type)) if related_type else None
    return model(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=agent_run_id,
        title=str(fields.get("title") or action.get("reason") or "销售线索跟进")[:240],
        task_type=str(fields.get("task_type") or "followup")[:50],
        status=str(fields.get("status") or "todo")[:30],
        priority=_db_priority(str(action.get("priority") or "medium")),
        related_object_type=str(related_type or "")[:50] or None,
        related_object_id=getattr(related, "id", None),
        due_hint=fields.get("due_hint"),
        summary=str(fields.get("summary") or action.get("reason") or message.text or ""),
    )


def _candidate_from_action(model: Any, message: Any, agent_run_id: int, fields: Mapping[str, Any]) -> Any:
    return model(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=agent_run_id,
        name=str(fields.get("name") or message.sender_name or "未知候选人")[:200],
        role=str(fields.get("role") or "待确认岗位")[:200],
        stage=str(fields.get("stage") or "screening")[:50],
        match_score=int(fields.get("match_score") or 50),
        summary=str(fields.get("summary") or message.text or ""),
        interview_questions_json=list(fields.get("interview_questions") or []),
        onboarding_checklist_json=list(fields.get("onboarding_checklist") or []),
    )


def _knowledge_gap_from_action(model: Any, message: Any, agent_run_id: int, fields: Mapping[str, Any]) -> Any:
    return model(
        tenant_id=message.tenant_id,
        source_message_id=message.id,
        agent_run_id=agent_run_id,
        question=str(fields.get("question") or message.text or "待补充问题")[:500],
        suggested_answer=str(fields.get("suggested_answer") or ""),
        category=str(fields.get("category") or "general")[:80],
        occurrence_count=1,
        status="pending",
        examples_json=[{"message_id": message.id, "text": message.text}],
    )


def _db_priority(priority: str) -> str:
    if priority == "urgent":
        return "high"
    if priority == "normal":
        return "medium"
    return priority[:30]
