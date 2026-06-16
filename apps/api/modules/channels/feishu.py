from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_
from sqlmodel import select

from apps.api.core.config import get_settings
from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, Channel, ChannelEvent, Conversation, FollowupTask, Lead, MessageEvent, Ticket
from apps.api.modules.adapters.feishu import FeishuAdapterError, FeishuClient, decrypt_feishu_callback_payload, parse_feishu_webhook, verify_callback_token
from apps.api.modules.approvals.feishu_cards import handle_approval_card_callback, is_approval_card_callback
from apps.api.modules.channels.acceptance import (
    build_connector_acceptance_report,
    require_real_send_authorization,
)
from apps.api.modules.channels.service import record_channel_event
from apps.api.modules.channels.stream_status import read_feishu_stream_status
from apps.api.modules.display import enrich_message, related_objects_for_message
from apps.api.modules.imports.service import import_records


router = APIRouter()


@router.get("/status")
def feishu_status(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    settings = get_settings()
    recent = recent_feishu_activity(session, tenant.id)
    worker = read_feishu_stream_status()
    return {
        "channel": "feishu",
        "configured": settings.feishu_configured,
        "real_im_adapters_enabled": settings.enable_real_im_adapters,
        "external_send_enabled": settings.enable_external_send,
        "api_base_url": settings.feishu_api_base_url,
        "public_base_url": settings.public_base_url,
        "encrypted_callback_supported": True,
        "webhook_path": "/api/channels/feishu/webhook",
        "card_callback": feishu_card_callback_diagnostics(settings),
        "stream_worker_command": "npm run services:start -- feishu-worker",
        "stream_worker": worker,
        "send_mode": "real" if settings.enable_external_send else "mock",
        "recent": recent,
        "production_readiness": feishu_production_readiness(settings, worker, recent),
    }


@router.get("/stream-status")
def feishu_stream_status() -> dict[str, Any]:
    return read_feishu_stream_status()


@router.get("/diagnostics")
def feishu_diagnostics(check_token: bool = False) -> dict[str, Any]:
    return build_feishu_diagnostics(check_token=check_token)


@router.get("/diagnostics/full")
def feishu_diagnostics_full(session: SessionDep, tenant: TenantDep, check_token: bool = False) -> dict[str, Any]:
    diagnostics = build_feishu_diagnostics(check_token=check_token)
    worker = read_feishu_stream_status()
    recent = recent_feishu_activity(session, tenant.id)
    summary = acceptance_summary(session, tenant.id)
    readiness = feishu_production_readiness(get_settings(), worker, recent)
    diagnostics.update(
        {
            "stream_worker": worker,
            "recent": recent,
            "recent_channel_events": recent_channel_events(session, tenant.id),
            "recent_agent_runs": recent_feishu_agent_runs(session, tenant.id),
            "business_trace": business_trace(session, tenant.id),
            "acceptance_traces": recent_feishu_acceptance_traces(session, tenant.id),
            "acceptance_summary": summary,
            "production_readiness": readiness,
            "safe_acceptance": build_connector_acceptance_report(
                session,
                tenant.id,
                "feishu",
                production_readiness=readiness,
                recent=recent,
                acceptance_summary=summary,
            ),
        }
    )
    return diagnostics


def build_feishu_diagnostics(check_token: bool = False) -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {
        "configured": settings.feishu_configured,
        "external_send_enabled": settings.enable_external_send,
        "send_mode": "real" if settings.enable_external_send else "mock",
        "api_base_url": settings.feishu_api_base_url,
        "public_base_url": settings.public_base_url,
        "webhook_path": "/api/channels/feishu/webhook",
        "card_callback": feishu_card_callback_diagnostics(settings),
        "checks": {
            "app_id": "ok" if settings.feishu_app_id else "missing",
            "app_secret": "ok" if settings.feishu_app_secret else "missing",
            "encrypt_key": "enabled" if settings.feishu_encrypt_key else "not_enabled",
        },
        "token": {"checked": False},
        "send_requirements": [
            "ENABLE_EXTERNAL_SEND=true",
            "FEISHU_APP_ID and FEISHU_APP_SECRET configured in the API process",
            "FEISHU_APPROVAL_CHAT_ID configured before sending internal approval cards",
            "Feishu app has message send permission and the latest version is published",
            "Bot is in the source chat or visible to the test user",
        ],
        "card_callback_requirements": [
            "飞书卡片按钮不会走长连接 worker，必须配置公网 HTTP 回调地址。",
            "在飞书开发者后台把卡片交互/机器人回调地址配置为 WorkBuddy 的 /api/channels/feishu/webhook。",
            "本地测试需使用 HTTPS tunnel 或已部署公网 HTTPS 地址；只启动 localhost 会让飞书提示“目标回调服务当前未在线”。",
            "如启用了回调加密，WorkBuddy 和飞书后台的 Encrypt Key 必须一致。",
        ],
        "receive_requirements": [
            "ENABLE_REAL_IM_ADAPTERS=true",
            "Feishu worker is running and heartbeat is fresh",
            "Feishu app has message receive permission and the latest version is published",
            "If Feishu callback encryption is enabled, FEISHU_ENCRYPT_KEY is configured in WorkBuddy",
        ],
        "production_notes": [
            "v0.15.x has completed the Feishu formal loop: worker observability, receive retry, approval cards, and acceptance traces are in place.",
            "Acceptance traces now verify message -> object -> approval -> send -> timeline coverage, including traceable non-text samples.",
            "Encrypted HTTP callbacks are supported when FEISHU_ENCRYPT_KEY is configured.",
            "Feishu long-connection worker passes the Encrypt Key to the official SDK event dispatcher.",
            "Feishu approval card button callbacks require a public HTTP callback URL; the long-connection worker cannot receive those button clicks.",
            "External replies still require approval and send preflight checks before they can reach Feishu.",
            "Approval cards are internal workflow cards and require a configured approval chat before real send.",
        ],
    }
    if check_token:
        result["token"]["checked"] = True
        try:
            token = FeishuClient(settings).get_tenant_access_token()
            result["token"].update({"status": "ok", "masked": mask_secret(token)})
        except FeishuAdapterError as exc:
            result["token"].update({"status": "failed", "error": str(exc), "code": exc.code, "advice": exc.advice})
    return result


def feishu_production_readiness(settings, worker: dict[str, Any], recent: dict[str, Any]) -> dict[str, Any]:
    checks = [
        readiness_check(
            "credentials",
            "飞书凭证",
            bool(settings.feishu_app_id and settings.feishu_app_secret),
            "已配置 App ID / Secret",
            "请在配置中心填写 App ID 和 App Secret。",
        ),
        readiness_check(
            "real_adapter",
            "真实接收开关",
            bool(settings.enable_real_im_adapters),
            "ENABLE_REAL_IM_ADAPTERS=true",
            "请在配置中心或环境变量启用真实 IM Adapter。",
        ),
        readiness_check(
            "worker",
            "Worker 心跳",
            bool(worker.get("receiving_real_messages")),
            "飞书 worker 在线且心跳新鲜",
            worker.get("health_message") or "请启动 npm run dev:feishu-stream 或 docker compose up feishu-worker。",
        ),
        readiness_check(
            "encryption",
            "回调加密",
            True,
            "已支持加密回调；当前状态：" + ("Encrypt Key 已配置" if settings.feishu_encrypt_key else "未启用加密回调"),
            "加密回调检查失败。",
        ),
        readiness_check(
            "approval_card_callback",
            "卡片按钮回调",
            bool(settings.public_base_url),
            f"飞书卡片按钮回调可配置为 {public_callback_url(settings)}",
            "未配置 WORKBUDDY_PUBLIC_BASE_URL。飞书卡片按钮需要公网 HTTP 回调；否则点击通过/拒绝会提示“目标回调服务当前未在线”。",
            severity="warning",
        ),
        readiness_check(
            "recent_message",
            "最近真实消息",
            bool(recent.get("last_message")),
            "已收到飞书消息",
            "请在飞书测试会话给机器人发送一条消息，并确认消息进入 WorkBuddy。",
        ),
        readiness_check(
            "external_send_policy",
            "外发策略",
            bool(settings.enable_external_send),
            "真实外发开关已开启，审批后可真实发送",
            "当前为模拟发送；正式飞书验收前需要 ENABLE_EXTERNAL_SEND=true。",
            severity="warning",
        ),
    ]
    blocking_failed = [item for item in checks if not item["ok"] and item.get("severity") == "error"]
    warning_failed = [item for item in checks if not item["ok"] and item.get("severity") == "warning"]
    return {
        "ready": not blocking_failed and not warning_failed,
        "receive_ready": all(item["ok"] for item in checks if item["key"] in {"credentials", "real_adapter", "worker", "encryption", "recent_message"}),
        "send_ready": bool(settings.enable_external_send and settings.feishu_configured),
        "blocking_failed": len(blocking_failed),
        "warning_failed": len(warning_failed),
        "checks": checks,
        "acceptance_steps": [
            "在配置中心保存飞书 App ID / Secret；如飞书后台启用了加密回调，同时填写 Encrypt Key。",
            "运行 npm run check:feishu-stream 检查配置。",
            "运行 npm run dev:feishu-stream 或 docker compose up feishu-worker 启动 worker。",
            "从飞书测试会话发送一条消息，确认诊断页最近消息和业务链路更新。",
            "如果要在飞书卡片里点通过/拒绝，请先配置 WORKBUDDY_PUBLIC_BASE_URL，并在飞书后台把卡片交互回调指向 /api/channels/feishu/webhook。",
            "进入审批队列查看上下文，审批通过后先看发送预览，再确认真实发送或模拟发送。",
            "运行 npm run check:feishu-acceptance，确认至少有一条链路达到 ready 或 complete。",
        ],
    }


def public_callback_url(settings, path: str = "/api/channels/feishu/webhook") -> str | None:
    base_url = str(getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    if not base_url:
        return None
    return f"{base_url}{path}"


def feishu_card_callback_diagnostics(settings) -> dict[str, Any]:
    webhook_path = "/api/channels/feishu/webhook"
    callback_url = public_callback_url(settings, webhook_path)
    ready = bool(callback_url)
    return {
        "ready": ready,
        "status": "configured" if ready else "needs_public_callback",
        "webhook_path": webhook_path,
        "public_base_url": settings.public_base_url,
        "callback_url": callback_url,
        "diagnosis": (
            "飞书卡片按钮回调已具备公网 URL 配置；还需要确认飞书后台实际填入同一个地址。"
            if ready
            else "飞书卡片按钮回调未配置公网 URL。长连接 worker 只能接收消息事件，不能接收卡片按钮点击。"
        ),
        "feishu_error_when_offline": "目标回调服务当前未在线",
        "requirements": [
            "公网 HTTPS 地址能访问当前 API 服务",
            "飞书后台卡片交互/机器人回调地址指向 /api/channels/feishu/webhook",
            "如果启用加密回调，FEISHU_ENCRYPT_KEY 与飞书后台一致",
            "API 服务保持运行，且安全组/防火墙允许公网访问 443/HTTPS",
        ],
        "next_steps": (
            [
                f"把飞书后台卡片交互回调地址设置为 {callback_url}",
                "发送一张 WorkBuddy 审批卡片到测试群",
                "点击通过/拒绝，确认 WorkBuddy 审批状态变化并生成 feishu.approval_card.callback 事件",
            ]
            if ready
            else [
                "为本地测试启动 HTTPS tunnel，或使用已部署公网 HTTPS 地址",
                "设置 WORKBUDDY_PUBLIC_BASE_URL=https://你的公网域名",
                "重启 API 后在飞书诊断页复制完整回调地址",
                "把飞书后台卡片交互回调地址设置为该完整地址",
            ]
        ),
    }


def readiness_check(
    key: str,
    label: str,
    ok: bool,
    ok_message: str,
    fail_message: str,
    *,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "ok": ok,
        "status": "ok" if ok else "failed",
        "severity": "ok" if ok else severity,
        "message": ok_message if ok else fail_message,
    }


def recent_feishu_activity(session, tenant_id: int) -> dict[str, Any]:
    event = session.exec(
        select(ChannelEvent)
        .where(ChannelEvent.tenant_id == tenant_id, ChannelEvent.channel_type == "feishu")
        .order_by(ChannelEvent.created_at.desc(), ChannelEvent.id.desc())
    ).first()
    feishu_channel_ids = [
        channel.id
        for channel in session.exec(
            select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "feishu")
        ).all()
        if channel.id is not None
    ]
    message = latest_feishu_message(session, tenant_id, feishu_channel_ids)
    send_run = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.agent_type == "feishu_send_adapter")
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    return {
        "last_event": serialize_channel_event(event),
        "last_message": serialize_message(message),
        "last_send": serialize_send_run(send_run),
    }


