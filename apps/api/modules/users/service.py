from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, select

from apps.api.models import FollowupTask, LocalUser, ProcessingRecord
from apps.api.schemas import FollowupTaskRead, LocalUserSummary, ProcessingRecordRead


def get_local_user(session: Session, tenant_id: int, user_id: int | None) -> LocalUser | None:
    if user_id is None:
        return None
    user = session.get(LocalUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        return None
    return user


def get_local_user_map(session: Session, tenant_id: int, user_ids: Iterable[int | None]) -> dict[int, LocalUser]:
    normalized_ids = sorted({user_id for user_id in user_ids if user_id is not None})
    if not normalized_ids:
        return {}
    rows = session.exec(
        select(LocalUser).where(LocalUser.tenant_id == tenant_id, LocalUser.id.in_(normalized_ids))
    ).all()
    return {user.id: user for user in rows if user.id is not None}


def local_user_summary(user: LocalUser | None) -> LocalUserSummary | None:
    if user is None or user.id is None:
        return None
    return LocalUserSummary(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
    )


def apply_assignee_user(target: FollowupTask | ProcessingRecord, user: LocalUser | None) -> None:
    if user is None or user.id is None:
        target.assignee_user_id = None
        target.assignee_username = None
        target.assignee_name = None
        return
    target.assignee_user_id = user.id
    target.assignee_username = user.username
    target.assignee_name = user.display_name


def serialize_task(task: FollowupTask, user_map: dict[int, LocalUser] | None = None) -> FollowupTaskRead:
    user = None
    if user_map and task.assignee_user_id is not None:
        user = user_map.get(task.assignee_user_id)
    return FollowupTaskRead(
        id=task.id,
        tenant_id=task.tenant_id,
        source_message_id=task.source_message_id,
        agent_run_id=task.agent_run_id,
        title=task.title,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        related_object_type=task.related_object_type,
        related_object_id=task.related_object_id,
        assignee_user_id=task.assignee_user_id,
        assignee_username=task.assignee_username,
        assignee_name=task.assignee_name,
        assignee_user=local_user_summary(user),
        due_hint=task.due_hint,
        due_at=task.due_at,
        is_overdue=task.is_overdue,
        summary=task.summary,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )


def serialize_processing_record(
    record: ProcessingRecord,
    assignee_user_map: dict[int, LocalUser] | None = None,
    operator_user_map: dict[int, LocalUser] | None = None,
) -> ProcessingRecordRead:
    assignee_user = None
    operator_user = None
    if assignee_user_map and record.assignee_user_id is not None:
        assignee_user = assignee_user_map.get(record.assignee_user_id)
    if operator_user_map and record.operator_user_id is not None:
        operator_user = operator_user_map.get(record.operator_user_id)
    return ProcessingRecordRead(
        id=record.id,
        tenant_id=record.tenant_id,
        object_type=record.object_type,
        object_id=record.object_id,
        action_type=record.action_type,
        status=record.status,
        assignee_user_id=record.assignee_user_id,
        assignee_username=record.assignee_username,
        assignee_name=record.assignee_name,
        assignee_user=local_user_summary(assignee_user),
        due_hint=record.due_hint,
        due_at=record.due_at,
        next_step=record.next_step,
        note=record.note,
        operator_user_id=record.operator_user_id,
        operator_username=record.operator_username,
        operator_name=record.operator_name,
        operator_user=local_user_summary(operator_user),
        created_at=record.created_at,
    )
