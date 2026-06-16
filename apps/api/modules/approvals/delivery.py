from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from apps.api.core.config import get_settings
from apps.api.models import BEIJING_TZ, AgentRun, Approval, Conversation, MessageEvent, utc_now
from apps.api.modules.adapters.feishu import FeishuAdapterError, FeishuClient
from apps.api.modules.adapters.wecom import WeComAdapterError, WeComClient
from apps.api.modules.config_center.settings_store import get_default_send_mode


SENDABLE_APPROVAL_STATUSES = {"approved", "edited"}
DELIVERY_AGENT_TYPES = ("feishu_send_adapter", "wecom_send_adapter")
MAX_DELIVERY_ATTEMPTS = 3
DELIVERY_RETRY_BACKOFF_SECONDS = {
    1: 60,
    2: 300,
}


def preview_approval_delivery(session: Session, approval: Approval) -> dict[str, Any]:
    previous_delivery = latest_delivery_run_for_approval(session, approval)
    delivery_attempts = delivery_attempt_count_for_approval(session, approval)
    retry_policy = delivery_retry_policy(previous_delivery, delivery_attempts)
    if approval.status == "sent":
        return {
            "sendable": False,
            "mode": "sent",
            "channel": None,
            "severity": "info",
            "title": "这条审批已经发送成功",
            "message": "系统已记录成功发送结果，不建议重复发送。",
            **retry_policy,
        }
    if approval.status not in SENDABLE_APPROVAL_STATUSES:
        return {
            "sendable": False,
            "mode": "blocked",
            "channel": None,
            "severity": "warning",
            "title": "当前状态不能发送",
            "message": "只有已通过或编辑后通过的审批才能进入发送步骤。",
            **retry_policy,
        }

    original_run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    message = session.get(MessageEvent, original_run.message_id) if original_run and original_run.message_id else None
    if message is None:
        return {
            "sendable": False,
            "mode": "blocked",
            "channel": None,
            "severity": "error",
            "title": "找不到原始消息",
            "message": "无法判断发送渠道和会话策略，请先检查运行日志。",
            **retry_policy,
        }

    content = approval.final_content or approval.draft_content
    if not content:
        return {
            "sendable": False,
            "mode": "blocked",
            "channel": None,
            "severity": "error",
            "title": "没有可发送内容",
            "message": "审批缺少最终内容和 AI 草稿。",
            **retry_policy,
        }

    if not retry_policy.get("retry_allowed", True):
        return {
            "sendable": False,
            "mode": "retry_wait" if retry_policy.get("retry_after_seconds") else "retry_limit",
            "channel": None,
            "severity": "warning",
            "title": retry_policy.get("retry_title") or "暂时不能重试发送",
            "message": retry_policy.get("retry_message") or "请稍后再试。",
            **retry_policy,
        }

    channel = str((message.normalized_json or {}).get("channel") or "local")
    settings = get_settings()
    if channel == "wecom":
        conversation = session.get(Conversation, message.conversation_id)
        conversation_send_mode = (conversation.send_mode if conversation else "inherit") or "inherit"
        default_send_mode = get_default_send_mode(session, message.tenant_id)
        send_mode = default_send_mode if conversation_send_mode == "inherit" else conversation_send_mode
        workbuddy_wecom = (message.raw_json or {}).get("workbuddy_wecom") if isinstance((message.raw_json or {}).get("workbuddy_wecom"), dict) else {}
        target_type = str(workbuddy_wecom.get("delivery_target_type") or ("chat" if (message.normalized_json or {}).get("conversation_type") == "group" else "user"))
        target_id = str(workbuddy_wecom.get("delivery_target_id") or (message.normalized_json or {}).get("conversation_id") or (message.normalized_json or {}).get("sender_id") or "")
        policy = {
            "conversation_send_mode": conversation_send_mode,
            "default_send_mode": default_send_mode,
            "effective_send_mode": send_mode,
            "enable_external_send": settings.enable_external_send,
            "target_type": target_type,
            "target_id": target_id,
        }
        if not target_id:
            return {
                "sendable": False,
                "mode": "blocked",
                "channel": "wecom",
                "severity": "error",
                "title": "缺少企微发送目标",
                "message": "源消息没有可回发的用户或群会话 ID。",
                "policy": policy,
                **retry_policy,
            }
        if send_mode == "disabled":
            return {
                "sendable": False,
                "mode": "disabled",
                "channel": "wecom",
                "severity": "error",
                "title": "会话策略禁止发送",
                "message": "当前会话 send_mode=disabled，发送按钮只会提示，不会触达企业微信。",
                "policy": policy,
                **retry_policy,
            }
        if send_mode == "mock" or not settings.enable_external_send:
            return {
                "sendable": True,
                "mode": "mock",
                "channel": "wecom",
                "severity": "info",
                "title": "即将模拟发送到企业微信",
                "message": "系统会记录发送审计，但不会真正触达企业微信。",
                "policy": policy,
                "content_preview": content,
                **retry_policy,
            }
        return {
            "sendable": True,
            "mode": "real",
            "channel": "wecom",
            "severity": "warning",
            "title": "即将真实发送到企业微信",
            "message": "这次操作会调用企业微信接口并把内容发到原始目标，请确认内容和目标无误。",
            "policy": policy,
            "content_preview": content,
            **retry_policy,
        }

    if channel != "feishu":
        return {
            "sendable": True,
            "mode": "mock",
            "channel": channel or "local",
            "severity": "info",
            "title": "本地模拟发送",
            "message": "来源不是飞书，Phase 0 会写入模拟发送审计，不会触达外部 IM。",
            "policy": {"channel": channel or "local"},
            "content_preview": content,
            **retry_policy,
        }

    conversation = session.get(Conversation, message.conversation_id)
    conversation_send_mode = (conversation.send_mode if conversation else "inherit") or "inherit"
    default_send_mode = get_default_send_mode(session, message.tenant_id)
    send_mode = default_send_mode if conversation_send_mode == "inherit" else conversation_send_mode
    chat_id = str((message.normalized_json or {}).get("conversation_id") or "")
    policy = {
        "conversation_send_mode": conversation_send_mode,
        "default_send_mode": default_send_mode,
        "effective_send_mode": send_mode,
        "enable_external_send": settings.enable_external_send,
        "chat_id": chat_id,
    }
    if not chat_id:
        return {
            "sendable": False,
            "mode": "blocked",
            "channel": "feishu",
            "severity": "error",
            "title": "缺少飞书会话 ID",
            "message": "源消息没有 chat_id，无法发送飞书回复。",
            "policy": policy,
            **retry_policy,
        }
    if send_mode == "disabled":
        return {
            "sendable": False,
            "mode": "disabled",
            "channel": "feishu",
            "severity": "error",
            "title": "会话策略禁止发送",
            "message": "当前会话 send_mode=disabled，发送按钮只会提示，不会触达外部 IM。",
            "policy": policy,
            **retry_policy,
        }
    if send_mode == "mock" or not settings.enable_external_send:
        return {
            "sendable": True,
            "mode": "mock",
            "channel": "feishu",
            "severity": "info",
            "title": "即将模拟发送",
            "message": "系统会记录发送审计，但不会真正发到飞书。",
            "policy": policy,
            "content_preview": content,
            **retry_policy,
        }
    return {
        "sendable": True,
        "mode": "real",
        "channel": "feishu",
        "severity": "warning",
        "title": "即将真实发送到飞书",
        "message": "这次操作会调用飞书接口并把内容发到原会话，请确认内容和会话无误。",
        "policy": policy,
        "content_preview": content,
        **retry_policy,
    }


