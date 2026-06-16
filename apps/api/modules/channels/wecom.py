from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import or_
from sqlmodel import select

from apps.api.core.config import get_settings
from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, Channel, ChannelEvent, Conversation, FollowupTask, Lead, MessageEvent, Ticket
from apps.api.modules.adapters.wecom import (
    WeComAdapterError,
    WeComClient,
    parse_wecom_webhook,
    verify_wecom_callback_url,
    wecom_message_type_label,
    wecom_payload_to_import_record,
)
from apps.api.modules.channels.service import record_channel_event
from apps.api.modules.channels.acceptance import (
    build_connector_acceptance_report,
    require_real_send_authorization,
)
from apps.api.modules.display import enrich_message, related_objects_for_message
from apps.api.modules.imports.service import import_records


router = APIRouter()


@router.get("/status")
def wecom_status(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    settings = get_settings()
    recent = recent_wecom_activity(session, tenant.id)
    return {
        "channel": "wecom",
        "configured": settings.wecom_configured,
        "real_im_adapters_enabled": settings.enable_real_im_adapters,
        "external_send_enabled": settings.enable_external_send,
        "webhook_path": "/api/channels/wecom/webhook",
        "callback_mode": "encrypted" if settings.wecom_encoding_aes_key else "plain_or_compat",
        "send_mode": "real" if settings.enable_external_send else "mock",
        "recent": recent,
        "production_readiness": wecom_production_readiness(settings, recent),
    }


@router.get("/diagnostics/full")
def wecom_diagnostics_full(session: SessionDep, tenant: TenantDep, check_token: bool = False) -> dict[str, Any]:
    diagnostics = build_wecom_diagnostics(check_token=check_token)
    recent = recent_wecom_activity(session, tenant.id)
    summary = wecom_acceptance_summary(session, tenant.id)
    readiness = wecom_production_readiness(get_settings(), recent)
    diagnostics.update(
        {
            "recent": recent,
            "recent_channel_events": recent_wecom_channel_events(session, tenant.id),
            "recent_agent_runs": recent_wecom_agent_runs(session, tenant.id),
            "business_trace": wecom_business_trace(session, tenant.id),
            "acceptance_traces": recent_wecom_acceptance_traces(session, tenant.id),
            "acceptance_summary": summary,
            "production_readiness": readiness,
            "safe_acceptance": build_connector_acceptance_report(
                session,
                tenant.id,
                "wecom",
                production_readiness=readiness,
                recent=recent,
                acceptance_summary=summary,
            ),
        }
    )
    return diagnostics


def build_wecom_diagnostics(check_token: bool = False) -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {
        "configured": settings.wecom_configured,
        "external_send_enabled": settings.enable_external_send,
        "send_mode": "real" if settings.enable_external_send else "mock",
        "webhook_path": "/api/channels/wecom/webhook",
        "callback_mode": "encrypted" if settings.wecom_encoding_aes_key else "plain_or_compat",
        "checks": {
            "corp_id": "ok" if settings.wecom_corp_id else "missing",
            "agent_id": "ok" if settings.wecom_agent_id else "missing",
            "secret": "ok" if settings.wecom_secret else "missing",
            "token": "ok" if settings.wecom_token else "missing",
            "encoding_aes_key": "ok" if settings.wecom_encoding_aes_key else "missing",
        },
        "token": {"checked": False},
        "callback_requirements": [
            "在企业微信后台把接收消息 URL 指向 /api/channels/wecom/webhook",
            "回调模式建议使用安全模式，并在配置中心填写 Token 和 EncodingAESKey",
            "ENABLE_REAL_IM_ADAPTERS=true 后再做真实消息验收",
            "企微后台保存 URL 后，浏览器打开 /api/channels/wecom/webhook?msg_signature=...&timestamp=...&nonce=...&echostr=... 应返回解密后的 echostr",
        ],
        "send_requirements": [
            "ENABLE_EXTERNAL_SEND=true",
            "WECOM_CORP_ID / WECOM_AGENT_ID / WECOM_SECRET 已配置",
            "审批通过后，当前只对应用会话单聊或 ChatId 群聊做真实文本发送",
            "企业微信应用可见范围需要覆盖测试用户，且应用有发送消息权限",
        ],
        "production_notes": [
            "v0.17.x 已把企微从 mock 骨架推进到真实回调、验签解密、消息入库、审批外发、诊断与验收脚本。",
            "企微接收现在支持 XML 回调和加密回调，仍保留 JSON payload 入口方便本地调试。",
            "所有接收、发送、审批动作都会进入 ChannelEvent / AgentRun / Audit 流水线。",
            "企微真实发送默认仍受审批和全局发送策略约束。",
        ],
    }
    if check_token:
        result["token"]["checked"] = True
        try:
            token = WeComClient(settings).get_access_token()
            result["token"].update({"status": "ok", "masked": mask_secret(token)})
        except WeComAdapterError as exc:
            result["token"].update({"status": "failed", "error": str(exc), "code": exc.code, "advice": exc.advice})
    return result


def wecom_production_readiness(settings, recent: dict[str, Any]) -> dict[str, Any]:
    checks = [
        readiness_check(
            "credentials",
            "企微凭证",
            bool(settings.wecom_corp_id and settings.wecom_agent_id and settings.wecom_secret),
            "Corp ID / Agent ID / Secret 已配置",
            "请在配置中心填写 Corp ID、Agent ID 和 Secret。",
        ),
        readiness_check(
            "callback_signature",
            "回调验签参数",
            bool(settings.wecom_token),
            "Token 已配置",
            "正式回调至少需要 Token 才能验签。",
        ),
        readiness_check(
            "callback_encryption",
            "回调解密参数",
            bool(settings.wecom_encoding_aes_key),
            "EncodingAESKey 已配置，支持安全模式回调",
            "建议补齐 EncodingAESKey，正式环境优先使用安全模式。",
            severity="warning",
        ),
        readiness_check(
            "real_adapter",
            "真实接收开关",
            bool(settings.enable_real_im_adapters),
            "ENABLE_REAL_IM_ADAPTERS=true",
            "请在配置中心或环境变量启用真实 IM Adapter。",
        ),
        readiness_check(
            "recent_message",
            "最近真实消息",
            bool(recent.get("last_message")),
            "已收到企微消息",
            "请从企业微信测试会话给应用发一条消息，并确认消息进入 WorkBuddy。",
        ),
        readiness_check(
            "external_send_policy",
            "外发策略",
            bool(settings.enable_external_send),
            "真实外发开关已开启，审批后可真实发送",
            "当前仍是模拟发送；正式企微验收前需要 ENABLE_EXTERNAL_SEND=true。",
            severity="warning",
        ),
    ]
    blocking_failed = [item for item in checks if not item["ok"] and item.get("severity") == "error"]
    warning_failed = [item for item in checks if not item["ok"] and item.get("severity") == "warning"]
    return {
        "ready": not blocking_failed and not warning_failed,
        "receive_ready": all(item["ok"] for item in checks if item["key"] in {"credentials", "callback_signature", "real_adapter", "recent_message"}),
        "send_ready": bool(settings.enable_external_send and settings.wecom_configured),
        "blocking_failed": len(blocking_failed),
        "warning_failed": len(warning_failed),
        "checks": checks,
        "acceptance_steps": [
            "在配置中心保存企微 Corp ID / Agent ID / Secret / Token / EncodingAESKey。",
            "运行 npm run check:wecom-runtime 检查企微运行参数。",
            "在企业微信后台保存消息接收 URL，确认 GET 校验通过。",
            "从企业微信测试会话发一条消息，确认最近消息、渠道事件、业务链路更新。",
            "进入审批队列确认上下文，审批通过后先看发送预览，再做真实发送验收。",
            "运行 npm run check:wecom-acceptance，确认至少有一条企微链路达到 ready 或 complete。",
        ],
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


@router.get("/webhook")
def wecom_webhook_verify(
    msg_signature: str | None = None,
    timestamp: str | None = None,
    nonce: str | None = None,
    echostr: str | None = None,
) -> PlainTextResponse:
    challenge = verify_wecom_callback_url(
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
        settings=get_settings(),
    )
    return PlainTextResponse(challenge)


@router.post("/webhook")
async def wecom_webhook(request: Request, session: SessionDep, tenant: TenantDep):
    settings = get_settings()
    content_type = request.headers.get("content-type", "").lower()
    body = await request.body()
    query = {key: value for key, value in request.query_params.items()}

    if "application/json" in content_type or body.lstrip().startswith(b"{"):
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"WeCom debug JSON is invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="WeCom debug payload must be a JSON object.")
        record = wecom_payload_to_import_record(payload)
        event = record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="wecom",
            event_type="wecom.json.debug",
            payload={
                "event_id": f"wecom.json.debug:{record.external_message_id}",
                "raw_payload": payload,
                "conversation_id": record.conversation_id,
                "sender_id": record.sender_external_id,
                "message_id": record.external_message_id,
            },
        )
        batch, messages = import_records(
            session=session,
            tenant=tenant,
            records=[record],
            source="wecom_webhook_debug",
            filename="wecom-webhook-debug.json",
        )
        return JSONResponse(
            {
                "status": "ok",
                "source": "wecom",
                "mode": "json_debug",
                "channel_event_id": event.id,
                "batch_id": batch.id,
                "message_ids": [message.id for message in messages],
            }
        )

    try:
        result = parse_wecom_webhook(body, query, settings)
    except WeComAdapterError as exc:
        record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="wecom",
            event_type="wecom.webhook.parse.failed",
            status="failed",
            payload={
                "event_id": failed_wecom_event_id(body, str(exc)),
                "error": str(exc),
                "advice": exc.advice,
                "query": query,
                "raw_xml": body.decode("utf-8", errors="ignore"),
            },
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "advice": exc.advice}) from exc

    if result.kind == "channel_event":
        record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="wecom",
            event_type=result.event_type or "wecom.event.unknown",
            payload=result.raw_payload or {"query": query},
        )
        return PlainTextResponse("success")

    if result.kind == "message" and result.record is not None:
        record_channel_event(
            session=session,
            tenant=tenant,
            channel_type="wecom",
            event_type=result.event_type or "wecom.message.receive",
            payload={
                **(result.raw_payload or {}),
                "conversation_id": result.record.conversation_id,
                "sender_id": result.record.sender_external_id,
                "message_id": result.record.external_message_id,
            },
        )
        import_records(
            session=session,
            tenant=tenant,
            records=[result.record],
            source="wecom_webhook",
            filename="wecom-webhook.xml",
        )
        return PlainTextResponse("success")

    return PlainTextResponse("success")


