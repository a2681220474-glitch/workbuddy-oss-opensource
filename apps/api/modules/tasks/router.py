from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import FollowupTask, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.users.service import apply_assignee_user, get_local_user, get_local_user_map, serialize_task
from apps.api.schemas import FollowupTaskRead, FollowupTaskUpdate


router = APIRouter()


@router.get("", response_model=list[FollowupTaskRead])
def list_tasks(
    session: SessionDep,
    tenant: TenantDep,
    status: str | None = None,
    assignee_name: str | None = None,
    assignee_user_id: int | None = None,
    overdue: bool | None = None,
) -> list[FollowupTaskRead]:
    statement = select(FollowupTask).where(FollowupTask.tenant_id == tenant.id)
    if status:
        statement = statement.where(FollowupTask.status == status)
    if assignee_name:
        statement = statement.where(FollowupTask.assignee_name == assignee_name)
    if assignee_user_id is not None:
        statement = statement.where(FollowupTask.assignee_user_id == assignee_user_id)
    if overdue is True:
        statement = statement.where(
            FollowupTask.due_at.is_not(None),
            FollowupTask.due_at < utc_now(),
            FollowupTask.status.notin_(["done", "cancelled"]),
        )
    statement = statement.order_by(FollowupTask.created_at.desc(), FollowupTask.id.desc())
    tasks = list(session.exec(statement).all())
    user_map = get_local_user_map(session, tenant.id, [task.assignee_user_id for task in tasks])
    return [serialize_task(task, user_map) for task in tasks]


@router.patch("/{task_id}", response_model=FollowupTaskRead)
def update_task(
    task_id: int,
    payload: FollowupTaskUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> FollowupTaskRead:
    task = session.get(FollowupTask, task_id)
    if task is None or task.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role == "readonly":
        raise HTTPException(status_code=403, detail="Readonly user cannot update tasks")
    if payload.status is not None:
        task.status = payload.status
        task.completed_at = utc_now() if payload.status == "done" else None
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.assignee_user_id is not None:
        assignee_user = get_local_user(session, tenant.id, payload.assignee_user_id)
        if assignee_user is None:
            raise HTTPException(status_code=404, detail="Assignee user not found")
        apply_assignee_user(task, assignee_user)
    if payload.assignee_name is not None:
        task.assignee_name = payload.assignee_name or None
        if payload.assignee_name == "":
            task.assignee_user_id = None
            task.assignee_username = None
    if payload.due_hint is not None:
        task.due_hint = payload.due_hint or None
    if payload.due_at is not None:
        task.due_at = payload.due_at
    if payload.summary is not None:
        task.summary = payload.summary
    task.updated_at = utc_now()
    session.add(task)
    append_audit_log(
        session,
        tenant.id,
        "task_updated",
        f"更新任务 #{task.id}：{task.title}",
        operator=current_user,
        scope_type="task",
        scope_id=task.id,
        object_type=task.related_object_type or "task",
        object_id=task.related_object_id or task.id,
        status=task.status,
        detail_json={
            "priority": task.priority,
            "assignee_user_id": task.assignee_user_id,
            "assignee_name": task.assignee_name,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        },
    )
    session.commit()
    session.refresh(task)
    user_map = get_local_user_map(session, tenant.id, [task.assignee_user_id])
    return serialize_task(task, user_map)
