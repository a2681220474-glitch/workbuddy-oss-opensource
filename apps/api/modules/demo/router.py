from pathlib import Path

from fastapi import APIRouter
from sqlmodel import delete, func, select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import (
    AgentRun,
    Approval,
    Candidate,
    Channel,
    ChannelEvent,
    Conversation,
    ExternalUser,
    FollowupTask,
    ImportBatch,
    KnowledgeGap,
    KnowledgeItem,
    Lead,
    MessageEvent,
    Report,
    Ticket,
)
from apps.api.modules.imports.parsers import parse_csv_records
from apps.api.modules.imports.service import import_records
from apps.api.modules.adapters.feishu import feishu_message_to_import_record
from apps.api.schemas import DemoResetResult


router = APIRouter()


@router.post("/reset", response_model=DemoResetResult)
def reset_demo_data(session: SessionDep, tenant: TenantDep) -> DemoResetResult:
    deleted = delete_tenant_demo_data(session, tenant.id)
    demo_dir = Path(__file__).resolve().parents[4] / "examples"
    imported_batches = []
    for filename in demo_filenames():
        records = parse_csv_records((demo_dir / filename).read_bytes())
        batch, _ = import_records(session, tenant, records, source="csv", filename=filename)
        imported_batches.append(batch)
    for index, record in enumerate(demo_feishu_records(), start=1):
        batch, _ = import_records(session, tenant, [record], source="feishu_demo_payload", filename=f"feishu-demo-{index}.json")
        imported_batches.append(batch)

    return DemoResetResult(
        deleted=deleted,
        imported_batches=imported_batches,
        message_count=count(session, MessageEvent, tenant.id),
        ticket_count=count(session, Ticket, tenant.id),
        lead_count=count(session, Lead, tenant.id),
        task_count=count(session, FollowupTask, tenant.id),
        approval_count=count(session, Approval, tenant.id),
        agent_run_count=count(session, AgentRun, tenant.id),
    )


@router.post("/prepare")
def prepare_demo_environment(session: SessionDep, tenant: TenantDep) -> dict[str, object]:
    deleted = delete_local_demo_data(session, tenant.id)
    demo_dir = Path(__file__).resolve().parents[4] / "examples"
    imported_batches = []
    imported_message_ids: list[int] = []
    for filename in demo_filenames():
        records = parse_csv_records((demo_dir / filename).read_bytes())
        batch, messages = import_records(session, tenant, records, source="csv", filename=filename)
        imported_batches.append(batch)
        imported_message_ids.extend([message.id for message in messages if message.id is not None])
    for index, record in enumerate(demo_feishu_records(), start=1):
        batch, messages = import_records(session, tenant, [record], source="feishu_demo_payload", filename=f"feishu-demo-{index}.json")
        imported_batches.append(batch)
        imported_message_ids.extend([message.id for message in messages if message.id is not None])
    promoted_items = promote_knowledge_gaps(session, tenant.id)
    generated_reports = generate_demo_reports(session, tenant.id)
    restored_conversations = restore_conversation_policies(session, tenant.id)
    object_counts = business_object_counts(session, tenant.id)
    validation_report = build_validation_report(session, tenant.id, object_counts)
    return {
        "status": "ready",
        "deleted_local_demo": deleted,
        "imported_batches": [serialize_import_batch(batch) for batch in imported_batches],
        "created_from_import": created_counts_for_messages(session, tenant.id, imported_message_ids),
        "business_object_counts": object_counts,
        "business_object_total": sum(
            object_counts[key]
            for key in ("tickets", "leads", "tasks", "candidates", "knowledge_gaps", "knowledge_items", "reports")
        ),
        "promoted_knowledge_items": promoted_items,
        "generated_reports": generated_reports,
        "validation_report": validation_report,
        "restored_conversations": restored_conversations,
        "next_message": "群里有人吗？我想报名训练营，怎么买？",
        "recommended_flow": [
            {"label": "导入或发送测试消息", "target": "#import"},
            {"label": "查看消息事件", "target": "#messages"},
            {"label": "查看业务对象中心", "target": "#objects"},
            {"label": "推进客服工单", "target": "#tickets"},
            {"label": "推进销售线索", "target": "#leads"},
            {"label": "检查社群运营", "target": "#community"},
            {"label": "检查候选入职", "target": "#candidates"},
            {"label": "沉淀知识条目", "target": "#knowledge"},
            {"label": "生成并查看报告", "target": "#reports"},
            {"label": "检查审批队列", "target": "#approvals"},
            {"label": "追踪运行日志", "target": "#agent-runs"},
        ],
    }


