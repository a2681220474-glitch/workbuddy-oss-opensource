from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from apps.api.core.config import get_settings
from apps.api.db.session import get_session
from apps.api.models import LocalUser, Tenant
from apps.api.modules.auth.service import read_session_payload


SessionDep = Annotated[Session, Depends(get_session)]


def get_current_tenant(
    session: SessionDep,
    x_tenant_key: Annotated[str | None, Header(alias="X-Tenant-Key")] = None,
) -> Tenant:
    tenant_key = x_tenant_key or get_settings().demo_tenant_key
    tenant = session.exec(select(Tenant).where(Tenant.key == tenant_key)).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_key}")
    return tenant


TenantDep = Annotated[Tenant, Depends(get_current_tenant)]


def get_current_user(
    session: SessionDep,
    tenant: TenantDep,
    request: Request,
    x_workbuddy_user: Annotated[str | None, Header(alias="X-WorkBuddy-User")] = None,
) -> LocalUser:
    statement = select(LocalUser).where(LocalUser.tenant_id == tenant.id, LocalUser.status == "active")
    settings = get_settings()
    workbuddy_session = request.cookies.get(settings.auth_cookie_name)
    if workbuddy_session:
        payload = read_session_payload(workbuddy_session)
        if payload and payload.get("tenant_id") == tenant.id and payload.get("user_id") is not None:
            user = session.get(LocalUser, int(payload["user_id"]))
            if user is not None and user.tenant_id == tenant.id and user.status == "active":
                return user
    if x_workbuddy_user:
        if settings.environment == "local":
            user = session.exec(
                statement.where((LocalUser.username == x_workbuddy_user) | (LocalUser.display_name == x_workbuddy_user))
            ).first()
            if user is not None:
                return user
    raise HTTPException(status_code=401, detail="Authentication required")


CurrentUserDep = Annotated[LocalUser, Depends(get_current_user)]