@router.post("/mock-send")
def wecom_mock_send(payload: dict[str, Any], session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    target_type = str(payload.get("target_type") or "user")
    target_id = str(payload.get("target_id") or "wecom-demo-user")
    text = str(payload.get("text") or "WorkBuddy OSS 企微模拟发送测试")
    result = {
        "sent": False,
        "mode": "mock",
        "target_type": target_type,
        "target_id": target_id,
        "text": text,
        "reason": "This diagnostics endpoint records a mock send only. Use /test-send with confirm_real_send=true for a real WeCom send.",
    }
    record_test_send_run(
        session,
        tenant.id,
        status="success",
        output={"channel": "wecom", "mode": "mock", "target_type": target_type, "target_id": target_id, "result": result},
    )
    return result


@router.post("/test-send")
def wecom_test_send(payload: dict[str, Any], session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    settings = get_settings()
    try:
        require_real_send_authorization(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not settings.enable_external_send:
        raise HTTPException(status_code=400, detail="ENABLE_EXTERNAL_SEND=false, real WeCom send is disabled.")
    target_type = str(payload.get("target_type") or "")
    target_id = str(payload.get("target_id") or "")
    text = str(payload.get("text") or "")
    if target_type not in {"user", "chat"}:
        raise HTTPException(status_code=400, detail="target_type must be user or chat.")
    if not target_id or not text:
        raise HTTPException(status_code=400, detail="target_id and text are required.")

    request_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"workbuddy:wecom:{tenant.id}:{target_type}:{target_id}:{text}"))
    started = time.perf_counter()
    try:
        client = WeComClient(settings)
        result = client.send_text_to_chat(target_id, text, request_uuid=request_uuid) if target_type == "chat" else client.send_text_to_user(target_id, text, request_uuid=request_uuid)
    except WeComAdapterError as exc:
        record_test_send_run(
            session,
            tenant.id,
            status="failed",
            output={
                "channel": "wecom",
                "mode": "real",
                "target_type": target_type,
                "target_id": target_id,
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
        "channel": "wecom",
        "mode": "real",
        "target_type": target_type,
        "target_id": target_id,
        "request_uuid": request_uuid,
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
        agent_type="wecom_send_adapter",
        status=status,
        prompt_version="v0.17-wecom-diagnostics-v1",
        prompt_json={"source": "wecom_diagnostics_page"},
        model_provider="local",
        model_name="delivery-diagnostics",
        model_output_json=output,
        action_json={
            "action_type": "diagnostics_send_test",
            "delivery_channel": "wecom",
            "delivery_mode": output.get("mode"),
            "target_type": output.get("target_type"),
            "target_id": output.get("target_id"),
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


def recent_wecom_activity(session, tenant_id: int) -> dict[str, Any]:
    event = session.exec(
        select(ChannelEvent)
        .where(ChannelEvent.tenant_id == tenant_id, ChannelEvent.channel_type == "wecom")
        .order_by(ChannelEvent.created_at.desc(), ChannelEvent.id.desc())
    ).first()
    channel_ids = [
        channel.id
        for channel in session.exec(select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "wecom")).all()
        if channel.id is not None
    ]
    message = latest_wecom_message(session, tenant_id, channel_ids)
    send_run = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.agent_type == "wecom_send_adapter")
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    return {
        "last_event": serialize_channel_event(event),
        "last_message": serialize_message(message),
        "last_send": serialize_send_run(send_run),
    }


def latest_wecom_message(session, tenant_id: int, channel_ids: list[int] | None = None) -> MessageEvent | None:
    ids = channel_ids
    if ids is None:
        ids = [
            channel.id
            for channel in session.exec(select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "wecom")).all()
            if channel.id is not None
        ]
    if not ids:
        return None
    return session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(ids))
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
    ).first()