def demo_filenames() -> tuple[str, ...]:
    return (
        "demo_support_messages.csv",
        "demo_sales_messages.csv",
        "demo_business_alpha_messages.csv",
    )


def demo_feishu_records() -> list:
    payloads = [
        feishu_demo_payload(
            message_id="feishu-demo-file-001",
            chat_id="oc_demo_sales_file",
            chat_type="p2p",
            open_id="ou_demo_sales_owner",
            sender_name="飞书测试用户A",
            create_time="1770036600000",
            message_type="file",
            content={
                "file_key": "file_demo_quote_001",
                "file_name": "报价方案-v0.15.pdf",
            },
        ),
        feishu_demo_payload(
            message_id="feishu-demo-post-001",
            chat_id="oc_demo_recruiting_post",
            chat_type="p2p",
            open_id="ou_demo_candidate_owner",
            sender_name="飞书测试用户B",
            create_time="1770036900000",
            message_type="post",
            content={
                "zh_cn": {
                    "title": "候选人简历摘要",
                    "content": [
                        [
                            {"tag": "text", "text": "候选人王宁，应聘销售岗位，5 年 SaaS 销售经验，希望安排面试。"}
                        ]
                    ],
                }
            },
        ),
        feishu_demo_payload(
            message_id="feishu-demo-image-001",
            chat_id="oc_demo_support_image",
            chat_type="group",
            open_id="ou_demo_support_owner",
            sender_name="飞书测试用户C",
            create_time="1770037200000",
            message_type="image",
            content={
                "image_key": "img_demo_error_001",
            },
        ),
    ]
    return [feishu_message_to_import_record(payload) for payload in payloads]


def feishu_demo_payload(
    *,
    message_id: str,
    chat_id: str,
    chat_type: str,
    open_id: str,
    sender_name: str,
    create_time: str,
    message_type: str,
    content: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": f"evt_{message_id}",
            "event_type": "im.message.receive_v1",
            "create_time": create_time,
            "token": "demo",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": open_id},
                "sender_name": sender_name,
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": message_type,
                "create_time": create_time,
                "content": json_dumps(content),
            },
        },
    }


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def promote_knowledge_gaps(session, tenant_id: int) -> list[dict[str, object]]:
    gaps = session.exec(
        select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant_id, KnowledgeGap.status == "pending")
    ).all()
    promoted: list[dict[str, object]] = []
    for gap in gaps:
        item = KnowledgeItem(
            tenant_id=tenant_id,
            source_gap_id=gap.id,
            title=gap.question[:240],
            answer=gap.suggested_answer or "已记录为待完善知识条目，人工确认后补充标准答案。",
            category=gap.category,
            status="published",
        )
        gap.status = "accepted"
        session.add(gap)
        session.add(item)
        session.flush()
        promoted.append({"gap_id": gap.id, "item_id": item.id, "title": item.title})
    session.commit()
    return promoted


def generate_demo_reports(session, tenant_id: int) -> list[dict[str, object]]:
    from apps.api.modules.reports.router import build_report_data, report_prompt_version

    report_types = (
        "operations_daily",
        "support_daily",
        "sales_daily",
        "community_daily",
        "recruiting_progress",
        "knowledge_gap",
    )
    generated: list[dict[str, object]] = []
    for report_type in report_types:
        data = build_report_data(session, tenant_id, report_type)
        run = AgentRun(
            tenant_id=tenant_id,
            agent_type="report_agent",
            status="success",
            prompt_version=report_prompt_version(report_type),
            prompt_json={"report_type": report_type, "scope_type": "tenant", "demo_prepare": True},
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
            scope_type="tenant",
            title=data["title"],
            summary=data["summary"],
            metrics_json=data["metrics"],
            sections_json=data["sections"],
            source_message_ids=data["source_message_ids"],
        )
        session.add(report)
        session.flush()
        generated.append({"id": report.id, "report_type": report.report_type, "title": report.title})
    session.commit()
    return generated


