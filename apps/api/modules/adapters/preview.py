from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from apps.api.core.config import get_settings
from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, MessageEvent
from apps.api.modules.adapters.feishu import FeishuAdapterError, feishu_message_to_import_record, get_feishu_event_type
from apps.api.modules.adapters.wecom import wecom_payload_to_import_record
from apps.api.modules.display import enrich_approval, enrich_message, related_objects_for_message
from apps.api.modules.imports.parsers import record_from_mapping
from apps.api.modules.imports.service import import_records


router = APIRouter()


class AdapterPreviewRequest(BaseModel):
    channel: str = Field(pattern="^(feishu|wecom|dingtalk)$")
    payload: dict[str, Any]


@router.post("/preview")
def preview_adapter_payload(payload: AdapterPreviewRequest) -> dict[str, Any]:
    try:
        record = normalize_preview(payload.channel, payload.payload)
    except FeishuAdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - preview should explain malformed payloads.
        raise HTTPException(status_code=400, detail=f"Payload cannot be normalized: {exc}") from exc

    return {
        "channel": payload.channel,
        "channel_label": channel_label(payload.channel),
        "supported": True,
        "mode": "real_parser" if payload.channel == "feishu" else "local_payload_parser",
        "event_type": detect_event_type(payload.channel, payload.payload),
        "message_event_preview": {
            "channel": record.channel,
            "text": record.text,
            "sender_name": record.sender_name,
            "sender_external_id": record.sender_external_id,
            "conversation_id": record.conversation_id,
            "conversation_name": record.conversation_name,
            "conversation_type": record.conversation_type,
            "message_type": record.message_type,
            "external_message_id": record.external_message_id,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "raw_payload": record.raw_payload,
        },
        "notes": preview_notes(payload.channel),
    }


@router.post("/import")
def import_adapter_payload(
    payload: AdapterPreviewRequest,
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    try:
        record = normalize_preview(payload.channel, payload.payload)
    except FeishuAdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - import should explain malformed payloads.
        raise HTTPException(status_code=400, detail=f"Payload cannot be normalized: {exc}") from exc

    batch, messages = import_records(
        session=session,
        tenant=tenant,
        records=[record],
        source=f"{payload.channel}_adapter_test",
        filename=f"{payload.channel}_adapter_preview.json",
    )
    traces = [build_import_trace(session, message) for message in messages]
    return {
        "status": "imported" if messages else "skipped",
        "batch": {
            "id": batch.id,
            "source": batch.source,
            "status": batch.status,
            "imported_count": batch.imported_count,
            "skipped_count": batch.skipped_count,
            "error_count": batch.error_count,
        },
        "messages": [enrich_message(session, message).model_dump(mode="json") for message in messages],
        "traces": traces,
        "notes": [
            "已走现有 import_records -> MessageEvent -> Agent Router -> Approval 流水线。",
            "真实外发仍需人工审批，不会因为导入测试台 payload 直接发送。",
        ],
    }


def normalize_preview(channel: str, payload: dict[str, Any]):
    if channel == "feishu":
        return feishu_message_to_import_record(payload)
    if channel == "wecom":
        return wecom_payload_to_import_record(payload)
    return record_from_mapping(
        {
            "channel": channel,
            "text": payload.get("text") or payload.get("content") or payload.get("message") or "",
            "sender_name": payload.get("sender_name") or payload.get("sender") or f"{channel}_demo_user",
            "sender_external_id": payload.get("sender_external_id") or payload.get("user_id") or payload.get("open_id"),
            "conversation_id": payload.get("conversation_id") or payload.get("chat_id") or f"{channel}_demo_chat",
            "conversation_name": payload.get("conversation_name") or payload.get("chat_name") or f"{channel} 测试会话",
            "conversation_type": payload.get("conversation_type") or payload.get("chat_type") or "group",
            "message_type": payload.get("message_type") or "text",
            "external_message_id": payload.get("external_message_id") or payload.get("message_id"),
            "timestamp": payload.get("timestamp") or payload.get("create_time"),
        },
        default_channel=channel,
    )


def detect_event_type(channel: str, payload: dict[str, Any]) -> str:
    if channel == "feishu":
        return get_feishu_event_type(payload) or "unknown"
    return str(payload.get("event_type") or payload.get("type") or "mock.message.receive")


def build_import_trace(session, message: MessageEvent) -> dict[str, Any]:
    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.message_id == message.id,
            AgentRun.agent_type.notin_(["feishu_send_adapter", "feishu_stream_worker"]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    approvals = session.exec(select(Approval).where(Approval.agent_run_id == run.id)).all() if run else []
    related_objects = related_objects_for_message(session, message)
    return {
        "message_id": message.id,
        "agent_run_id": run.id if run else None,
        "agent_type": run.agent_type if run else None,
        "approval_ids": [approval.id for approval in approvals if approval.id is not None],
        "approvals": [enrich_approval(session, approval).model_dump(mode="json") for approval in approvals],
        "related_objects": [item.model_dump(mode="json") for item in related_objects],
    }


def preview_notes(channel: str) -> list[str]:
    if channel == "feishu":
        settings = get_settings()
        return [
            "使用现有飞书明文事件解析器预览。",
            "这里只预览标准化结果，不写入 MessageEvent，也不会触发 Agent。",
            "当前 API 进程飞书配置：" + ("已配置" if settings.feishu_configured else "未配置"),
        ]
    if channel == "wecom":
        return [
            "支持企业微信 JSON 调试 payload 和真实 XML/加密回调字段的标准化预览。",
            "这里只预览标准化结果，不写入 MessageEvent，也不会触发 Agent。",
            "真实回调验签、解密和外发请到企微诊断页联调。",
        ]
    return [
        "当前已提供本地 payload parser 和 webhook 导入入口，可先用测试账号 payload 联调。",
        "真实平台验签/解密、通讯录解析和真实外发需要在账号联调时继续补齐。",
    ]


def channel_label(channel: str) -> str:
    labels = {"feishu": "飞书", "wecom": "企业微信", "dingtalk": "钉钉"}
    return labels.get(channel, channel)