def latest_feishu_message(session, tenant_id: int, feishu_channel_ids: list[int] | None = None) -> MessageEvent | None:
    channel_ids = feishu_channel_ids
    if channel_ids is None:
        channel_ids = [
            channel.id
            for channel in session.exec(
                select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "feishu")
            ).all()
            if channel.id is not None
        ]
    if not channel_ids:
        return None
    return session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(channel_ids))
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
    ).first()


def recent_feishu_messages(session, tenant_id: int, limit: int = 12) -> list[MessageEvent]:
    feishu_channel_ids = [
        channel.id
        for channel in session.exec(
            select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "feishu")
        ).all()
        if channel.id is not None
    ]
    if not feishu_channel_ids:
        return []
    return session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(feishu_channel_ids))
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
        .limit(limit)
    ).all()


def recent_channel_events(session, tenant_id: int, limit: int = 10) -> list[dict[str, Any]]:
    events = session.exec(
        select(ChannelEvent)
        .where(ChannelEvent.tenant_id == tenant_id, ChannelEvent.channel_type == "feishu")
        .order_by(ChannelEvent.created_at.desc(), ChannelEvent.id.desc())
        .limit(limit)
    ).all()
    return [serialize_channel_event(event) for event in events if event is not None]


def recent_feishu_agent_runs(session, tenant_id: int, limit: int = 10) -> list[dict[str, Any]]:
    feishu_channel_ids = [
        channel.id
        for channel in session.exec(
            select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "feishu")
        ).all()
        if channel.id is not None
    ]
    message_ids: list[int] = []
    if feishu_channel_ids:
        message_ids = [
            message_id
            for message_id in session.exec(
                select(MessageEvent.id).where(
                    MessageEvent.tenant_id == tenant_id,
                    MessageEvent.channel_id.in_(feishu_channel_ids),
                )
            ).all()
            if message_id is not None
        ]

    conditions = [AgentRun.agent_type.in_(["feishu_stream_worker", "feishu_send_adapter"])]
    if message_ids:
        conditions.append(AgentRun.message_id.in_(message_ids))

    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id)
        .where(or_(*conditions))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
    ).all()
    return [serialize_agent_run(session, run) for run in runs]


