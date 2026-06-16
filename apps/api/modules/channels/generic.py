from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter

from apps.api.core.config import get_settings
from apps.api.dependencies import SessionDep, TenantDep
from apps.api.modules.adapters.preview import normalize_preview
from apps.api.modules.imports.service import import_records


router = APIRouter()


@router.get("/{channel}/status")
def channel_status(channel: Literal["dingtalk"]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "channel": channel,
        "label": "钉钉",
        "configured": settings.dingtalk_configured,
        "real_im_adapters_enabled": settings.enable_real_im_adapters,
        "external_send_enabled": settings.enable_external_send,
        "webhook_path": f"/api/channels/{channel}/webhook",
        "mode": "ready_for_real_payload_test" if settings.dingtalk_configured else "waiting_for_credentials",
        "notes": [
            "当前已提供配置入口、payload 标准化入口和导入流水线。",
            "真实平台验签/解密和真实外发仍需要按平台账号补齐后继续验证。",
        ],
    }


@router.post("/{channel}/webhook")
def channel_webhook(
    channel: Literal["dingtalk"],
    payload: dict[str, Any],
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    record = normalize_preview(channel, payload)
    batch, messages = import_records(
        session=session,
        tenant=tenant,
        records=[record],
        source=f"{channel}_webhook",
        filename=f"{channel}_webhook.json",
    )
    return {
        "status": "imported" if messages else "skipped",
        "channel": channel,
        "batch": {
            "id": batch.id,
            "status": batch.status,
            "imported_count": batch.imported_count,
            "skipped_count": batch.skipped_count,
            "error_count": batch.error_count,
        },
        "message_ids": [message.id for message in messages],
        "notes": [
            "Webhook payload 已进入 MessageEvent -> Agent Router -> 业务对象/审批流水线。",
            "平台级验签、回调 challenge 和加密消息解密会在真实账号联调时补齐。",
        ],
    }