def send_approval_reply(session: Session, approval: Approval) -> Approval:
    if approval.status == "sent":
        return approval
    if approval.status not in SENDABLE_APPROVAL_STATUSES:
        raise HTTPException(status_code=400, detail="Only approved or edited approvals can be sent")
    previous_delivery = latest_delivery_run_for_approval(session, approval)
    if previous_delivery and previous_delivery.status == "success":
        approval.status = "sent"
        approval.operated_at = approval.operated_at or previous_delivery.created_at
        approval.sent_at = approval.sent_at or previous_delivery.created_at
        session.add(approval)
        session.commit()
        session.refresh(approval)
        return approval
    delivery_attempts = delivery_attempt_count_for_approval(session, approval)
    retry_policy = delivery_retry_policy(previous_delivery, delivery_attempts)
    if not retry_policy.get("retry_allowed", True):
        raise HTTPException(
            status_code=400,
            detail={
                "message": retry_policy.get("retry_message") or "Delivery retry is currently blocked.",
                "retry": retry_policy,
            },
        )

    original_run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    message = session.get(MessageEvent, original_run.message_id) if original_run and original_run.message_id else None
    if message is None:
        record_delivery_run(
            session=session,
            approval=approval,
            original_message=None,
            status="failed",
            output={"error": "Original message not found for approval."},
        )
        raise HTTPException(status_code=400, detail="Original message not found for approval")

    content = approval.final_content or approval.draft_content
    if not content:
        record_delivery_run(
            session=session,
            approval=approval,
            original_message=message,
            status="failed",
            output={"error": "Approval has no final or draft content to send."},
        )
        raise HTTPException(status_code=400, detail="Approval has no final or draft content to send")

    delivery_attempt = delivery_attempts + 1
    try:
        delivery = deliver_message(session, message, content)
    except FeishuAdapterError as exc:
        record_delivery_run(
            session=session,
            approval=approval,
            original_message=message,
            status="failed",
            output={**failed_delivery_context(message), "error": str(exc), "code": exc.code, "advice": exc.advice, "body": exc.body},
            attempt=delivery_attempt,
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "code": exc.code, "advice": exc.advice}) from exc
    except WeComAdapterError as exc:
        record_delivery_run(
            session=session,
            approval=approval,
            original_message=message,
            status="failed",
            output={**failed_delivery_context(message), "error": str(exc), "code": exc.code, "advice": exc.advice, "body": exc.body},
            attempt=delivery_attempt,
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "code": exc.code, "advice": exc.advice}) from exc
    except Exception as exc:  # noqa: BLE001 - delivery failures should be audited and returned.
        record_delivery_run(
            session=session,
            approval=approval,
            original_message=message,
            status="failed",
            output={"error": str(exc)},
            attempt=delivery_attempt,
        )
        raise HTTPException(status_code=502, detail=f"Failed to deliver approval reply: {exc}") from exc

    record_delivery_run(
        session=session,
        approval=approval,
        original_message=message,
        status="success",
        output=delivery,
        attempt=delivery_attempt,
    )

    approval.status = "sent"
    approval.final_content = content
    approval.operated_at = utc_now()
    approval.sent_at = approval.operated_at
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return approval


def deliver_message(session: Session, message: MessageEvent, content: str) -> dict[str, Any]:
    channel = str((message.normalized_json or {}).get("channel") or "")
    if channel == "feishu":
        conversation = session.get(Conversation, message.conversation_id)
        conversation_send_mode = (conversation.send_mode if conversation else "inherit") or "inherit"
        default_send_mode = get_default_send_mode(session, message.tenant_id)
        send_mode = default_send_mode if conversation_send_mode == "inherit" else conversation_send_mode
        chat_id = str((message.normalized_json or {}).get("conversation_id") or "")
        if not chat_id:
            raise FeishuAdapterError("Cannot send Feishu reply because the source message has no chat_id.")
        if send_mode == "disabled":
            raise FeishuAdapterError("This Feishu conversation has external sending disabled by policy.")
        if send_mode == "mock":
            return {
                "channel": "feishu",
                "mode": "mock",
                "chat_id": chat_id,
                "policy": {"send_mode": send_mode, "conversation_send_mode": conversation_send_mode, "default_send_mode": default_send_mode},
                "feishu_message_id": None,
                "result": {
                    "sent": False,
                    "mode": "mock",
                    "reason": "Conversation send_mode=mock, external Feishu send was not attempted.",
                    "text": content,
                },
            }
        request_uuid = stable_delivery_uuid(message, content)
        result = FeishuClient(get_settings()).send_text_to_chat(chat_id=chat_id, text=content, request_uuid=request_uuid)
        return {
            "channel": "feishu",
            "mode": "real" if get_settings().enable_external_send else "mock",
            "chat_id": chat_id,
            "request_uuid": request_uuid,
            "feishu_message_id": extract_feishu_message_id(result),
            "policy": {"send_mode": send_mode, "conversation_send_mode": conversation_send_mode, "default_send_mode": default_send_mode},
            "result": result,
            }
    if channel == "wecom":
        conversation = session.get(Conversation, message.conversation_id)
        conversation_send_mode = (conversation.send_mode if conversation else "inherit") or "inherit"
        default_send_mode = get_default_send_mode(session, message.tenant_id)
        send_mode = default_send_mode if conversation_send_mode == "inherit" else conversation_send_mode
        workbuddy_wecom = (message.raw_json or {}).get("workbuddy_wecom") if isinstance((message.raw_json or {}).get("workbuddy_wecom"), dict) else {}
        target_type = str(workbuddy_wecom.get("delivery_target_type") or ("chat" if (message.normalized_json or {}).get("conversation_type") == "group" else "user"))
        target_id = str(workbuddy_wecom.get("delivery_target_id") or (message.normalized_json or {}).get("conversation_id") or (message.normalized_json or {}).get("sender_id") or "")
        if not target_id:
            raise WeComAdapterError("Cannot send WeCom reply because the source message has no delivery target.")
        if send_mode == "disabled":
            raise WeComAdapterError("This WeCom conversation has external sending disabled by policy.")
        if send_mode == "mock":
            return {
                "channel": "wecom",
                "mode": "mock",
                "target_type": target_type,
                "target_id": target_id,
                "policy": {"send_mode": send_mode, "conversation_send_mode": conversation_send_mode, "default_send_mode": default_send_mode},
                "result": {
                    "sent": False,
                    "mode": "mock",
                    "reason": "Conversation send_mode=mock, external WeCom send was not attempted.",
                    "text": content,
                },
            }
        request_uuid = stable_delivery_uuid(message, content)
        client = WeComClient(get_settings())
        result = client.send_text_to_chat(target_id, content, request_uuid=request_uuid) if target_type == "chat" else client.send_text_to_user(target_id, content, request_uuid=request_uuid)
        return {
            "channel": "wecom",
            "mode": "real" if get_settings().enable_external_send else "mock",
            "target_type": target_type,
            "target_id": target_id,
            "request_uuid": request_uuid,
            "policy": {"send_mode": send_mode, "conversation_send_mode": conversation_send_mode, "default_send_mode": default_send_mode},
            "result": result,
        }

    return {
        "channel": channel or "local",
        "result": {
            "sent": False,
            "mode": "mock",
            "reason": "Source channel is not Feishu. Phase 0.2.4 records a mock delivery only.",
            "text": content,
        },
        "feishu_message_id": None,
    }


