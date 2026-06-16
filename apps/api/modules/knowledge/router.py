from __future__ import annotations

from datetime import timedelta
import hashlib
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import AgentRun, KnowledgeGap, KnowledgeHit, KnowledgeItem, KnowledgeItemVersion, MessageEvent, ProcessingRecord, Ticket, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.knowledge.retrieval import ensure_item_embedding, rebuild_embeddings, retrieve_knowledge
from apps.api.schemas import (
    KnowledgeGapRead,
    KnowledgeHitFeedbackRequest,
    KnowledgeItemRead,
    KnowledgeItemUpdate,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeVersionRollbackRequest,
)


router = APIRouter()

KNOWLEDGE_ITEM_TRANSITIONS = {
    "draft": {"draft", "pending_review", "archived"},
    "pending_review": {"pending_review", "published", "draft", "archived"},
    "published": {"published", "archived"},
    "archived": {"archived"},
}
KNOWLEDGE_ITEM_STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "published": "已发布",
    "archived": "已归档",
}


@router.get("/gaps", response_model=list[KnowledgeGapRead])
def list_knowledge_gaps(
    session: SessionDep,
    tenant: TenantDep,
    status: str | None = None,
    category: str | None = None,
) -> list[KnowledgeGap]:
    statement = select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id)
    if status:
        statement = statement.where(KnowledgeGap.status == status)
    if category:
        statement = statement.where(KnowledgeGap.category == category)
    statement = statement.order_by(KnowledgeGap.created_at.desc(), KnowledgeGap.id.desc())
    return list(session.exec(statement).all())


@router.get("/gaps/{gap_id}")
def get_knowledge_gap_detail(gap_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    gap = get_gap(session, tenant.id, gap_id)
    return {
        "type": "knowledge_gap",
        "gap": gap.model_dump(),
        "source_references": source_references_for_gap(session, gap),
        "related_items": [item.model_dump() for item in related_items_for_gap(session, tenant.id, gap.id or 0)],
        "processing_records": processing_records(session, tenant.id, "knowledge_gap", gap.id or 0),
        "timeline": gap_timeline(session, gap),
    }


@router.get("/items", response_model=list[KnowledgeItemRead])
def list_knowledge_items(
    session: SessionDep,
    tenant: TenantDep,
    status: str | None = None,
    category: str | None = None,
) -> list[KnowledgeItem]:
    statement = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant.id)
    if status:
        statement = statement.where(KnowledgeItem.status == status)
    if category:
        statement = statement.where(KnowledgeItem.category == category)
    statement = statement.order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.id.desc())
    return list(session.exec(statement).all())


@router.get("/items/workflow")
def get_knowledge_item_workflow() -> dict[str, Any]:
    return {
        "statuses": [
            {"value": status, "label": KNOWLEDGE_ITEM_STATUS_LABELS[status], "next": sorted(next_statuses)}
            for status, next_statuses in KNOWLEDGE_ITEM_TRANSITIONS.items()
        ],
        "transitions": {status: sorted(next_statuses) for status, next_statuses in KNOWLEDGE_ITEM_TRANSITIONS.items()},
    }


@router.get("/graph")
def get_knowledge_graph(
    session: SessionDep,
    tenant: TenantDep,
    category: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    items_statement = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant.id)
    gaps_statement = select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id)
    if category:
        items_statement = items_statement.where(KnowledgeItem.category == category)
        gaps_statement = gaps_statement.where(KnowledgeGap.category == category)
    if status:
        items_statement = items_statement.where(KnowledgeItem.status == status)
    items = list(session.exec(items_statement.order_by(KnowledgeItem.updated_at.desc(), KnowledgeItem.id.desc()).limit(160)).all())
    gaps = list(session.exec(gaps_statement.order_by(KnowledgeGap.updated_at.desc(), KnowledgeGap.id.desc()).limit(160)).all())
    item_ids = [item.id for item in items if item.id is not None]
    gap_ids = [gap.id for gap in gaps if gap.id is not None]
    versions = list(
        session.exec(
            select(KnowledgeItemVersion)
            .where(KnowledgeItemVersion.tenant_id == tenant.id, KnowledgeItemVersion.item_id.in_(item_ids or [-1]))
            .order_by(KnowledgeItemVersion.version_no.desc(), KnowledgeItemVersion.id.desc())
            .limit(240)
        ).all()
    )
    hits = list(
        session.exec(
            select(KnowledgeHit)
            .where(KnowledgeHit.tenant_id == tenant.id, KnowledgeHit.item_id.in_(item_ids or [-1]))
            .order_by(KnowledgeHit.created_at.desc(), KnowledgeHit.id.desc())
            .limit(120)
        ).all()
    )
    return build_knowledge_graph(session, tenant.id, items, gaps, versions, hits, gap_ids)


