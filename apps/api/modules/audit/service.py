from __future__ import annotations

from typing import Any

from sqlmodel import Session

from apps.api.models import AuditLog, LocalUser
from apps.api.schemas import AuditLogRead
from apps.api.modules.users.service import get_local_user_map, local_user_summary


def append_audit_log(
    session: Session,
    tenant_id: int,
    action_type: str,
    summary: str,
    *,
    operator: LocalUser | None = None,
    scope_type: str = "system",
    scope_id: int | None = None,
    object_type: str | None = None,
    object_id: int | None = None,
    status: str | None = None,
    detail_json: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        tenant_id=tenant_id,
        action_type=action_type,
        scope_type=scope_type,
        scope_id=scope_id,
        object_type=object_type,
        object_id=object_id,
        operator_user_id=operator.id if operator and operator.id is not None else None,
        operator_username=operator.username if operator else None,
        operator_name=operator.display_name if operator else "系统",
        status=status,
        summary=summary,
        detail_json=detail_json or {},
    )
    session.add(log)
    return log


def serialize_audit_logs(session: Session, tenant_id: int, logs: list[AuditLog]) -> list[AuditLogRead]:
    user_map = get_local_user_map(session, tenant_id, [log.operator_user_id for log in logs])
    return [
        AuditLogRead(
            id=log.id,
            tenant_id=log.tenant_id,
            action_type=log.action_type,
            scope_type=log.scope_type,
            scope_id=log.scope_id,
            object_type=log.object_type,
            object_id=log.object_id,
            operator_user_id=log.operator_user_id,
            operator_username=log.operator_username,
            operator_name=log.operator_name,
            operator_user=local_user_summary(user_map.get(log.operator_user_id)) if log.operator_user_id else None,
            status=log.status,
            summary=log.summary,
            detail_json=log.detail_json or {},
            created_at=log.created_at,
        )
        for log in logs
    ]