def record_delivery_run(
    session: Session,
    approval: Approval,
    original_message: MessageEvent | None,
    status: str,
    output: dict[str, Any],
    attempt: int | None = None,
) -> AgentRun:
    started = time.perf_counter()
    agent_type = "wecom_send_adapter" if output.get("channel") == "wecom" else "feishu_send_adapter"
    run = AgentRun(
        tenant_id=approval.tenant_id,
        message_id=original_message.id if original_message else None,
        agent_type=agent_type,
        status=status,
        prompt_version="phase0.2.4-delivery-v1",
        prompt_json={
            "approval_id": approval.id,
            "source_message_id": original_message.id if original_message else None,
            "external_message_id": original_message.external_message_id if original_message else None,
            "delivery_attempt": attempt,
        },
        model_provider="local",
        model_name="delivery-adapter",
        model_output_json=output,
        action_json={
            "approval_id": approval.id,
            "action_type": "send_approval_reply",
            "delivery_channel": output.get("channel"),
            "delivery_mode": extract_delivery_mode(output),
            "chat_id": output.get("chat_id"),
            "target_type": output.get("target_type"),
            "target_id": output.get("target_id"),
            "feishu_message_id": output.get("feishu_message_id"),
            "request_uuid": output.get("request_uuid"),
            "delivery_attempt": attempt,
        },
        confidence=1.0 if status == "success" else 0.0,
        risk_level="medium",
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_message=output.get("error"),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def latest_delivery_run_for_approval(session: Session, approval: Approval) -> AgentRun | None:
    if approval.id is None:
        return None
    original_run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    source_message_id = original_run.message_id if original_run else None
    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == approval.tenant_id, AgentRun.agent_type.in_(DELIVERY_AGENT_TYPES))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    for run in runs:
        if (run.action_json or {}).get("approval_id") != approval.id:
            continue
        if source_message_id is not None:
            prompt_source = (run.prompt_json or {}).get("source_message_id")
            if run.message_id != source_message_id and str(prompt_source) != str(source_message_id):
                continue
        if run.created_at < approval.created_at:
            continue
        return run
    return None


