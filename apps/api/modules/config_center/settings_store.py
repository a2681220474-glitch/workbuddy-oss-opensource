from __future__ import annotations

from sqlmodel import Session, select

from apps.api.core.config import get_settings
from apps.api.models import RuntimeSetting, utc_now


DEFAULT_SEND_MODE_KEY = "default_send_mode"
VALID_DEFAULT_SEND_MODES = {"mock", "real"}


def get_default_send_mode(session: Session, tenant_id: int) -> str:
    setting = session.exec(
        select(RuntimeSetting).where(
            RuntimeSetting.tenant_id == tenant_id,
            RuntimeSetting.key == DEFAULT_SEND_MODE_KEY,
        )
    ).first()
    if setting and setting.value in VALID_DEFAULT_SEND_MODES:
        return setting.value
    return "real" if get_settings().enable_external_send else "mock"


def set_default_send_mode(session: Session, tenant_id: int, mode: str) -> RuntimeSetting:
    if mode not in VALID_DEFAULT_SEND_MODES:
        raise ValueError("default_send_mode must be mock or real")
    setting = session.exec(
        select(RuntimeSetting).where(
            RuntimeSetting.tenant_id == tenant_id,
            RuntimeSetting.key == DEFAULT_SEND_MODE_KEY,
        )
    ).first()
    if setting is None:
        setting = RuntimeSetting(tenant_id=tenant_id, key=DEFAULT_SEND_MODE_KEY, value=mode)
    else:
        setting.value = mode
        setting.updated_at = utc_now()
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting
