from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlmodel import Session, select

from apps.api.models import BEIJING_TZ, Approval, FollowupTask, Report, Tenant, Ticket, utc_now
from apps.api.modules.approvals.delivery import (
    SENDABLE_APPROVAL_STATUSES,
    delivery_retry_policy,
    latest_delivery_run_for_approval,
    send_approval_reply,
)
from apps.api.modules.reports.router import create_report


def run_runtime_job_cycle(session: Session) -> dict[str, Any]:
    approval_retry = retry_failed_approval_deliveries(session)
    overdue = scan_overdue_objects(session)
    reports = generate_scheduled_reports(session)
    summary = {
        "occurred_at": datetime.now().astimezone().isoformat(),
        "approval_retry_scan": approval_retry,
        "overdue_scan": overdue,
        "scheduled_reports": reports,
    }
    return summary


def retry_failed_approval_deliveries(session: Session) -> dict[str, Any]:
    approvals = session.exec(
        select(Approval)
        .where(Approval.status.in_(tuple(SENDABLE_APPROVAL_STATUSES)))
        .order_by(Approval.created_at.asc(), Approval.id.asc())
    ).all()
    checked = 0
    retry_ready = 0
    sent = 0
    failed = 0
    skipped = 0
    details: list[dict[str, Any]] = []
    for approval in approvals:
        previous = latest_delivery_run_for_approval(session, approval)
        if previous is None or previous.status != "failed":
            continue
        checked += 1
        attempts = int((previous.action_json or {}).get("delivery_attempt") or 0)
        policy = delivery_retry_policy(previous, attempts)
        if not policy.get("retry_allowed", False):
            skipped += 1
            continue
        retry_ready += 1
        try:
            send_approval_reply(session, approval)
            sent += 1
            details.append({"approval_id": approval.id, "status": "sent"})
        except Exception as exc:  # noqa: BLE001 - worker should keep going and summarize failures
            failed += 1
            details.append({"approval_id": approval.id, "status": "failed", "error": str(exc)})
    return {
        "checked": checked,
        "retry_ready": retry_ready,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "details": details[:12],
    }


def scan_overdue_objects(session: Session) -> dict[str, Any]:
    now = utc_now()
    overdue_tasks = session.exec(
        select(FollowupTask).where(FollowupTask.due_at.is_not(None), FollowupTask.status.notin_(["done", "cancelled"]))
    ).all()
    overdue_task_ids = [task.id for task in overdue_tasks if task.due_at and ensure_tz(task.due_at) < now and task.id is not None]

    open_tickets = session.exec(
        select(Ticket).where(Ticket.status.in_(["open", "in_progress", "waiting_customer"]))
    ).all()
    stale_ticket_ids = [
        ticket.id
        for ticket in open_tickets
        if ticket.updated_at is not None and ensure_tz(ticket.updated_at) < now.replace(hour=0, minute=0, second=0, microsecond=0) and ticket.id is not None
    ]
    return {
        "overdue_task_count": len(overdue_task_ids),
        "overdue_task_ids": overdue_task_ids[:20],
        "stale_open_ticket_count": len(stale_ticket_ids),
        "stale_open_ticket_ids": stale_ticket_ids[:20],
    }


def generate_scheduled_reports(session: Session) -> dict[str, Any]:
    report_types = ["operations_daily", "support_daily", "sales_daily", "community_daily", "recruiting_progress", "knowledge_gap"]
    today = datetime.now(BEIJING_TZ).date()
    scope_id = today.isoformat()
    tenants = session.exec(select(Tenant).order_by(Tenant.id.asc())).all()
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for tenant in tenants:
        if tenant.id is None:
            continue
        for report_type in report_types:
            if scheduled_report_exists(session, tenant.id, report_type, scope_id):
                skipped.append({"tenant_id": tenant.id, "report_type": report_type, "reason": "already_generated"})
                continue
            try:
                report = create_report(
                    session=session,
                    tenant_id=tenant.id,
                    report_type=report_type,
                    scope_type="scheduled_daily",
                    scope_id=scope_id,
                )
                session.flush()
                generated.append({"tenant_id": tenant.id, "report_type": report_type, "report_id": report.id})
                session.commit()
            except Exception as exc:  # noqa: BLE001 - keep other reports moving
                session.rollback()
                failed.append({"tenant_id": tenant.id, "report_type": report_type, "error": str(exc)})
    return {
        "status": "ok" if not failed else "partial_failure",
        "date": scope_id,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "generated": generated[:20],
        "skipped": skipped[:20],
        "failed": failed[:12],
    }


def scheduled_report_exists(session: Session, tenant_id: int, report_type: str, scope_id: str) -> bool:
    existing = session.exec(
        select(Report).where(
            Report.tenant_id == tenant_id,
            Report.report_type == report_type,
            Report.scope_type == "scheduled_daily",
            Report.scope_id == scope_id,
        )
    ).first()
    if existing is not None:
        return True
    # Backward-compatible guard for any older scheduled reports created without scope_id.
    day = datetime.fromisoformat(scope_id).date()
    start = datetime.combine(day, time.min, tzinfo=BEIJING_TZ)
    end = datetime.combine(day, time.max, tzinfo=BEIJING_TZ)
    return (
        session.exec(
            select(Report).where(
                Report.tenant_id == tenant_id,
                Report.report_type == report_type,
                Report.scope_type == "scheduled_daily",
                Report.created_at >= start,
                Report.created_at <= end,
            )
        ).first()
        is not None
    )


def ensure_tz(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
