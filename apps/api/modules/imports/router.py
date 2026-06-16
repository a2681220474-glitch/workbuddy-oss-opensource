import json
import csv
import io
import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, Candidate, ImportBatch, KnowledgeGap, KnowledgeItem, Lead, Ticket, utc_now
from apps.api.modules.imports.parsers import parse_csv_records, record_from_mapping
from apps.api.modules.imports.service import import_records
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.knowledge.router import snapshot_knowledge_item_version
from apps.api.schemas import (
    ImportRecord,
    ImportResult,
    JSONImportRequest,
    KnowledgeImportConfirmResult,
    KnowledgeImportPreviewResult,
    KnowledgeImportPreviewRow,
    KnowledgeImportRequest,
    RawImportRequest,
)


router = APIRouter()


@router.post("/csv", response_model=ImportResult)
async def import_csv_chat(
    session: SessionDep,
    tenant: TenantDep,
    file: UploadFile = File(...),
) -> ImportResult:
    records = parse_csv_records(await file.read())
    batch, messages = import_records(session, tenant, records, source="csv", filename=file.filename)
    return ImportResult(batch=batch, messages=messages)


@router.post("/json", response_model=ImportResult)
def import_json_chat(
    payload: JSONImportRequest,
    session: SessionDep,
    tenant: TenantDep,
) -> ImportResult:
    batch, messages = import_records(session, tenant, payload.records, source=payload.source)
    return ImportResult(batch=batch, messages=messages)


@router.post("/messages")
def import_messages_compat(
    payload: RawImportRequest,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, object]:
    records = parse_raw_import(payload)
    batch, messages = import_records(
        session,
        tenant,
        records,
        source=payload.source_type,
        filename=payload.filename,
    )
    message_ids = [message.id for message in messages if message.id is not None]
    created_tickets = count_for_messages(session, Ticket, tenant.id, message_ids)
    created_leads = count_for_messages(session, Lead, tenant.id, message_ids)
    created_candidates = count_for_messages(session, Candidate, tenant.id, message_ids)
    created_knowledge_gaps = count_for_messages(session, KnowledgeGap, tenant.id, message_ids)
    agent_runs = count_agent_runs_for_messages(session, tenant.id, message_ids)
    approval_count = 0
    if message_ids:
        run_ids = list(
            session.exec(
                select(AgentRun.id).where(
                    AgentRun.tenant_id == tenant.id,
                    AgentRun.message_id.in_(message_ids),  # type: ignore[union-attr]
                )
            ).all()
        )
        if run_ids:
            approval_count = len(
                session.exec(
                    select(Approval).where(
                        Approval.tenant_id == tenant.id,
                        Approval.agent_run_id.in_(run_ids),  # type: ignore[union-attr]
                    )
                ).all()
            )
    return {
        "import_id": batch.id,
        "imported_count": batch.imported_count,
        "message_count": batch.imported_count,
        "created_tickets": created_tickets,
        "created_leads": created_leads,
        "created_candidates": created_candidates,
        "created_knowledge_gaps": created_knowledge_gaps,
        "created_approvals": approval_count,
        "agent_runs": agent_runs,
        "errors": [] if batch.error_count == 0 else [f"{batch.error_count} row(s) failed"],
        "batch": batch,
        "messages": messages,
    }


@router.post("/knowledge/preview", response_model=KnowledgeImportPreviewResult)
def preview_knowledge_import(payload: KnowledgeImportRequest) -> KnowledgeImportPreviewResult:
    return build_knowledge_import_preview(payload)