def build_validation_report(session, tenant_id: int, object_counts: dict[str, int]) -> dict[str, object]:
    agent_runs = session.exec(select(AgentRun).where(AgentRun.tenant_id == tenant_id)).all()
    approvals = session.exec(select(Approval).where(Approval.tenant_id == tenant_id)).all()
    checks = [
        validation_check("message_import", "消息导入", object_counts["messages"] >= 10, f"{object_counts['messages']} 条消息"),
        validation_check("support_agent", "客服工单知识 Agent", object_counts["tickets"] > 0, f"{object_counts['tickets']} 个工单"),
        validation_check("sales_agent", "销售线索跟进 Agent", object_counts["leads"] > 0, f"{object_counts['leads']} 条线索"),
        validation_check("community_agent", "私域社群运营 Agent", any(run.agent_type == "community_ops_agent" for run in agent_runs), "已产生社群 AgentRun"),
        validation_check("recruiting_agent", "招聘与入职 Agent", object_counts["candidates"] > 0, f"{object_counts['candidates']} 个候选人"),
        validation_check("knowledge_loop", "知识沉淀", object_counts["knowledge_items"] > 0, f"{object_counts['knowledge_items']} 条知识"),
        validation_check("report_loop", "报告生成", object_counts["reports"] >= 6, f"{object_counts['reports']} 份报告"),
        validation_check("approval_audit", "审批与审计", object_counts["approvals"] > 0 and object_counts["agent_runs"] > 0, f"{len(approvals)} 条审批 / {object_counts['agent_runs']} 条运行日志"),
    ]
    passed = sum(1 for check in checks if check["status"] == "passed")
    return {
        "title": "Business Alpha Beta 验收报告",
        "passed": passed,
        "total": len(checks),
        "ready_for_beta": passed == len(checks),
        "checks": checks,
    }


def validation_check(key: str, label: str, passed: bool, detail: str) -> dict[str, object]:
    return {"key": key, "label": label, "status": "passed" if passed else "failed", "detail": detail}


def business_object_counts(session, tenant_id: int) -> dict[str, int]:
    return {
        "tickets": count(session, Ticket, tenant_id),
        "leads": count(session, Lead, tenant_id),
        "tasks": count(session, FollowupTask, tenant_id),
        "candidates": count(session, Candidate, tenant_id),
        "knowledge_gaps": count(session, KnowledgeGap, tenant_id),
        "knowledge_items": count(session, KnowledgeItem, tenant_id),
        "reports": count(session, Report, tenant_id),
        "approvals": count(session, Approval, tenant_id),
        "agent_runs": count(session, AgentRun, tenant_id),
        "messages": count(session, MessageEvent, tenant_id),
    }


def created_counts_for_messages(session, tenant_id: int, message_ids: list[int]) -> dict[str, int]:
    if not message_ids:
        return {"tickets": 0, "leads": 0, "tasks": 0, "candidates": 0, "knowledge_gaps": 0, "approvals": 0, "agent_runs": 0}
    run_ids = list(
        session.exec(
            select(AgentRun.id).where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.message_id.in_(message_ids),  # type: ignore[union-attr]
            )
        ).all()
    )
    return {
        "tickets": count_for_messages(session, Ticket, tenant_id, message_ids),
        "leads": count_for_messages(session, Lead, tenant_id, message_ids),
        "tasks": count_for_messages(session, FollowupTask, tenant_id, message_ids),
        "candidates": count_for_messages(session, Candidate, tenant_id, message_ids),
        "knowledge_gaps": count_for_messages(session, KnowledgeGap, tenant_id, message_ids),
        "approvals": count_for_runs(session, Approval, tenant_id, run_ids),
        "agent_runs": len(run_ids),
    }


def count_for_messages(session, model, tenant_id: int, message_ids: list[int]) -> int:
    return len(
        session.exec(
            select(model).where(
                model.tenant_id == tenant_id,
                model.source_message_id.in_(message_ids),  # type: ignore[attr-defined]
            )
        ).all()
    )


def count_for_runs(session, model, tenant_id: int, run_ids: list[int]) -> int:
    if not run_ids:
        return 0
    return len(
        session.exec(
            select(model).where(
                model.tenant_id == tenant_id,
                model.agent_run_id.in_(run_ids),  # type: ignore[attr-defined]
            )
        ).all()
    )


