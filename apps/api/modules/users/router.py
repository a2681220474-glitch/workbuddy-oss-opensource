from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import LocalUser, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.auth.service import hash_password
from apps.api.schemas import LocalUserCreate, LocalUserRead, LocalUserUpdate


router = APIRouter()


@router.get("", response_model=list[LocalUserRead])
def list_local_users(session: SessionDep, tenant: TenantDep, _: CurrentUserDep) -> list[LocalUser]:
    statement = (
        select(LocalUser)
        .where(LocalUser.tenant_id == tenant.id)
        .order_by(LocalUser.created_at.asc(), LocalUser.id.asc())
    )
    return list(session.exec(statement).all())


@router.post("", response_model=LocalUserRead)
def create_local_user(
    payload: LocalUserCreate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> LocalUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create local users in v0.16.0")
    existing = session.exec(
        select(LocalUser).where(LocalUser.tenant_id == tenant.id, LocalUser.username == payload.username.strip())
    ).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = LocalUser(
        tenant_id=tenant.id,
        username=payload.username.strip(),
        display_name=payload.display_name.strip() or payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        status="active",
        updated_at=utc_now(),
    )
    session.add(user)
    session.flush()
    append_audit_log(
        session,
        tenant.id,
        "local_user_created",
        f"新增团队成员 @{user.username}",
        operator=current_user,
        scope_type="user",
        scope_id=user.id,
        object_type="local_user",
        object_id=user.id,
        status=user.status,
        detail_json={"username": user.username, "role": user.role, "display_name": user.display_name, "password_set": True},
    )
    session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=LocalUserRead)
def update_local_user(
    user_id: int,
    payload: LocalUserUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> LocalUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage local users in v0.16.0")
    user = session.get(LocalUser, user_id)
    if user is None or user.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Local user not found")
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip() or user.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        if user.username == "local_admin" and payload.status != "active":
            raise HTTPException(status_code=400, detail="Default local admin cannot be disabled")
        user.status = payload.status
    if payload.password is not None and payload.password.strip():
        user.password_hash = hash_password(payload.password)
    user.updated_at = utc_now()
    session.add(user)
    append_audit_log(
        session,
        tenant.id,
        "local_user_updated",
        f"更新团队成员 @{user.username}",
        operator=current_user,
        scope_type="user",
        scope_id=user.id,
        object_type="local_user",
        object_id=user.id,
        status=user.status,
        detail_json={"role": user.role, "display_name": user.display_name, "password_updated": bool(payload.password)},
    )
    session.commit()
    session.refresh(user)
    return user
