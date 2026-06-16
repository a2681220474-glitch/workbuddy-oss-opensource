from __future__ import annotations

from typing import Any

from sqlmodel import select

from apps.api.models import AgentRun, ChannelEvent


REAL_SEND_AUTHORIZATION_PHRASE = "CONFIRM WORKBUDDY REAL SEND"


def build_connector_acceptance_report(
    session: Any,
    tenant_id: int,
    channel: str,
    *,
    production_readiness: dict[str, Any],
    recent: dict[str, Any],
    acceptance_summary: dict[str, Any],
) -> dict[str, Any]:
    send_runs = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.agent_type == f"{channel}_send_adapter",
            AgentRun.status == "success",
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(30)
    ).all()
    mock_verified = any((run.model_output_json or {}).get("mode") == "mock" for run in send_runs)
    receive_verified = bool(recent.get("last_message"))
    routed_verified = int(acceptance_summary.get("ready") or 0) > 0
    retry_runs = session.exec(
        select(AgentRun).where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.agent_type.in_(["feishu_receive_retry", "feishu_send_adapter", "wecom_send_adapter"]),
        )
    ).all()
    retry_evidence = any(
        (channel == "feishu" and run.agent_type == "feishu_receive_retry")
        or (
            run.agent_type == f"{channel}_send_adapter"
            and int((run.action_json or {}).get("delivery_attempt") or 0) > 1
        )
        for run in retry_runs
    )
    failed_events = session.exec(
        select(ChannelEvent).where(
            ChannelEvent.tenant_id == tenant_id,
            ChannelEvent.channel_type == channel,
            ChannelEvent.status == "failed",
        )
    ).all()
    checks = [
        acceptance_check("configuration", "连接器配置", not production_readiness.get("blocking_failed"), "阻塞配置项已补齐"),
        acceptance_check("receive_evidence", "接收链路证据", receive_verified, "已有最近消息进入 WorkBuddy"),
        acceptance_check("workflow_trace", "业务链路证据", routed_verified, "已有消息达到 ready 或 complete"),
        acceptance_check("mock_send", "安全模拟发送", mock_verified, "已有 Mock 发送审计，不触达外部平台"),
        acceptance_check(
            "failure_recovery",
            "失败恢复策略",
            retry_evidence or not failed_events,
            "已有重试证据" if retry_evidence else "当前无待恢复失败事件，发送重试策略已启用",
        ),
    ]
    safe_verified = all(check["ok"] for check in checks)
    return {
        "status": "safe_verified" if safe_verified else "needs_attention",
        "safe_verified": safe_verified,
        "automated_real_send": False,
        "real_send_requires_manual_authorization": True,
        "authorization_phrase": REAL_SEND_AUTHORIZATION_PHRASE,
        "real_send_evidence": latest_real_send_evidence(session, tenant_id, channel),
        "checks": checks,
        "next_action": (
            "自动安全复验已通过。真实外发仍需人工确认目标、内容并输入授权短语。"
            if safe_verified
            else "先处理未通过的安全检查；不要执行真实外发。"
        ),
    }


def require_real_send_authorization(payload: dict[str, Any]) -> None:
    if payload.get("confirm_real_send") is not True:
        raise ValueError("confirm_real_send=true is required for diagnostics real send.")
    if str(payload.get("authorization_phrase") or "").strip() != REAL_SEND_AUTHORIZATION_PHRASE:
        raise ValueError(f"authorization_phrase must equal: {REAL_SEND_AUTHORIZATION_PHRASE}")


def latest_real_send_evidence(session: Any, tenant_id: int, channel: str) -> dict[str, Any] | None:
    runs = session.exec(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.agent_type == f"{channel}_send_adapter",
            AgentRun.status == "success",
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(20)
    ).all()
    for run in runs:
        output = run.model_output_json or {}
        if output.get("mode") == "real":
            return {
                "agent_run_id": run.id,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
            }
    return None


def acceptance_check(key: str, label: str, ok: bool, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "ok": ok,
        "status": "ok" if ok else "pending",
        "message": message if ok else pending_message(key),
    }


def pending_message(key: str) -> str:
    messages = {
        "configuration": "仍有阻塞配置项未完成。",
        "receive_evidence": "尚无最近消息进入接收链路。",
        "workflow_trace": "尚无达到 ready 或 complete 的业务链路。",
        "mock_send": "尚未执行安全 Mock 发送。",
        "failure_recovery": "存在待恢复失败事件且暂无重试证据。",
    }
    return messages.get(key, "等待人工复验。")