def recent_wecom_messages(session, tenant_id: int, limit: int = 12) -> list[MessageEvent]:
    channel_ids = [
        channel.id
        for channel in session.exec(select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "wecom")).all()
        if channel.id is not None
    ]
    if not channel_ids:
        return []
    return session.exec(
        select(MessageEvent)
        .where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(channel_ids))
        .order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
        .limit(limit)
    ).all()


def recent_wecom_channel_events(session, tenant_id: int, limit: int = 10) -> list[dict[str, Any]]:
    events = session.exec(
        select(ChannelEvent)
        .where(ChannelEvent.tenant_id == tenant_id, ChannelEvent.channel_type == "wecom")
        .order_by(ChannelEvent.created_at.desc(), ChannelEvent.id.desc())
        .limit(limit)
    ).all()
    return [serialize_channel_event(event) for event in events if event is not None]


def recent_wecom_agent_runs(session, tenant_id: int, limit: int = 10) -> list[dict[str, Any]]:
    channel_ids = [
        channel.id
        for channel in session.exec(select(Channel).where(Channel.tenant_id == tenant_id, Channel.type == "wecom")).all()
        if channel.id is not None
    ]
    message_ids: list[int] = []
    if channel_ids:
        message_ids = [
            message_id
            for message_id in session.exec(
                select(MessageEvent.id).where(MessageEvent.tenant_id == tenant_id, MessageEvent.channel_id.in_(channel_ids))
            ).all()
            if message_id is not None
        ]
    conditions = [AgentRun.agent_type == "wecom_send_adapter"]
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


