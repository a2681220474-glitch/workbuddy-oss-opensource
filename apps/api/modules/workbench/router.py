from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import Approval, AuditLog, FollowupTask
from apps.api.modules.audit.service import serialize_audit_logs
from apps.api.modules.display import enrich_approval
from apps.api.modules.users.service import local_user_summary, serialize_task
from apps.api.schemas import WorkbenchSummary


router = APIRouter()


@router.get("/me", response_model=WorkbenchSummary)
def my_workbench(
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> WorkbenchSummary:
    task_rows = session.exec(
        select(FollowupTask)
        .where(FollowupTask.tenant_id == tenant.id, FollowupTask.assignee_user_id == current_user.id)
        .order_by(FollowupTask.created_at.desc(), FollowupTask.id.desc())
        .limit(40)
    ).all()
    my_tasks = sorted(
        [task for task in task_rows if task.status not in {"done", "cancelled"}],
        key=lambda task: (task.due_at is None, task.due_at or task.created_at, -int(task.id or 0)),
    )
    my_overdue = [task for task in my_tasks if task.is_overdue]
    unassigned_rows = session.exec(
        select(FollowupTask)
        .where(
            FollowupTask.tenant_id == tenant.id,
            FollowupTask.assignee_user_id.is_(None),
            FollowupTask.status.notin_(["done", "cancelled"]),
        )
        .order_by(FollowupTask.created_at.desc(), FollowupTask.id.desc())
        .limit(12)
    ).all()

    approval_rows: list[Approval] = []
    if current_user.role in {"admin", "approver"}:
        approval_rows = session.exec(
            select(Approval)
            .where(Approval.tenant_id == tenant.id, Approval.status == "pending_review")
            .order_by(Approval.created_at.desc(), Approval.id.desc())
            .limit(20)
        ).all()

    recent_logs = session.exec(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant.id, AuditLog.operator_user_id == current_user.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(12)
    ).all()
    task_user_map = {current_user.id: current_user} if current_user.id is not None else {}

    return WorkbenchSummary(
        current_user=local_user_summary(current_user),
        summary={
            "my_open_tasks": len(my_tasks),
            "my_overdue_tasks": len(my_overdue),
            "unassigned_tasks": len(unassigned_rows),
            "my_pending_approvals": len(approval_rows),
            "recent_actions": len(recent_logs),
        },
        my_tasks=[serialize_task(task, task_user_map) for task in my_tasks[:12]],
        my_overdue_tasks=[serialize_task(task, task_user_map) for task in my_overdue[:12]],
        unassigned_tasks=[serialize_task(task) for task in unassigned_rows],
        my_pending_approvals=[enrich_approval(session, approval) for approval in approval_rows],
        recent_activity=serialize_audit_logs(session, tenant.id, list(recent_logs)),
    )