@router.get("/quality")
def get_knowledge_quality(session: SessionDep, tenant: TenantDep, category: str | None = None) -> dict[str, Any]:
    items_statement = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant.id)
    gaps_statement = select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id)
    if category:
        items_statement = items_statement.where(KnowledgeItem.category == category)
        gaps_statement = gaps_statement.where(KnowledgeGap.category == category)
    items = list(session.exec(items_statement.order_by(KnowledgeItem.updated_at.desc(), KnowledgeItem.id.desc())).all())
    gaps = list(session.exec(gaps_statement.order_by(KnowledgeGap.updated_at.desc(), KnowledgeGap.id.desc()).limit(200)).all())
    hits = list(
        session.exec(
            select(KnowledgeHit)
            .where(KnowledgeHit.tenant_id == tenant.id, KnowledgeHit.item_id.in_([item.id for item in items if item.id is not None] or [-1]))
            .order_by(KnowledgeHit.created_at.desc(), KnowledgeHit.id.desc())
        ).all()
    )
    return build_quality_dashboard(items, gaps, hits)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(payload: KnowledgeSearchRequest, session: SessionDep, tenant: TenantDep) -> KnowledgeSearchResponse:
    total_candidates, ranked = retrieve_knowledge(
        session,
        tenant.id,
        payload.query,
        category=payload.category,
        include_drafts=payload.include_drafts,
        limit=payload.limit,
        keyword_score_fn=knowledge_search_score,
    )
    matches = []
    source_object_id = payload.source_object_id or stable_query_id(payload.query)
    for match in ranked:
        item = match.item
        hit_id = None
        if payload.record_hit and item.id is not None:
            hit = record_search_hit(
                session,
                tenant.id,
                item,
                payload.query,
                match.score,
                payload.source_object_type,
                source_object_id,
            )
            hit_id = hit.id
        matches.append(
            {
                "item": item.model_dump(),
                "score": match.score,
                "keyword_score": match.keyword_score,
                "semantic_score": match.semantic_score,
                "quality_score": match.quality_score,
                "retrieval_mode": "hybrid",
                "reasons": match.reasons,
                "snippet": match.snippet,
                "citation": match.citation,
                "source_reference": {
                    "type": "knowledge_item",
                    "id": item.id,
                    "label": match.citation,
                    "title": item.title,
                    "category": item.category,
                    "status": item.status,
                },
                "recorded_hit_id": hit_id,
            }
        )
    if payload.record_hit:
        session.commit()
    return KnowledgeSearchResponse(query=payload.query, total_candidates=total_candidates, matches=matches)


@router.post("/index/rebuild")
def rebuild_knowledge_index(
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can rebuild the knowledge index")
    result = rebuild_embeddings(session, tenant.id)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_index_rebuilt",
        f"{current_user.display_name} 重建知识向量索引",
        operator=current_user,
        scope_type="knowledge_index",
        status="completed",
        detail_json=result,
    )
    session.commit()
    return result


@router.get("/obsidian-export")
def export_knowledge_obsidian_draft(session: SessionDep, tenant: TenantDep, category: str | None = None) -> dict[str, Any]:
    items_statement = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant.id)
    gaps_statement = select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant.id)
    if category:
        items_statement = items_statement.where(KnowledgeItem.category == category)
        gaps_statement = gaps_statement.where(KnowledgeGap.category == category)
    items = list(session.exec(items_statement.order_by(KnowledgeItem.updated_at.desc(), KnowledgeItem.id.desc()).limit(240)).all())
    gaps = list(session.exec(gaps_statement.order_by(KnowledgeGap.updated_at.desc(), KnowledgeGap.id.desc()).limit(240)).all())
    hits = list(
        session.exec(
            select(KnowledgeHit)
            .where(KnowledgeHit.tenant_id == tenant.id, KnowledgeHit.item_id.in_([item.id for item in items if item.id is not None] or [-1]))
            .order_by(KnowledgeHit.created_at.desc(), KnowledgeHit.id.desc())
            .limit(240)
        ).all()
    )
    files = build_obsidian_export_files(items, gaps, hits)
    return {
        "format": "obsidian_markdown_draft",
        "file_count": len(files),
        "files": files,
    }


@router.get("/items/{item_id}")
def get_knowledge_item_detail(item_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    item = get_item(session, tenant.id, item_id)
    gap = session.get(KnowledgeGap, item.source_gap_id) if item.source_gap_id else None
    if gap is not None and gap.tenant_id != tenant.id:
        gap = None
    versions = session.exec(
        select(KnowledgeItemVersion)
        .where(KnowledgeItemVersion.tenant_id == tenant.id, KnowledgeItemVersion.item_id == item.id)
        .order_by(KnowledgeItemVersion.version_no.desc(), KnowledgeItemVersion.id.desc())
    ).all()
    version_payloads = [version.model_dump() for version in versions]
    if not version_payloads:
        version_payloads = [virtual_current_version(item)]
    return {
        "type": "knowledge_item",
        "item": item.model_dump(),
        "source_gap": gap.model_dump() if gap else None,
        "source_references": source_references_for_item(session, item, gap),
        "versions": version_payloads,
        "hit_summary": knowledge_hit_summary(session, tenant.id, item.id or 0),
        "hits": knowledge_hits(session, tenant.id, item.id or 0),
        "processing_records": processing_records(session, tenant.id, "knowledge_item", item.id or 0),
        "timeline": item_timeline(session, item, gap, versions, include_virtual_version=not versions),
    }


@router.post("/gaps/{gap_id}/accept", response_model=KnowledgeItemRead)
def accept_knowledge_gap(gap_id: int, session: SessionDep, tenant: TenantDep, current_user: CurrentUserDep) -> KnowledgeItem:
    gap = session.get(KnowledgeGap, gap_id)
    if gap is None or gap.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    item = KnowledgeItem(
        tenant_id=tenant.id,
        source_gap_id=gap.id,
        title=gap.question[:240],
        answer=gap.suggested_answer or "待人工补充标准答案。",
        category=gap.category,
        status="draft",
    )
    gap.status = "accepted"
    gap.updated_at = utc_now()
    session.add(gap)
    session.add(item)
    session.flush()
    ensure_item_embedding(session, item)
    snapshot_knowledge_item_version(session, item, "accept_gap", f"采纳 KnowledgeGap#{gap.id} 生成知识条目")
    record_knowledge_processing(session, item, "accept_gap", item.status, f"{current_user.display_name} 采纳 KnowledgeGap#{gap.id} 生成知识草稿", current_user)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_gap_accepted",
        f"{current_user.display_name} 采纳知识缺口 #{gap.id}",
        operator=current_user,
        scope_type="knowledge_gap",
        scope_id=gap.id,
        object_type="knowledge_item",
        object_id=item.id,
        status=item.status,
        detail_json={"gap_id": gap.id, "item_id": item.id},
    )
    session.commit()
    session.refresh(item)
    return item