def wecom_business_trace(session, tenant_id: int) -> dict[str, Any]:
    message = latest_wecom_message(session, tenant_id)
    if message is None:
        return {"message": None, "conversation": None, "agent_run": None, "business_objects": [], "approvals": [], "send_run": None}
    conversation = session.get(Conversation, message.conversation_id)
    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.message_id == message.id,
            AgentRun.agent_type.notin_(["wecom_send_adapter"]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    approvals = session.exec(
        select(Approval)
        .where(Approval.tenant_id == tenant_id, Approval.agent_run_id == (run.id if run else None))
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    ).all() if run and run.id is not None else []
    send_run = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.agent_type == "wecom_send_adapter")
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).first()
    return {
        "message": serialize_message(message),
        "conversation": serialize_conversation_policy(conversation),
        "agent_run": serialize_agent_run(session, run) if run else None,
        "business_objects": [
            {"type": item.type, "id": item.id, "label": item.label, "target": object_target(item.type)}
            for item in related_objects_for_message(session, message)
        ],
        "approvals": [serialize_approval_link(approval) for approval in approvals],
        "send_run": serialize_agent_run(session, send_run) if send_run else None,
    }


def recent_wecom_acceptance_traces(session, tenant_id: int, limit: int = 12) -> list[dict[str, Any]]:
    traces = [wecom_acceptance_trace_for_message(session, tenant_id, message) for message in recent_wecom_messages(session, tenant_id, limit=limit)]
    return [trace for trace in traces if trace is not None]