def business_trace(session, tenant_id: int) -> dict[str, Any]:
    message = latest_feishu_message(session, tenant_id)
    if message is None:
        return {"message": None, "conversation": None, "agent_run": None, "business_objects": [], "approvals": [], "send_run": None}
    conversation = session.get(Conversation, message.conversation_id)

    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.message_id == message.id,
            AgentRun.agent_type.notin_(["feishu_send_adapter", "feishu_stream_worker"]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    approvals = []
    if run is not None and run.id is not None:
        approvals = [
            serialize_approval_link(approval)
            for approval in session.exec(
                select(Approval)
                .where(Approval.tenant_id == tenant_id, Approval.agent_run_id == run.id)
                .order_by(Approval.created_at.desc(), Approval.id.desc())
            ).all()
        ]
    send_run = None
    delivery_runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.agent_type == "feishu_send_adapter")
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    for approval in approvals:
        approval_id = approval.get("id")
        if approval_id is None:
            continue
        for delivery in delivery_runs:
            if (delivery.action_json or {}).get("approval_id") == approval_id:
                send_run = delivery
                break
        if send_run is not None:
            break

    return {
        "message": serialize_message(message),
        "conversation": serialize_conversation_policy(conversation),
        "agent_run": serialize_agent_run(session, run) if run else None,
        "business_objects": [
            {"type": item.type, "id": item.id, "label": item.label, "target": object_target(item.type)}
            for item in related_objects_for_message(session, message)
        ],
        "approvals": approvals,
        "send_run": serialize_agent_run(session, send_run) if send_run else None,
    }