@router.post("/gaps/{gap_id}/ignore", response_model=KnowledgeGapRead)
def ignore_knowledge_gap(gap_id: int, session: SessionDep, tenant: TenantDep, current_user: CurrentUserDep) -> KnowledgeGap:
    gap = session.get(KnowledgeGap, gap_id)
    if gap is None or gap.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    gap.status = "ignored"
    gap.updated_at = utc_now()
    session.add(gap)
    record_gap_processing(session, gap, "ignore_gap", gap.status, f"{current_user.display_name} 忽略知识缺口", current_user)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_gap_ignored",
        f"{current_user.display_name} 忽略知识缺口 #{gap.id}",
        operator=current_user,
        scope_type="knowledge_gap",
        scope_id=gap.id,
        object_type="knowledge_gap",
        object_id=gap.id,
        status=gap.status,
    )
    session.commit()
    session.refresh(gap)
    return gap


@router.patch("/items/{item_id}", response_model=KnowledgeItemRead)
def update_knowledge_item(
    item_id: int,
    payload: KnowledgeItemUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> KnowledgeItem:
    item = session.get(KnowledgeItem, item_id)
    if item is None or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    before = item.model_dump(mode="json")
    if payload.title is not None:
        item.title = payload.title[:240]
    if payload.answer is not None:
        item.answer = payload.answer
    if payload.category is not None:
        item.category = payload.category[:80]
    if payload.status is not None:
        ensure_knowledge_item_transition(item.status, payload.status)
        item.status = payload.status
    if payload.review_due_at is not None:
        item.review_due_at = payload.review_due_at
    if payload.last_reviewed_at is not None:
        item.last_reviewed_at = payload.last_reviewed_at
    if payload.quality_status is not None:
        item.quality_status = payload.quality_status
    if payload.quality_score is not None:
        item.quality_score = payload.quality_score
    item.updated_at = utc_now()
    session.add(item)
    session.flush()
    ensure_item_embedding(session, item)
    change_type = knowledge_item_change_type(before.get("status"), item.status, payload)
    change_summary = (payload.change_summary or default_knowledge_change_summary(change_type, before.get("status"), item.status)).strip()[:500]
    snapshot_knowledge_item_version(session, item, change_type, change_summary)
    record_knowledge_processing(session, item, change_type, item.status, change_summary, current_user)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_item_updated",
        f"{current_user.display_name} 更新知识条目 #{item.id}",
        operator=current_user,
        scope_type="knowledge_item",
        scope_id=item.id,
        object_type="knowledge_item",
        object_id=item.id,
        status=item.status,
        detail_json={"before": before, "after": item.model_dump(mode="json"), "change_type": change_type, "change_summary": change_summary},
    )
    session.commit()
    session.refresh(item)
    return item


@router.post("/items/{item_id}/versions/{version_id}/rollback", response_model=KnowledgeItemRead)
def rollback_knowledge_item_version(
    item_id: int,
    version_id: int,
    payload: KnowledgeVersionRollbackRequest,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> KnowledgeItem:
    item = get_item(session, tenant.id, item_id)
    version = session.get(KnowledgeItemVersion, version_id)
    if version is None or version.tenant_id != tenant.id or version.item_id != item.id:
        raise HTTPException(status_code=404, detail="Knowledge item version not found")
    before = item.model_dump(mode="json")
    item.title = version.title
    item.answer = version.answer
    item.category = version.category
    item.status = version.status
    item.updated_at = utc_now()
    session.add(item)
    session.flush()
    ensure_item_embedding(session, item)
    summary = (
        payload.change_summary
        or f"回滚至知识版本 v{version.version_no}，保留当前状态为历史版本"
    ).strip()[:500]
    snapshot_knowledge_item_version(session, item, "rollback", summary)
    record_knowledge_processing(session, item, "rollback", item.status, summary, current_user)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_item_rolled_back",
        f"{current_user.display_name} 将知识条目 #{item.id} 回滚至 v{version.version_no}",
        operator=current_user,
        scope_type="knowledge_item",
        scope_id=item.id,
        object_type="knowledge_item",
        object_id=item.id,
        status=item.status,
        detail_json={
            "before": before,
            "target_version_id": version.id,
            "target_version_no": version.version_no,
            "after": item.model_dump(mode="json"),
        },
    )
    session.commit()
    session.refresh(item)
    return item