def wecom_acceptance_summary(session, tenant_id: int) -> dict[str, Any]:
    traces = recent_wecom_acceptance_traces(session, tenant_id, limit=12)
    complete = sum(1 for trace in traces if trace.get("status") == "complete")
    ready = sum(1 for trace in traces if trace.get("status") in {"complete", "ready"})
    return {
        "total": len(traces),
        "complete": complete,
        "ready": ready,
        "needs_attention": sum(1 for trace in traces if trace.get("status") in {"needs_action", "blocked"}),
    }


def wecom_acceptance_trace_for_message(session, tenant_id: int, message: MessageEvent) -> dict[str, Any]:
    from apps.api.modules.approvals.delivery import delivery_runs_for_approval
    from apps.api.modules.business_objects.router import build_business_object_detail

    enriched_message = enrich_message(session, message)
    conversation = session.get(Conversation, message.conversation_id)
    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.message_id == message.id,
            AgentRun.agent_type.notin_(["wecom_send_adapter"]),
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
    send_runs = [item for item in send_runs if item.agent_type == "wecom_send_adapter"]
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
        next_action = "链路已闭环，可作为 v0.17.x 企微正式验收样本。"
    elif routed and object_created and approval_created and timeline_ready:
        status = "ready"
        next_action = "链路已进入审批与时间线，请在审批队列完成企微发送验收。"
    elif routed and object_created:
        status = "needs_action"
        next_action = "业务对象已生成，但还需要检查审批草稿或发送动作。"
    else:
        status = "blocked"
        next_action = "这条企微消息尚未形成完整链路，请检查回调配置、路由规则或业务动作。"

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
        "channel_type": event.channel_type,
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
        "message_type_label": tracking.get("message_type_label") or wecom_message_type_label(message.message_type),
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
        "target_type": (run.action_json or {}).get("target_type"),
        "target_id": (run.action_json or {}).get("target_id"),
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
        approval = session.exec(select(Approval).where(Approval.tenant_id == run.tenant_id, Approval.agent_run_id == run.id)).first()
        if approval is not None:
            links["approval_id"] = approval.id
        ticket = session.exec(select(Ticket).where(Ticket.tenant_id == run.tenant_id, Ticket.agent_run_id == run.id)).first()
        if ticket is not None:
            links["ticket_id"] = ticket.id
        lead = session.exec(select(Lead).where(Lead.tenant_id == run.tenant_id, Lead.agent_run_id == run.id)).first()
        if lead is not None:
            links["lead_id"] = lead.id
        task = session.exec(select(FollowupTask).where(FollowupTask.tenant_id == run.tenant_id, FollowupTask.agent_run_id == run.id)).first()
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


def failed_wecom_event_id(body: bytes, error: str) -> str:
    raw = json.dumps({"body": body.decode("utf-8", errors="ignore"), "error": error}, ensure_ascii=False, sort_keys=True, default=str)
    return f"wecom.webhook.parse.failed:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"