def recent_feishu_acceptance_traces(session, tenant_id: int, limit: int = 12) -> list[dict[str, Any]]:
    traces = [acceptance_trace_for_message(session, tenant_id, message) for message in recent_feishu_messages(session, tenant_id, limit=limit)]
    return [trace for trace in traces if trace is not None]


def acceptance_summary(session, tenant_id: int) -> dict[str, Any]:
    traces = recent_feishu_acceptance_traces(session, tenant_id, limit=12)
    complete = sum(1 for trace in traces if trace.get("status") == "complete")
    ready = sum(1 for trace in traces if trace.get("status") in {"complete", "ready"})
    return {
        "total": len(traces),
        "complete": complete,
        "ready": ready,
        "needs_attention": sum(1 for trace in traces if trace.get("status") in {"needs_action", "blocked"}),
    }


def acceptance_trace_for_message(session, tenant_id: int, message: MessageEvent) -> dict[str, Any]:
    from apps.api.modules.approvals.delivery import delivery_runs_for_approval
    from apps.api.modules.business_objects.router import build_business_object_detail

    enriched_message = enrich_message(session, message)
    conversation = session.get(Conversation, message.conversation_id)
    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.message_id == message.id,
            AgentRun.agent_type.notin_(["feishu_send_adapter", "feishu_stream_worker", "feishu_approval_card_adapter"]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    related = related_objects_for_message(session, message)
    approvals = session.exec(
        select(Approval)
        .where(Approval.tenant_id == tenant_id, Approval.agent_run_id == (run.id if run else None))
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    ).all() if run and run.id is not None else []

    send_runs: list[AgentRun] = []
    for approval in approvals:
        send_runs.extend(delivery_runs_for_approval(session, approval))
    send_runs = sorted(send_runs, key=lambda item: ((item.created_at.isoformat() if item.created_at else ""), item.id or 0), reverse=True)

    timeline_checks = []
    timeline_ready = False
    for related_object in related[:3]:
        detail = build_business_object_detail(session, tenant_id, related_object.type, int(related_object.id))
        timeline = detail.get("timeline") or []
        timeline_types = [str(item.get("type") or "") for item in timeline]
        has_required = all(required in timeline_types for required in ["message", "agent_run", "business_object"])
        has_approval = (not approvals) or ("approval" in timeline_types)
        timeline_checks.append(
            {
                "object_type": related_object.type,
                "object_id": related_object.id,
                "timeline_count": len(timeline),
                "timeline_types": timeline_types,
                "ok": has_required and has_approval,
            }
        )
        if has_required and has_approval:
            timeline_ready = True

    traced = bool(enriched_message.traceable_non_text or message.message_type == "text")
    routed = run is not None
    object_created = bool(related)
    approval_created = bool(approvals)
    send_completed = bool(any((delivery.status == "success") for delivery in send_runs) or any(approval.status == "sent" for approval in approvals))

    if routed and object_created and approval_created and timeline_ready and send_completed:
        status = "complete"
        next_action = "链路已闭环，可作为 v0.15.x 飞书正式验收样本。"
    elif routed and object_created and approval_created and timeline_ready:
        status = "ready"
        next_action = "链路已进入审批与时间线，请在审批队列完成发送验收。"
    elif routed and object_created:
        status = "needs_action"
        next_action = "业务对象已生成，但还需要检查审批草稿或发送动作。"
    else:
        status = "blocked"
        next_action = "这条飞书消息尚未形成完整链路，请检查 worker、路由规则或业务动作。"

    return {
        "message": serialize_message(message),
        "message_tracking": {
            "message_type": enriched_message.message_type,
            "message_type_label": enriched_message.message_type_label,
            "traceable_non_text": enriched_message.traceable_non_text,
            "summary": enriched_message.non_text_summary,
            "details": enriched_message.message_tracking.get("details") if isinstance(enriched_message.message_tracking, dict) else {},
        },
        "conversation": serialize_conversation_policy(conversation),
        "agent_run": serialize_agent_run(session, run) if run else None,
        "business_objects": [
            {"type": item.type, "id": item.id, "label": item.label, "target": object_target(item.type)}
            for item in related
        ],
        "approvals": [serialize_approval_link(approval) for approval in approvals],
        "send_runs": [serialize_send_run(run_item) for run_item in send_runs[:3]],
        "timeline_checks": timeline_checks,
        "status": status,
        "next_action": next_action,
        "checklist": {
            "message_tracked": traced,
            "routed": routed,
            "business_object_created": object_created,
            "approval_created": approval_created,
            "timeline_ready": timeline_ready,
            "send_completed": send_completed,
        },
    }


def serialize_conversation_policy(conversation: Conversation | None) -> dict[str, Any] | None:
    if conversation is None:
        return None
    return {
        "id": conversation.id,
        "name": conversation.name,
        "type": conversation.type,
        "external_conversation_id": conversation.external_conversation_id,
        "bound_agent": conversation.bound_agent or "auto",
        "send_mode": conversation.send_mode or "inherit",
    }


def serialize_channel_event(event: ChannelEvent | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "id": event.id,
        "event_type": event.event_type,
        "status": event.status,
        "conversation_external_id": event.conversation_external_id,
        "actor_external_id": event.actor_external_id,
        "created_at": event.created_at.isoformat(),
        "raw_json": event.raw_json,
    }


def serialize_message(message: MessageEvent | None) -> dict[str, Any] | None:
    if message is None:
        return None
    tracking = (message.raw_json or {}).get("workbuddy_message_tracking") if isinstance((message.raw_json or {}).get("workbuddy_message_tracking"), dict) else {}
    return {
        "id": message.id,
        "sender_name": message.sender_name,
        "sender_external_id": message.sender_external_id,
        "text": message.text,
        "message_type": message.message_type,
        "message_type_label": tracking.get("message_type_label"),
        "traceable_non_text": tracking.get("traceable_non_text"),
        "received_at": message.received_at.isoformat(),
    }


def serialize_send_run(run: AgentRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "mode": (run.action_json or {}).get("delivery_mode"),
        "channel": (run.action_json or {}).get("delivery_channel"),
        "chat_id": (run.action_json or {}).get("chat_id"),
        "feishu_message_id": (run.action_json or {}).get("feishu_message_id"),
        "error": run.error_message,
        "created_at": run.created_at.isoformat(),
    }


def serialize_agent_run(session, run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "message_id": run.message_id,
        "agent_type": run.agent_type,
        "status": run.status,
        "risk_level": run.risk_level,
        "confidence": run.confidence,
        "error_message": run.error_message,
        "prompt_json": run.prompt_json,
        "model_output_json": run.model_output_json,
        "action_json": run.action_json,
        "links": links_for_run(session, run),
        "created_at": run.created_at.isoformat(),
    }


def links_for_run(session, run: AgentRun) -> dict[str, Any]:
    action_json = run.action_json or {}
    prompt_json = run.prompt_json or {}
    links: dict[str, Any] = {}
    message_id = run.message_id or prompt_json.get("source_message_id") or prompt_json.get("message_id")
    if message_id:
        links["message_id"] = message_id
    approval_id = action_json.get("approval_id") or prompt_json.get("approval_id")
    if approval_id:
        links["approval_id"] = approval_id
    if run.id is not None:
        approval = session.exec(
            select(Approval).where(Approval.tenant_id == run.tenant_id, Approval.agent_run_id == run.id)
        ).first()
        if approval is not None:
            links["approval_id"] = approval.id
        ticket = session.exec(select(Ticket).where(Ticket.tenant_id == run.tenant_id, Ticket.agent_run_id == run.id)).first()
        if ticket is not None:
            links["ticket_id"] = ticket.id
        lead = session.exec(select(Lead).where(Lead.tenant_id == run.tenant_id, Lead.agent_run_id == run.id)).first()
        if lead is not None:
            links["lead_id"] = lead.id
        task = session.exec(
            select(FollowupTask).where(FollowupTask.tenant_id == run.tenant_id, FollowupTask.agent_run_id == run.id)
        ).first()
        if task is not None:
            links["task_id"] = task.id
    return links


def serialize_approval_link(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "status": approval.status,
        "label": f"审批#{approval.id}",
        "created_at": approval.created_at.isoformat(),
    }


def object_target(object_type: str) -> str:
    targets = {
        "lead": "leads",
        "ticket": "tickets",
        "task": "tasks",
    }
    return targets.get(object_type, object_type)


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def failed_webhook_event_id(payload: dict[str, Any], error: str) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event_id = header.get("event_id") or payload.get("event_id")
    if event_id:
        return f"feishu.webhook.parse.failed:{event_id}"
    raw = json.dumps({"payload": payload, "error": error}, ensure_ascii=False, sort_keys=True, default=str)
    return f"feishu.webhook.parse.failed:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


@router.post("/webhook")
def feishu_webhook(
    payload: dict[str, Any],
    session: SessionDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    settings = get_settings()
    callback_payload = payload
    if "encrypt" in payload:
        try:
            callback_payload = decrypt_feishu_callback_payload(payload, settings)
        except FeishuAdapterError:
            callback_payload = payload
    if is_approval_card_callback(callback_payload):
        header = callback_payload.get("header") if isinstance(callback_payload.get("header"), dict) else {}
        verify_callback_token(header.get("token") or callback_payload.get("token"), settings)
        result = handle_approval_card_callback(session, tenant, callback_payload)
        event = record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="feishu",
            event_type="feishu.approval_card.callback",
            status="received",
            payload={
                "event_id": failed_webhook_event_id(callback_payload, f"approval-card:{result.get('approval_id')}"),
                "callback_result": result,
                "raw_payload": payload,
                "normalized_payload": callback_payload,
            },
        )
        callback_response = result.get("callback_response")
        if isinstance(callback_response, dict):
            return callback_response
        return {"msg": "success"}
    try:
        result = parse_feishu_webhook(payload, settings)
    except FeishuAdapterError as exc:
        record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="feishu",
            event_type="feishu.webhook.parse.failed",
            status="failed",
            payload={
                "event_id": failed_webhook_event_id(payload, str(exc)),
                "error": str(exc),
                "advice": exc.advice,
                "encrypted": "encrypt" in payload,
                "raw_payload": payload,
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.kind == "url_verification":
        return {"challenge": result.challenge}

    if result.kind == "ignored":
        return {"status": "ignored", "reason": result.reason}

    if result.kind == "channel_event":
        event = record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="feishu",
            event_type=result.reason or "unknown",
            payload=payload,
        )
        return {"status": "ok", "source": "feishu", "channel_event_id": event.id, "event_type": event.event_type}

    if result.kind == "message" and result.record is not None:
        batch, messages = import_records(
            session=session,
            tenant=tenant,
            records=[result.record],
            source="feishu_webhook",
            filename="feishu-webhook",
        )
        return {
            "status": "ok",
            "source": "feishu",
            "batch_id": batch.id,
            "message_count": len(messages),
            "message_ids": [message.id for message in messages],
        }

    return {"status": "ignored", "reason": "No supported Feishu payload found."}


@router.post("/mock-send")
def feishu_mock_send(payload: dict[str, Any], session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    chat_id = str(payload.get("chat_id") or "")
    text = str(payload.get("text") or "WorkBuddy OSS 飞书模拟发送测试")
    result = {
        "sent": False,
        "mode": "mock",
        "reason": "This diagnostics endpoint never sends to Feishu. Use /test-send with confirm_real_send=true for a real send.",
        "chat_id": chat_id,
        "text": text,
    }
    record_test_send_run(
        session,
        tenant.id,
        status="success",
        output={"channel": "feishu", "mode": "mock", "chat_id": chat_id, "result": result},
    )
    return result


@router.post("/test-send")
def feishu_test_send(payload: dict[str, Any], session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    settings = get_settings()
    chat_id = str(payload.get("chat_id") or "")
    text = str(payload.get("text") or "")
    try:
        require_real_send_authorization(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not settings.enable_external_send:
        raise HTTPException(status_code=400, detail="ENABLE_EXTERNAL_SEND=false, real Feishu send is disabled.")
    if not chat_id or not text:
        raise HTTPException(status_code=400, detail="chat_id and text are required.")

    request_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"workbuddy:diagnostics:{tenant.id}:{chat_id}:{text}"))
    started = time.perf_counter()
    try:
        result = FeishuClient(settings).send_text_to_chat(chat_id=chat_id, text=text, request_uuid=request_uuid)
    except FeishuAdapterError as exc:
        record_test_send_run(
            session,
            tenant.id,
            status="failed",
            output={
                "channel": "feishu",
                "mode": "real",
                "chat_id": chat_id,
                "request_uuid": request_uuid,
                "error": str(exc),
                "code": exc.code,
                "advice": exc.advice,
                "body": exc.body,
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "code": exc.code, "advice": exc.advice}) from exc

    output = {
        "channel": "feishu",
        "mode": "real",
        "chat_id": chat_id,
        "request_uuid": request_uuid,
        "feishu_message_id": extract_feishu_message_id(result),
        "result": result,
    }
    record_test_send_run(
        session,
        tenant.id,
        status="success",
        output=output,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return output


def record_test_send_run(
    session,
    tenant_id: int,
    *,
    status: str,
    output: dict[str, Any],
    latency_ms: int = 0,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        agent_type="feishu_send_adapter",
        status=status,
        prompt_version="phase0.3.2-diagnostics-v1",
        prompt_json={"source": "feishu_diagnostics_page"},
        model_provider="local",
        model_name="delivery-diagnostics",
        model_output_json=output,
        action_json={
            "action_type": "diagnostics_send_test",
            "delivery_channel": output.get("channel"),
            "delivery_mode": output.get("mode"),
            "chat_id": output.get("chat_id"),
            "feishu_message_id": output.get("feishu_message_id"),
            "request_uuid": output.get("request_uuid"),
        },
        confidence=1.0 if status == "success" else 0.0,
        risk_level="medium",
        latency_ms=latency_ms,
        error_message=output.get("error"),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def extract_feishu_message_id(result: dict[str, Any]) -> str | None:
    data = result.get("data") if isinstance(result, dict) else None
    if isinstance(data, dict) and data.get("message_id"):
        return str(data.get("message_id"))
    return None