@router.post("/hits/{hit_id}/feedback")
def update_knowledge_hit_feedback(
    hit_id: int,
    payload: KnowledgeHitFeedbackRequest,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    hit = session.get(KnowledgeHit, hit_id)
    if hit is None or hit.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge hit not found")
    item = get_item(session, tenant.id, hit.item_id)
    before_score = item.quality_score
    if hit.status == payload.status:
        return {
            "hit": hit.model_dump(),
            "item": item.model_dump(),
            "feedback": payload.status,
        }
    hit.status = payload.status
    if payload.status == "useful":
        item.quality_score = min(100, item.quality_score + 2)
        if item.quality_status == "needs_review" and item.quality_score >= 70:
            item.quality_status = "healthy"
    else:
        item.quality_score = max(0, item.quality_score - 10)
        item.quality_status = "needs_review"
    item.updated_at = utc_now()
    note = (payload.note or ("检索结果有帮助" if payload.status == "useful" else "检索结果无帮助")).strip()[:500]
    session.add(hit)
    session.add(item)
    record_knowledge_processing(
        session,
        item,
        "retrieval_feedback",
        item.quality_status,
        f"{current_user.display_name} 标记 hit#{hit.id} 为 {payload.status}：{note}",
        current_user,
    )
    append_audit_log(
        session,
        tenant.id,
        "knowledge_hit_feedback",
        f"{current_user.display_name} 提交知识命中反馈 hit#{hit.id}",
        operator=current_user,
        scope_type="knowledge_item",
        scope_id=item.id,
        object_type="knowledge_hit",
        object_id=hit.id,
        status=payload.status,
        detail_json={
            "note": note,
            "quality_score_before": before_score,
            "quality_score_after": item.quality_score,
        },
    )
    session.commit()
    session.refresh(hit)
    session.refresh(item)
    return {
        "hit": hit.model_dump(),
        "item": item.model_dump(),
        "feedback": payload.status,
    }


def build_knowledge_graph(
    session,
    tenant_id: int,
    items: list[KnowledgeItem],
    gaps: list[KnowledgeGap],
    versions: list[KnowledgeItemVersion],
    hits: list[KnowledgeHit],
    gap_ids: list[int],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def add_node(node_id: str, kind: str, label: str, **payload: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "kind": kind,
                "label": label,
                **payload,
            }
            return
        nodes[node_id].update({key: value for key, value in payload.items() if value not in (None, "")})
        if label and nodes[node_id].get("label", "").startswith(("KnowledgeGap#", "工单#")):
            nodes[node_id]["label"] = label

    def add_edge(source: str, target: str, edge_type: str, label: str | None = None) -> None:
        if source not in nodes or target not in nodes:
            return
        edge_id = f"{source}->{target}:{edge_type}"
        edges[edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label or edge_type,
        }

    for item in items:
        item_node = f"knowledge_item:{item.id}"
        category_node = f"category:{item.category or 'general'}"
        add_node(
            item_node,
            "KnowledgeItem",
            item.title[:80],
            object_type="knowledge_item",
            object_id=item.id,
            status=item.status,
            category=item.category,
            summary=item.answer[:220],
        )
        add_node(category_node, "Category", item.category or "general", category=item.category or "general")
        add_edge(category_node, item_node, "same_category", "同分类")
        if item.source_gap_id:
            gap_node = f"knowledge_gap:{item.source_gap_id}"
            add_node(gap_node, "KnowledgeGap", f"KnowledgeGap#{item.source_gap_id}", object_type="knowledge_gap", object_id=item.source_gap_id)
            add_edge(gap_node, item_node, "created_from", "从缺口生成")

    for gap in gaps:
        gap_node = f"knowledge_gap:{gap.id}"
        category_node = f"category:{gap.category or 'general'}"
        add_node(
            gap_node,
            "KnowledgeGap",
            gap.question[:80],
            object_type="knowledge_gap",
            object_id=gap.id,
            status=gap.status,
            category=gap.category,
            summary=gap.suggested_answer[:220],
        )
        add_node(category_node, "Category", gap.category or "general", category=gap.category or "general")
        add_edge(category_node, gap_node, "same_category", "同分类")
        if gap.source_message_id:
            message = session.get(MessageEvent, gap.source_message_id)
            if message is not None and message.tenant_id == tenant_id:
                message_node = f"source_message:{message.id}"
                add_node(
                    message_node,
                    "SourceMessage",
                    f"消息#{message.id}",
                    object_type="message",
                    object_id=message.id,
                    summary=message.text[:220],
                    created_at=message.received_at.isoformat(),
                )
                add_edge(message_node, gap_node, "source_of", "来源")
        if gap.agent_run_id:
            run = session.get(AgentRun, gap.agent_run_id)
            if run is not None and run.tenant_id == tenant_id:
                run_node = f"agent_run:{run.id}"
                add_node(
                    run_node,
                    "AgentRun",
                    f"AgentRun#{run.id}",
                    object_type="agent_run",
                    object_id=run.id,
                    status=run.status,
                    summary=run.agent_type,
                    created_at=run.created_at.isoformat(),
                )
                add_edge(run_node, gap_node, "created_from", "识别生成")
        for example in gap.examples_json or []:
            if not isinstance(example, dict) or not example.get("ticket_id"):
                continue
            ticket_id = int(example["ticket_id"])
            ticket = session.get(Ticket, ticket_id)
            if ticket is None or ticket.tenant_id != tenant_id:
                continue
            ticket_node = f"ticket:{ticket.id}"
            add_node(
                ticket_node,
                "Ticket",
                f"工单#{ticket.id}",
                object_type="ticket",
                object_id=ticket.id,
                status=ticket.status,
                summary=ticket.title[:220],
                created_at=ticket.created_at.isoformat(),
            )
            add_edge(ticket_node, gap_node, "source_of", "来源")

    for version in versions:
        item_node = f"knowledge_item:{version.item_id}"
        version_node = f"knowledge_version:{version.id}"
        add_node(
            version_node,
            "KnowledgeVersion",
            f"v{version.version_no}",
            object_type="knowledge_item",
            object_id=version.item_id,
            status=version.status,
            category=version.category,
            summary=version.change_summary or version.change_type,
            created_at=version.created_at.isoformat(),
        )
        add_edge(version_node, item_node, "version_of", "版本")

    for hit in hits:
        item_node = f"knowledge_item:{hit.item_id}"
        hit_node = f"knowledge_hit:{hit.id}"
        add_node(
            hit_node,
            "Hit",
            f"命中#{hit.id}",
            object_type="knowledge_hit",
            object_id=hit.id,
            status=hit.status,
            summary=hit.query_text[:220],
            score=hit.score,
            created_at=hit.created_at.isoformat(),
        )
        add_edge(hit_node, item_node, "hit_by", "命中")
        if hit.source_object_type == "ticket":
            ticket = session.get(Ticket, hit.source_object_id)
            if ticket is not None and ticket.tenant_id == tenant_id:
                ticket_node = f"ticket:{ticket.id}"
                add_node(
                    ticket_node,
                    "Ticket",
                    f"工单#{ticket.id}",
                    object_type="ticket",
                    object_id=ticket.id,
                    status=ticket.status,
                    summary=ticket.title[:220],
                    created_at=ticket.created_at.isoformat(),
                )
                add_edge(ticket_node, hit_node, "source_of", "来源")
        else:
            source_node = f"{hit.source_object_type}:{hit.source_object_id}"
            add_node(
                source_node,
                hit.source_object_type.title(),
                f"{hit.source_object_type}#{hit.source_object_id}",
                object_type=hit.source_object_type,
                object_id=hit.source_object_id,
            )
            add_edge(source_node, hit_node, "source_of", "来源")

    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "knowledge_items": len([node for node in nodes.values() if node["kind"] == "KnowledgeItem"]),
            "knowledge_gaps": len([node for node in nodes.values() if node["kind"] == "KnowledgeGap"]),
            "hits": len([node for node in nodes.values() if node["kind"] == "Hit"]),
        },
    }


