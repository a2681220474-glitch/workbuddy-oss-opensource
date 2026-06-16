from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AuditLog
from apps.api.modules.audit.service import serialize_audit_logs
from apps.api.schemas import AuditLogRead


router = APIRouter()


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    session: SessionDep,
    tenant: TenantDep,
    action_type: str | None = None,
    scope_type: str | None = None,
    object_type: str | None = None,
    operator_user_id: int | None = None,
    limit: int = 100,
) -> list[AuditLogRead]:
    statement = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    if action_type:
        statement = statement.where(AuditLog.action_type == action_type)
    if scope_type:
        statement = statement.where(AuditLog.scope_type == scope_type)
    if object_type:
        statement = statement.where(AuditLog.object_type == object_type)
    if operator_user_id is not None:
        statement = statement.where(AuditLog.operator_user_id == operator_user_id)
    rows = session.exec(
        statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(max(1, min(limit, 300)))
    ).all()
    return serialize_audit_logs(session, tenant.id, list(rows))
