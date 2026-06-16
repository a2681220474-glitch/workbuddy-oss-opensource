from __future__ import annotations

from datetime import datetime, timezone

from apps.api.core.config import get_settings
from apps.api.models import BEIJING_TZ


def as_beijing(value: datetime, database_url: str | None = None) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(BEIJING_TZ)
    runtime_database_url = database_url if database_url is not None else get_settings().database_url
    if runtime_database_url.startswith("postgresql"):
        return value.replace(tzinfo=timezone.utc).astimezone(BEIJING_TZ)
    return value.replace(tzinfo=BEIJING_TZ)


def beijing_iso(value: datetime) -> str:
    return as_beijing(value).isoformat()