def build_quality_dashboard(items: list[KnowledgeItem], gaps: list[KnowledgeGap], hits: list[KnowledgeHit]) -> dict[str, Any]:
    now = utc_now()
    review_window = now + timedelta(days=14)
    stale_before = now - timedelta(days=90)
    hit_map: dict[int, list[KnowledgeHit]] = {}
    for hit in hits:
        hit_map.setdefault(hit.item_id, []).append(hit)

    expired_items: list[dict[str, Any]] = []
    review_due_soon: list[dict[str, Any]] = []
    optimization_candidates: list[dict[str, Any]] = []
    archive_suggestions: list[dict[str, Any]] = []
    item_payloads: list[dict[str, Any]] = []
    quality_score_total = 0

    for item in items:
        item_hits = hit_map.get(item.id or 0, [])
        hit_count = len(item_hits)
        average_score = round(sum(hit.score for hit in item_hits) / hit_count, 2) if hit_count else 0
        review_due_at = normalize_dt(item.review_due_at)
        updated_at = normalize_dt(item.updated_at)
        computed_status = computed_quality_status(item, review_due_at, updated_at, hit_count, average_score, now, stale_before)
        quality_score_total += item.quality_score
        payload = {
            "item": item.model_dump(mode="json"),
            "hit_count": hit_count,
            "average_hit_score": average_score,
            "computed_quality_status": computed_status,
            "reason": quality_reason(item, computed_status, hit_count, average_score),
        }
        item_payloads.append(payload)
        if item.status == "archived":
            continue
        if computed_status == "expired":
            expired_items.append(payload)
        if review_due_at and now <= review_due_at <= review_window:
            review_due_soon.append(payload)
        if computed_status == "needs_optimization":
            optimization_candidates.append(payload)
        if computed_status == "archive_suggested":
            archive_suggestions.append(payload)

    pending_gaps = [gap for gap in gaps if gap.status == "pending"]
    repeated_gaps = [gap for gap in pending_gaps if gap.occurrence_count > 1]
    return {
        "summary": {
            "total_items": len(items),
            "published_items": len([item for item in items if item.status == "published"]),
            "expired_items": len(expired_items),
            "review_due_soon": len(review_due_soon),
            "optimization_candidates": len(optimization_candidates),
            "archive_suggestions": len(archive_suggestions),
            "pending_gaps": len(pending_gaps),
            "repeated_gaps": len(repeated_gaps),
            "average_quality_score": round(quality_score_total / len(items), 2) if items else 0,
        },
        "expired_items": expired_items[:30],
        "review_due_soon": review_due_soon[:30],
        "optimization_candidates": optimization_candidates[:30],
        "archive_suggestions": archive_suggestions[:30],
        "gap_quality": {
            "pending_gaps": [gap.model_dump(mode="json") for gap in pending_gaps[:30]],
            "repeated_gaps": [gap.model_dump(mode="json") for gap in repeated_gaps[:30]],
        },
        "items": sorted(item_payloads, key=lambda row: (row["computed_quality_status"] == "healthy", -(row["hit_count"] or 0)))[:80],
        "rules": {
            "expired": "review_due_at 已早于当前时间，或人工质量状态为 expired。",
            "needs_optimization": "质量分低于 60，或命中不少于 3 次但平均命中分低于 60。",
            "archive_suggested": "已发布知识 90 天未更新且从未命中，或人工质量状态为 archive_suggested。",
            "review_due_soon": "复审日期在未来 14 天内。",
        },
    }


def knowledge_search_score(query: str, item: KnowledgeItem) -> tuple[int, list[str]]:
    tokens = tokenize_query(query)
    if not tokens:
        return 0, []
    title = (item.title or "").lower()
    answer = (item.answer or "").lower()
    category = (item.category or "").lower()
    normalized_query = query.lower().strip()
    score = 0
    reasons: list[str] = []
    if normalized_query and normalized_query in title:
        score += 45
        reasons.append("title_phrase")
    if normalized_query and normalized_query in answer:
        score += 30
        reasons.append("answer_phrase")
    for token in tokens:
        if token in title:
            score += 20
            reasons.append(f"title:{token}")
        if token in answer:
            score += 8
            reasons.append(f"answer:{token}")
        if token in category:
            score += 6
            reasons.append(f"category:{token}")
    if item.quality_score >= 80:
        score += 5
    if item.quality_status in {"expired", "needs_optimization", "archive_suggested"}:
        score -= 12
        reasons.append(f"quality:{item.quality_status}")
    return max(score, 0), dedupe_reasons(reasons)