def delivery_runs_for_approval(session: Session, approval: Approval) -> list[AgentRun]:
    if approval.id is None:
        return []
    original_run = session.get(AgentRun, approval.agent_run_id) if approval.agent_run_id else None
    source_message_id = original_run.message_id if original_run else None
    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.tenant_id == approval.tenant_id, AgentRun.agent_type.in_(DELIVERY_AGENT_TYPES))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    matched = []
    for run in runs:
        if (run.action_json or {}).get("approval_id") != approval.id:
            continue
        if source_message_id is not None:
            prompt_source = (run.prompt_json or {}).get("source_message_id")
            if run.message_id != source_message_id and str(prompt_source) != str(source_message_id):
                continue
        if run.created_at < approval.created_at:
            continue
        matched.append(run)
    return matched


def delivery_attempt_count_for_approval(session: Session, approval: Approval) -> int:
    return len(delivery_runs_for_approval(session, approval))


def extract_delivery_mode(output: dict[str, Any]) -> str | None:
    if output.get("mode"):
        return str(output.get("mode"))
    result = output.get("result")
    if isinstance(result, dict):
        return result.get("mode")
    if output.get("channel") == "feishu" and output.get("feishu_message_id"):
        return "real"
    return None


def failed_delivery_context(message: MessageEvent) -> dict[str, Any]:
    channel = str((message.normalized_json or {}).get("channel") or "")
    if channel == "wecom":
        workbuddy_wecom = (message.raw_json or {}).get("workbuddy_wecom") if isinstance((message.raw_json or {}).get("workbuddy_wecom"), dict) else {}
        target_type = str(workbuddy_wecom.get("delivery_target_type") or ("chat" if (message.normalized_json or {}).get("conversation_type") == "group" else "user"))
        target_id = str(workbuddy_wecom.get("delivery_target_id") or (message.normalized_json or {}).get("conversation_id") or (message.normalized_json or {}).get("sender_id") or "")
        return {"channel": "wecom", "mode": "real", "target_type": target_type, "target_id": target_id}
    if channel == "feishu":
        chat_id = str((message.normalized_json or {}).get("conversation_id") or "")
        return {"channel": "feishu", "mode": "real", "chat_id": chat_id}
    return {"channel": channel or "local", "mode": "mock"}


def stable_delivery_uuid(message: MessageEvent, content: str) -> str:
    seed = f"workbuddy:{message.tenant_id}:{message.external_message_id}:{content}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def extract_feishu_message_id(result: dict[str, Any]) -> str | None:
    data = result.get("data") if isinstance(result, dict) else None
    if isinstance(data, dict):
        value = data.get("message_id")
        if value:
            return str(value)
    return None


def delivery_retry_policy(previous_delivery: AgentRun | None, delivery_attempts: int) -> dict[str, Any]:
    base = {
        "delivery_attempts": delivery_attempts,
        "previous_delivery_status": previous_delivery.status if previous_delivery else None,
        "max_delivery_attempts": MAX_DELIVERY_ATTEMPTS,
        "retry_allowed": True,
        "retry_after_seconds": 0,
        "next_retry_at": None,
        "next_attempt": delivery_attempts + 1,
    }
    if previous_delivery is None or previous_delivery.status != "failed":
        return base

    if delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
        return {
            **base,
            "retry_allowed": False,
            "next_attempt": None,
            "retry_title": "发送重试次数已达上限",
            "retry_message": f"这条审批已经尝试发送 {delivery_attempts} 次。请先检查飞书配置、会话策略和错误日志，再人工处理。",
        }

    backoff_seconds = DELIVERY_RETRY_BACKOFF_SECONDS.get(delivery_attempts, 300)
    next_retry_at = ensure_beijing_time(previous_delivery.created_at) + timedelta(seconds=backoff_seconds)
    remaining_seconds = max(0, int((next_retry_at - utc_now()).total_seconds()))
    return {
        **base,
        "retry_allowed": remaining_seconds == 0,
        "retry_after_seconds": remaining_seconds,
        "next_retry_at": next_retry_at.isoformat(),
        "retry_title": "等待重试冷却" if remaining_seconds else "可以重试发送",
        "retry_message": (
            f"上次发送失败后需要等待 {backoff_seconds} 秒再重试，预计 {next_retry_at.isoformat()} 可再次发送。"
            if remaining_seconds
            else f"上次发送失败已超过 {backoff_seconds} 秒，可以进行第 {delivery_attempts + 1} 次发送。"
        ),
    }


def ensure_beijing_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)