@router.post("/knowledge/confirm", response_model=KnowledgeImportConfirmResult)
def confirm_knowledge_import(
    payload: KnowledgeImportRequest,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> KnowledgeImportConfirmResult:
    preview = build_knowledge_import_preview(payload)
    batch = ImportBatch(
        tenant_id=tenant.id,
        source=f"knowledge_{payload.source_type}",
        filename=payload.filename,
        status="completed",
        total_rows=preview.total_rows,
        imported_count=0,
        skipped_count=0,
        error_count=0,
        metadata_json={
            "import_type": "knowledge",
            "source_type": payload.source_type,
            "filename": payload.filename,
            "default_category": payload.default_category,
            "publish": payload.publish,
        },
        completed_at=utc_now(),
    )
    session.add(batch)
    session.flush()
    created_items: list[KnowledgeItem] = []
    created_gaps: list[KnowledgeGap] = []
    skipped = 0
    for row in preview.rows:
        if row.warnings:
            skipped += 1
            continue
        if row.mode == "item":
            item = KnowledgeItem(
                tenant_id=tenant.id,
                title=row.title[:240],
                answer=row.answer,
                category=row.category[:80],
                status=row.status,
            )
            session.add(item)
            session.flush()
            snapshot_knowledge_item_version(session, item, "knowledge_import", f"从 {payload.filename or payload.source_type} 导入知识条目")
            created_items.append(item)
            continue
        gap = KnowledgeGap(
            tenant_id=tenant.id,
            question=(row.question or row.title)[:500],
            suggested_answer=row.answer,
            category=row.category[:80],
            status="pending",
            examples_json=[{
                "import_batch_id": batch.id,
                "filename": payload.filename,
                "source_type": payload.source_type,
                "source_excerpt": row.source_excerpt,
            }],
        )
        session.add(gap)
        session.flush()
        created_gaps.append(gap)
    batch.imported_count = len(created_items) + len(created_gaps)
    batch.skipped_count = skipped
    batch.error_count = skipped
    batch.metadata_json = {
        **(batch.metadata_json or {}),
        "created_item_ids": [item.id for item in created_items],
        "created_gap_ids": [gap.id for gap in created_gaps],
    }
    session.add(batch)
    append_audit_log(
        session,
        tenant.id,
        "knowledge_import_confirmed",
        f"{current_user.display_name} 导入知识 {batch.imported_count} 条",
        operator=current_user,
        scope_type="knowledge",
        object_type="import_batch",
        object_id=batch.id,
        status="completed",
        detail_json=batch.metadata_json,
    )
    session.commit()
    session.refresh(batch)
    for item in created_items:
        session.refresh(item)
    for gap in created_gaps:
        session.refresh(gap)
    return KnowledgeImportConfirmResult(
        batch=batch,
        created_items=created_items,
        created_gaps=created_gaps,
        preview=preview,
    )


def parse_raw_import(payload: RawImportRequest) -> list[ImportRecord]:
    if payload.source_type == "csv":
        return parse_csv_records(payload.content.encode("utf-8"))
    if payload.source_type == "json":
        try:
            parsed = json.loads(payload.content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        rows = parsed.get("records", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(rows, list):
            raise HTTPException(status_code=400, detail="JSON import must be an array or contain records[]")
        return [
            row if isinstance(row, ImportRecord) else record_from_mapping(row, default_channel="local_json")
            for row in rows
            if isinstance(row, dict)
        ]
    return [
        ImportRecord(
            text=line.strip(),
            sender_name="本地粘贴",
            channel="local_text",
            conversation_id=payload.filename or "pasted-text",
            conversation_name=payload.filename or "Pasted Text",
        )
        for line in payload.content.splitlines()
        if line.strip()
    ]


def count_for_messages(session, model, tenant_id: int, message_ids: list[int]) -> int:
    if not message_ids:
        return 0
    return len(
        session.exec(
            select(model).where(
                model.tenant_id == tenant_id,
                model.source_message_id.in_(message_ids),  # type: ignore[attr-defined]
            )
        ).all()
    )


def count_agent_runs_for_messages(session, tenant_id: int, message_ids: list[int]) -> int:
    if not message_ids:
        return 0
    return len(
        session.exec(
            select(AgentRun).where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.message_id.in_(message_ids),  # type: ignore[union-attr]
            )
        ).all()
    )


def build_knowledge_import_preview(payload: KnowledgeImportRequest) -> KnowledgeImportPreviewResult:
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Knowledge import content is empty")
    if payload.source_type == "csv":
        rows = parse_knowledge_csv(payload)
    elif payload.source_type == "faq":
        rows = parse_knowledge_faq(payload)
    else:
        rows = parse_knowledge_markdown(payload)
    return KnowledgeImportPreviewResult(
        source_type=payload.source_type,
        filename=payload.filename,
        total_rows=len(rows),
        rows=rows,
        warnings=[] if rows else ["No knowledge rows parsed"],
    )


def parse_knowledge_csv(payload: KnowledgeImportRequest) -> list[KnowledgeImportPreviewRow]:
    reader = csv.DictReader(io.StringIO(payload.content))
    rows: list[KnowledgeImportPreviewRow] = []
    for index, raw in enumerate(reader, start=1):
        title = first_value(raw, "title", "标题", "question", "问题", "q") or f"导入知识 {index}"
        question = first_value(raw, "question", "问题", "q") or title
        answer = first_value(raw, "answer", "答案", "a", "content", "正文") or ""
        category = first_value(raw, "category", "分类") or payload.default_category
        mode = normalize_import_mode(first_value(raw, "mode", "类型") or payload.default_mode, answer)
        status = normalize_import_status(first_value(raw, "status", "状态"), payload.publish)
        rows.append(preview_row(index, mode, title, question, answer, category, status, str(raw)))
    return rows


def parse_knowledge_faq(payload: KnowledgeImportRequest) -> list[KnowledgeImportPreviewRow]:
    pairs: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in payload.content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        question_match = re.match(r"^(?:Q|Question|问|问题)[:：]\s*(.+)$", stripped, re.IGNORECASE)
        answer_match = re.match(r"^(?:A|Answer|答|答案)[:：]\s*(.+)$", stripped, re.IGNORECASE)
        if question_match:
            if current:
                pairs.append(current)
            current = {"question": question_match.group(1).strip(), "answer": ""}
        elif answer_match:
            current["answer"] = f"{current.get('answer', '')}\n{answer_match.group(1).strip()}".strip()
        elif current:
            current["answer"] = f"{current.get('answer', '')}\n{stripped}".strip()
    if current:
        pairs.append(current)
    return [
        preview_row(
            index,
            normalize_import_mode(payload.default_mode, pair.get("answer", "")),
            pair.get("question") or f"FAQ {index}",
            pair.get("question") or f"FAQ {index}",
            pair.get("answer", ""),
            payload.default_category,
            "published" if payload.publish else "draft",
            f"Q: {pair.get('question', '')}\nA: {pair.get('answer', '')}",
        )
        for index, pair in enumerate(pairs, start=1)
    ]


def parse_knowledge_markdown(payload: KnowledgeImportRequest) -> list[KnowledgeImportPreviewRow]:
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in payload.content.splitlines():
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            if current_title or current_lines:
                sections.append((current_title or f"Markdown Section {len(sections) + 1}", "\n".join(current_lines).strip()))
            current_title = heading.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title or current_lines:
        sections.append((current_title or f"Markdown Section {len(sections) + 1}", "\n".join(current_lines).strip()))
    return [
        preview_row(
            index,
            normalize_import_mode(payload.default_mode, body),
            title,
            title,
            body,
            payload.default_category,
            "published" if payload.publish else "draft",
            f"# {title}\n{body}",
        )
        for index, (title, body) in enumerate(sections, start=1)
        if title.strip() or body.strip()
    ]


def preview_row(
    index: int,
    mode: str,
    title: str,
    question: str,
    answer: str,
    category: str,
    status: str,
    source_excerpt: str,
) -> KnowledgeImportPreviewRow:
    warnings: list[str] = []
    if not title.strip() and mode == "item":
        warnings.append("Missing title")
    if not question.strip():
        warnings.append("Missing question")
    if mode == "item" and not answer.strip():
        warnings.append("KnowledgeItem answer is empty")
    return KnowledgeImportPreviewRow(
        row_index=index,
        mode=mode,
        title=title.strip()[:240] or question.strip()[:240] or f"导入知识 {index}",
        question=question.strip()[:500] or title.strip()[:500],
        answer=answer.strip(),
        category=(category or "general").strip()[:80],
        status=status,
        source_excerpt=source_excerpt[:500],
        warnings=warnings,
    )


def normalize_import_mode(raw: Any, answer: str) -> str:
    value = str(raw or "").lower()
    if value in {"gap", "knowledge_gap", "缺口"}:
        return "gap"
    if value in {"item", "knowledge_item", "知识条目"}:
        return "item"
    return "item" if answer.strip() else "gap"


def normalize_import_status(raw: Any, publish: bool) -> str:
    value = str(raw or "").lower()
    if value in {"draft", "pending_review", "published", "archived"}:
        return value
    return "published" if publish else "draft"


def first_value(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None
