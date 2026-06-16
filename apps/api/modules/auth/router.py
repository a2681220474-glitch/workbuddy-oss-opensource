from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import LocalUser, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.auth.service import (
    active_password_user_count,
    clear_session_cookie,
    hash_password,
    set_session_cookie,
    validate_password_strength,
    verify_password,
)
from apps.api.schemas import (
    AuthBootstrapRequest,
    AuthBootstrapStatusRead,
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthSessionRead,
    LocalUserRead,
)


router = APIRouter()


@router.get("/bootstrap-status", response_model=AuthBootstrapStatusRead)
def bootstrap_status(session: SessionDep, tenant: TenantDep) -> AuthBootstrapStatusRead:
    users = list(
        session.exec(
            select(LocalUser)
            .where(LocalUser.tenant_id == tenant.id, LocalUser.status == "active")
            .order_by(LocalUser.id.asc())
        ).all()
    )
    return AuthBootstrapStatusRead(
        needs_bootstrap=active_password_user_count(users) == 0,
        password_user_count=active_password_user_count(users),
        active_user_count=len(users),
        bootstrap_username="local_admin",
    )


@router.post("/bootstrap", response_model=AuthSessionRead)
def bootstrap_auth(
    payload: AuthBootstrapRequest,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
) -> AuthSessionRead:
    users = list(
        session.exec(
            select(LocalUser)
            .where(LocalUser.tenant_id == tenant.id, LocalUser.status == "active")
            .order_by(LocalUser.id.asc())
        ).all()
    )
    if active_password_user_count(users) > 0:
        raise HTTPException(status_code=400, detail="Local auth bootstrap is already completed.")
    username = payload.username.strip() or "local_admin"
    user = next((item for item in users if item.username == username), None)
    if user is None:
        user = LocalUser(
            tenant_id=tenant.id,
            username=username,
            display_name=(payload.display_name or username).strip() or username,
            password_hash=hash_password(payload.password),
            role="admin",
            status="active",
            updated_at=utc_now(),
        )
        session.add(user)
    else:
        user.display_name = (payload.display_name or user.display_name or username).strip() or username
        user.password_hash = hash_password(payload.password)
        user.updated_at = utc_now()
        session.add(user)
    session.flush()
    append_audit_log(
        session,
        tenant.id,
        "local_auth_bootstrapped",
        f"初始化本地登录管理员 @{user.username}",
        scope_type="auth",
        scope_id=user.id,
        object_type="local_user",
        object_id=user.id,
        status="active",
        detail_json={"username": user.username, "role": user.role},
    )
    session.commit()
    session.refresh(user)
    set_session_cookie(response, tenant, user)
    return AuthSessionRead(status="authenticated", user=LocalUserRead.model_validate(user))


@router.post("/login", response_model=AuthSessionRead)
def login(
    payload: AuthLoginRequest,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
) -> AuthSessionRead:
    username = payload.username.strip()
    user = session.exec(
        select(LocalUser).where(
            LocalUser.tenant_id == tenant.id,
            LocalUser.username == username,
            LocalUser.status == "active",
        )
    ).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    append_audit_log(
        session,
        tenant.id,
        "local_user_login",
        f"{user.display_name} 登录系统",
        operator=user,
        scope_type="auth",
        scope_id=user.id,
        object_type="local_user",
        object_id=user.id,
        status="authenticated",
    )
    session.commit()
    set_session_cookie(response, tenant, user)
    return AuthSessionRead(status="authenticated", user=LocalUserRead.model_validate(user))


@router.post("/logout")
def logout(response: Response, current_user: CurrentUserDep, session: SessionDep, tenant: TenantDep) -> dict[str, str]:
    append_audit_log(
        session,
        tenant.id,
        "local_user_logout",
        f"{current_user.display_name} 退出系统",
        operator=current_user,
        scope_type="auth",
        scope_id=current_user.id,
        object_type="local_user",
        object_id=current_user.id,
        status="logged_out",
    )
    session.commit()
    clear_session_cookie(response)
    return {"status": "logged_out"}


@router.post("/change-password")
def change_password(
    payload: AuthChangePasswordRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    current_user.password_hash = hash_password(validate_password_strength(payload.new_password))
    current_user.updated_at = utc_now()
    session.add(current_user)
    append_audit_log(
        session,
        tenant.id,
        "local_user_password_changed",
        f"{current_user.display_name} 修改登录密码",
        operator=current_user,
        scope_type="auth",
        scope_id=current_user.id,
        object_type="local_user",
        object_id=current_user.id,
        status="updated",
    )
    session.commit()
    return {"status": "password_updated"}


@router.get("/me", response_model=LocalUserRead)
def current_user(user: CurrentUserDep) -> LocalUserRead:
    return LocalUserRead.model_validate(user)