def tokenize_query(query: str) -> list[str]:
    raw_tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) <= 1:
            continue
        tokens.append(token)
    return tokens[:20]


def dedupe_reasons(reasons: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def knowledge_snippet(query: str, item: KnowledgeItem) -> str:
    answer = item.answer or ""
    tokens = tokenize_query(query)
    lower_answer = answer.lower()
    for token in tokens:
        index = lower_answer.find(token)
        if index >= 0:
            start = max(index - 40, 0)
            end = min(index + 140, len(answer))
            return answer[start:end]
    return answer[:180]


def stable_query_id(query: str) -> int:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def record_search_hit(
    session,
    tenant_id: int,
    item: KnowledgeItem,
    query: str,
    score: int,
    source_object_type: str,
    source_object_id: int,
) -> KnowledgeHit:
    existing = session.exec(
        select(KnowledgeHit).where(
            KnowledgeHit.tenant_id == tenant_id,
            KnowledgeHit.item_id == item.id,
            KnowledgeHit.source_object_type == source_object_type,
            KnowledgeHit.source_object_id == source_object_id,
        )
    ).first()
    if existing is not None:
        existing.query_text = query
        existing.score = score
        existing.answer_snapshot = item.answer[:1000]
        if existing.status not in {"useful", "not_useful"}:
            existing.status = "retrieved"
        session.add(existing)
        session.flush()
        return existing
    hit = KnowledgeHit(
        tenant_id=tenant_id,
        item_id=item.id or 0,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        query_text=query,
        score=score,
        answer_snapshot=item.answer[:1000],
        status="retrieved",
    )
    session.add(hit)
    session.flush()
    return hit


def computed_quality_status(
    item: KnowledgeItem,
    review_due_at,
    updated_at,
    hit_count: int,
    average_score: float,
    now,
    stale_before,
) -> str:
    if item.quality_status in {"expired", "needs_optimization", "archive_suggested"}:
        return item.quality_status
    if review_due_at and review_due_at < now:
        return "expired"
    if item.quality_score < 60 or (hit_count >= 3 and average_score < 60):
        return "needs_optimization"
    if item.status == "published" and hit_count == 0 and updated_at < stale_before:
        return "archive_suggested"
    if item.quality_status == "needs_review":
        return "needs_review"
    return "healthy"


def quality_reason(item: KnowledgeItem, computed_status: str, hit_count: int, average_score: float) -> str:
    if computed_status == "expired":
        return "复审日期已过期，需要确认答案仍然有效。"
    if computed_status == "needs_optimization":
        if item.quality_score < 60:
            return f"人工质量分 {item.quality_score} 低于 60。"
        return f"命中 {hit_count} 次但平均分 {average_score} 低于 60。"
    if computed_status == "archive_suggested":
        return "长期未命中，建议复审后归档或合并。"
    if computed_status == "needs_review":
        return "人工标记为待复审。"
    return "质量状态正常。"


def normalize_dt(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value


def build_obsidian_export_files(items: list[KnowledgeItem], gaps: list[KnowledgeGap], hits: list[KnowledgeHit]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    item_map = {item.id: item for item in items if item.id is not None}
    categories = sorted({item.category or "general" for item in items} | {gap.category or "general" for gap in gaps})
    index_lines = [
        "# WorkBuddy Knowledge Vault Draft",
        "",
        "## Categories",
        *[f"- [[Category-{category}]]" for category in categories],
        "",
        "## Knowledge Items",
        *[f"- [[KnowledgeItem-{item.id}]] {item.title}" for item in items],
        "",
        "## Knowledge Gaps",
        *[f"- [[KnowledgeGap-{gap.id}]] {gap.question}" for gap in gaps],
        "",
    ]
    files.append({"path": "WorkBuddy Knowledge Vault Draft.md", "content": "\n".join(index_lines)})

    for category in categories:
        category_items = [item for item in items if (item.category or "general") == category]
        category_gaps = [gap for gap in gaps if (gap.category or "general") == category]
        lines = [
            f"# Category {category}",
            "",
            "## Items",
            *[f"- [[KnowledgeItem-{item.id}]] {item.title}" for item in category_items],
            "",
            "## Gaps",
            *[f"- [[KnowledgeGap-{gap.id}]] {gap.question}" for gap in category_gaps],
            "",
        ]
        files.append({"path": f"categories/Category-{category}.md", "content": "\n".join(lines)})

    hit_map: dict[int, list[KnowledgeHit]] = {}
    for hit in hits:
        hit_map.setdefault(hit.item_id, []).append(hit)

    for item in items:
        lines = [
            "---",
            f"id: {item.id}",
            "type: KnowledgeItem",
            f"status: {item.status}",
            f"category: {item.category or 'general'}",
            "---",
            "",
            f"# KnowledgeItem {item.id}: {item.title}",
            "",
            f"Category: [[Category-{item.category or 'general'}]]",
            f"Status: {item.status}",
            f"Source gap: [[KnowledgeGap-{item.source_gap_id}]]" if item.source_gap_id else "Source gap: -",
            "",
            "## Answer",
            item.answer or "待补充",
            "",
            "## Hits",
            *([
                f"- {hit.source_object_type}#{hit.source_object_id} score={hit.score}: {hit.query_text[:120]}"
                for hit in hit_map.get(item.id or 0, [])[:10]
            ] or ["- 暂无命中"]),
            "",
        ]
        files.append({"path": f"items/KnowledgeItem-{item.id}.md", "content": "\n".join(lines)})

    for gap in gaps:
        related_items = [item for item in item_map.values() if item.source_gap_id == gap.id]
        lines = [
            "---",
            f"id: {gap.id}",
            "type: KnowledgeGap",
            f"status: {gap.status}",
            f"category: {gap.category or 'general'}",
            "---",
            "",
            f"# KnowledgeGap {gap.id}",
            "",
            f"Category: [[Category-{gap.category or 'general'}]]",
            f"Status: {gap.status}",
            f"Source message: message#{gap.source_message_id}" if gap.source_message_id else "Source message: -",
            f"Agent run: agent_run#{gap.agent_run_id}" if gap.agent_run_id else "Agent run: -",
            "",
            "## Question",
            gap.question,
            "",
            "## Suggested Answer",
            gap.suggested_answer or "待补充",
            "",
            "## Related Items",
            *([f"- [[KnowledgeItem-{item.id}]] {item.title}" for item in related_items] or ["- 暂无关联条目"]),
            "",
        ]
        files.append({"path": f"gaps/KnowledgeGap-{gap.id}.md", "content": "\n".join(lines)})

    return files


def get_gap(session, tenant_id: int, gap_id: int) -> KnowledgeGap:
    gap = session.get(KnowledgeGap, gap_id)
    if gap is None or gap.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    return gap


def get_item(session, tenant_id: int, item_id: int) -> KnowledgeItem:
    item = session.get(KnowledgeItem, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return item


def snapshot_knowledge_item_version(
    session,
    item: KnowledgeItem,
    change_type: str,
    change_summary: str,
) -> KnowledgeItemVersion:
    current_max = session.exec(
        select(func.max(KnowledgeItemVersion.version_no)).where(
            KnowledgeItemVersion.tenant_id == item.tenant_id,
            KnowledgeItemVersion.item_id == item.id,
        )
    ).one()
    version = KnowledgeItemVersion(
        tenant_id=item.tenant_id,
        item_id=item.id or 0,
        version_no=int(current_max or 0) + 1,
        title=item.title,
        answer=item.answer,
        category=item.category,
        status=item.status,
        change_type=change_type,
        change_summary=change_summary,
    )
    session.add(version)
    return version


def ensure_knowledge_item_transition(current_status: str, next_status: str) -> None:
    allowed_next = KNOWLEDGE_ITEM_TRANSITIONS.get(current_status)
    if not allowed_next or next_status not in allowed_next:
        raise HTTPException(status_code=400, detail=f"Invalid knowledge item transition: {current_status} -> {next_status}")


def knowledge_item_change_type(previous_status: str | None, next_status: str, payload: KnowledgeItemUpdate) -> str:
    if previous_status != next_status:
        if next_status == "pending_review":
            return "submit_review"
        if next_status == "published":
            return "publish"
        if next_status == "archived":
            return "archive"
        if next_status == "draft":
            return "return_to_draft"
    return "edit"


def default_knowledge_change_summary(change_type: str, previous_status: str | None, next_status: str) -> str:
    if change_type == "submit_review":
        return "知识条目提交审核"
    if change_type == "publish":
        return "审核通过并发布知识条目"
    if change_type == "archive":
        return "归档知识条目"
    if change_type == "return_to_draft":
        return "退回草稿继续编辑"
    return f"知识条目人工编辑，状态 {previous_status or '-'} -> {next_status}"


def record_knowledge_processing(session, item: KnowledgeItem, action_type: str, status: str, note: str, current_user) -> ProcessingRecord:
    record = ProcessingRecord(
        tenant_id=item.tenant_id,
        object_type="knowledge_item",
        object_id=item.id or 0,
        action_type=action_type,
        status=status,
        note=note,
        operator_user_id=current_user.id,
        operator_username=current_user.username,
        operator_name=current_user.display_name,
    )
    session.add(record)
    return record


def record_gap_processing(session, gap: KnowledgeGap, action_type: str, status: str, note: str, current_user) -> ProcessingRecord:
    record = ProcessingRecord(
        tenant_id=gap.tenant_id,
        object_type="knowledge_gap",
        object_id=gap.id or 0,
        action_type=action_type,
        status=status,
        note=note,
        operator_user_id=current_user.id,
        operator_username=current_user.username,
        operator_name=current_user.display_name,
    )
    session.add(record)
    return record


def virtual_current_version(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "id": None,
        "tenant_id": item.tenant_id,
        "item_id": item.id,
        "version_no": 1,
        "title": item.title,
        "answer": item.answer,
        "category": item.category,
        "status": item.status,
        "change_type": "current",
        "change_summary": "当前知识条目快照；首次人工更新后会写入正式版本记录。",
        "created_at": item.updated_at.isoformat(),
    }


def related_items_for_gap(session, tenant_id: int, gap_id: int) -> list[KnowledgeItem]:
    return list(
        session.exec(
            select(KnowledgeItem)
            .where(KnowledgeItem.tenant_id == tenant_id, KnowledgeItem.source_gap_id == gap_id)
            .order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.id.desc())
        ).all()
    )


def source_references_for_gap(session, gap: KnowledgeGap) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    if gap.source_message_id:
        message = session.get(MessageEvent, gap.source_message_id)
        references.append(
            {
                "type": "message",
                "id": gap.source_message_id,
                "label": f"消息#{gap.source_message_id}",
                "summary": message.text[:180] if message else "",
                "created_at": message.received_at.isoformat() if message else None,
            }
        )
    if gap.agent_run_id:
        run = session.get(AgentRun, gap.agent_run_id)
        references.append(
            {
                "type": "agent_run",
                "id": gap.agent_run_id,
                "label": f"AgentRun#{gap.agent_run_id}",
                "summary": run.agent_type if run else "",
                "created_at": run.created_at.isoformat() if run else None,
            }
        )
    for index, example in enumerate(gap.examples_json or []):
        if isinstance(example, dict):
            ticket_id = example.get("ticket_id")
            if ticket_id:
                references.append(
                    {
                        "type": "ticket",
                        "id": ticket_id,
                        "label": f"工单#{ticket_id}",
                        "summary": str(example.get("title") or example.get("summary") or "")[:180],
                        "created_at": None,
                    }
                )
            elif example:
                references.append(
                    {
                        "type": "example",
                        "id": index + 1,
                        "label": f"示例#{index + 1}",
                        "summary": str(example)[:180],
                        "created_at": None,
                    }
                )
    return references


def source_references_for_item(session, item: KnowledgeItem, gap: KnowledgeGap | None) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    if gap is not None:
        references.append(
            {
                "type": "knowledge_gap",
                "id": gap.id,
                "label": f"KnowledgeGap#{gap.id}",
                "summary": gap.question[:180],
                "created_at": gap.created_at.isoformat(),
            }
        )
        references.extend(source_references_for_gap(session, gap))
    records = session.exec(
        select(ProcessingRecord)
        .where(
            ProcessingRecord.tenant_id == item.tenant_id,
            ProcessingRecord.object_type == "knowledge_item",
            ProcessingRecord.object_id == item.id,
        )
        .order_by(ProcessingRecord.created_at.desc(), ProcessingRecord.id.desc())
    ).all()
    for record in records[:6]:
        references.append(
            {
                "type": "processing_record",
                "id": record.id,
                "label": f"处理记录#{record.id}",
                "summary": record.note[:180],
                "created_at": record.created_at.isoformat(),
            }
        )
    return references


def knowledge_hits(session, tenant_id: int, item_id: int) -> list[dict[str, Any]]:
    hits = session.exec(
        select(KnowledgeHit)
        .where(KnowledgeHit.tenant_id == tenant_id, KnowledgeHit.item_id == item_id)
        .order_by(KnowledgeHit.created_at.desc(), KnowledgeHit.id.desc())
        .limit(20)
    ).all()
    return [hit.model_dump() for hit in hits]


def knowledge_hit_summary(session, tenant_id: int, item_id: int) -> dict[str, Any]:
    hits = session.exec(
        select(KnowledgeHit).where(KnowledgeHit.tenant_id == tenant_id, KnowledgeHit.item_id == item_id)
    ).all()
    if not hits:
        return {"total": 0, "latest_at": None, "average_score": 0}
    total_score = sum(hit.score for hit in hits)
    latest = max(hit.created_at for hit in hits)
    return {
        "total": len(hits),
        "latest_at": latest.isoformat(),
        "average_score": round(total_score / len(hits), 2),
    }


def processing_records(session, tenant_id: int, object_type: str, object_id: int) -> list[dict[str, Any]]:
    return [
        record.model_dump()
        for record in session.exec(
            select(ProcessingRecord)
            .where(
                ProcessingRecord.tenant_id == tenant_id,
                ProcessingRecord.object_type == object_type,
                ProcessingRecord.object_id == object_id,
            )
            .order_by(ProcessingRecord.created_at.desc(), ProcessingRecord.id.desc())
        ).all()
    ]


def gap_timeline(session, gap: KnowledgeGap) -> list[dict[str, Any]]:
    events = [
        {
            "type": "knowledge_gap_created",
            "title": "发现知识缺口",
            "description": gap.question,
            "created_at": gap.created_at.isoformat(),
        }
    ]
    for reference in source_references_for_gap(session, gap):
        if reference.get("created_at"):
            events.append(
                {
                    "type": f"source_{reference['type']}",
                    "title": f"来源：{reference['label']}",
                    "description": reference.get("summary") or "",
                    "created_at": reference["created_at"],
                }
            )
    if gap.status in {"accepted", "ignored"}:
        events.append(
            {
                "type": f"knowledge_gap_{gap.status}",
                "title": "知识缺口状态变更",
                "description": gap.status,
                "created_at": gap.updated_at.isoformat(),
            }
        )
    return sorted(events, key=lambda event: str(event.get("created_at") or ""))


def item_timeline(
    session,
    item: KnowledgeItem,
    gap: KnowledgeGap | None,
    versions: list[KnowledgeItemVersion],
    include_virtual_version: bool = False,
) -> list[dict[str, Any]]:
    events = [
        {
            "type": "knowledge_item_created",
            "title": "创建知识条目",
            "description": item.title,
            "created_at": item.created_at.isoformat(),
        }
    ]
    if gap is not None:
        events.append(
            {
                "type": "source_gap",
                "title": f"来源缺口 KnowledgeGap#{gap.id}",
                "description": gap.question,
                "created_at": gap.created_at.isoformat(),
            }
        )
    for version in versions:
        events.append(
            {
                "type": "knowledge_version",
                "title": f"版本 v{version.version_no}",
                "description": version.change_summary or version.change_type,
                "created_at": version.created_at.isoformat(),
            }
        )
    if include_virtual_version:
        events.append(
            {
                "type": "knowledge_version",
                "title": "版本 v1",
                "description": "当前知识条目快照",
                "created_at": item.updated_at.isoformat(),
            }
        )
    for hit in knowledge_hits(session, item.tenant_id, item.id or 0)[:5]:
        events.append(
            {
                "type": "knowledge_hit",
                "title": f"知识命中 {hit.get('source_object_type')}#{hit.get('source_object_id')}",
                "description": f"score={hit.get('score')} / {hit.get('query_text') or ''}",
                "created_at": hit.get("created_at"),
            }
        )
    return sorted(events, key=lambda event: str(event.get("created_at") or ""))