def delete_local_demo_data(session, tenant_id: int) -> dict[str, int]:
    feishu_channels = session.exec(
        select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "feishu")
    ).all()
    feishu_channel_ids = {channel.id for channel in feishu_channels if channel.id is not None}
    feishu_messages = []
    if feishu_channel_ids:
        feishu_messages = session.exec(
            select(MessageEvent).where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(feishu_channel_ids))
        ).all()
    feishu_message_ids = {message.id for message in feishu_messages if message.id is not None}
    feishu_run_ids = {
        run.id
        for run in session.exec(
            select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.message_id.in_(feishu_message_ids))
        ).all()
        if run.id is not None
    } if feishu_message_ids else set()

    deleted: dict[str, int] = {}
    for model in (Approval, FollowupTask, Ticket, Lead, Candidate):
        rows = session.exec(select(model).where(model.tenant_id == tenant_id)).all()
        doomed = [row for row in rows if getattr(row, "source_message_id", None) not in feishu_message_ids]
        deleted[model.__tablename__] = len(doomed)
        for row in doomed:
            session.delete(row)

    for model in (KnowledgeItem, Report):
        rows = session.exec(select(model).where(model.tenant_id == tenant_id)).all()
        deleted[model.__tablename__] = len(rows)
        for row in rows:
            session.delete(row)

    gaps = session.exec(select(KnowledgeGap).where(KnowledgeGap.tenant_id == tenant_id)).all()
    doomed_gaps = [gap for gap in gaps if gap.source_message_id not in feishu_message_ids]
    deleted[KnowledgeGap.__tablename__] = len(doomed_gaps)
    for gap in doomed_gaps:
        session.delete(gap)

    runs = session.exec(select(AgentRun).where(AgentRun.tenant_id == tenant_id)).all()
    doomed_runs = [
        run
        for run in runs
        if (run.message_id is not None and run.message_id not in feishu_message_ids)
        or (run.message_id is None and run.id not in feishu_run_ids and run.agent_type != "feishu_send_adapter")
    ]
    deleted[AgentRun.__tablename__] = len(doomed_runs)
    for run in doomed_runs:
        session.delete(run)

    messages = session.exec(select(MessageEvent).where(MessageEvent.tenant_id == tenant_id)).all()
    doomed_messages = [message for message in messages if message.id not in feishu_message_ids]
    deleted[MessageEvent.__tablename__] = len(doomed_messages)
    for message in doomed_messages:
        session.delete(message)

    batches = session.exec(select(ImportBatch).where(ImportBatch.tenant_id == tenant_id, ImportBatch.source != "feishu_stream")).all()
    deleted[ImportBatch.__tablename__] = len(batches)
    for batch in batches:
        session.delete(batch)

    conversations = session.exec(select(Conversation).where(Conversation.tenant_id == tenant_id)).all()
    doomed_conversations = [conversation for conversation in conversations if conversation.channel_id not in feishu_channel_ids]
    deleted[Conversation.__tablename__] = len(doomed_conversations)
    for conversation in doomed_conversations:
        session.delete(conversation)

    channels = session.exec(select(Channel).where(Channel.tenant_id == tenant_id, Channel.type != "feishu")).all()
    deleted[Channel.__tablename__] = len(channels)
    for channel in channels:
        session.delete(channel)

    session.commit()
    return deleted


def restore_conversation_policies(session, tenant_id: int) -> list[dict[str, object]]:
    conversations = session.exec(
        select(Conversation)
        .join(Channel, Conversation.channel_id == Channel.id)
        .where(Conversation.tenant_id == tenant_id, Channel.type == "feishu")
    ).all()
    restored = []
    for conversation in conversations:
        conversation.bound_agent = None
        conversation.send_mode = "inherit"
        session.add(conversation)
        restored.append({"id": conversation.id, "name": conversation.name, "bound_agent": "auto", "send_mode": "inherit"})
    session.commit()
    return restored


def serialize_import_batch(batch: ImportBatch) -> dict[str, object]:
    return {
        "id": batch.id,
        "source": batch.source,
        "filename": batch.filename,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "imported_count": batch.imported_count,
        "error_count": batch.error_count,
    }


def delete_tenant_demo_data(session, tenant_id: int) -> dict[str, int]:
    models = [
        Approval,
        FollowupTask,
        Candidate,
        KnowledgeItem,
        KnowledgeGap,
        Report,
        Ticket,
        Lead,
        AgentRun,
        MessageEvent,
        ImportBatch,
        Conversation,
        Channel,
        ChannelEvent,
        ExternalUser,
    ]
    deleted: dict[str, int] = {}
    for model in models:
        rows = session.exec(select(model).where(model.tenant_id == tenant_id)).all()
        deleted[model.__tablename__] = len(rows)
        session.exec(delete(model).where(model.tenant_id == tenant_id))
    session.commit()
    return deleted


def count(session, model, tenant_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    ).one()
