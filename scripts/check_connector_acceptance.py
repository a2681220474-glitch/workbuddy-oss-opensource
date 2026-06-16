from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD = "ConnectorAcceptance#2026"
AUTHORIZATION_PHRASE = "CONFIRM WORKBUDDY REAL SEND"


def main() -> int:
    original_cwd = Path.cwd()
    checks: list[tuple[str, bool, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="workbuddy-connectors-") as temp_dir:
            temp_root = Path(temp_dir)
            configure_isolated_runtime(temp_root)
            write_fake_worker_status(temp_root)
            os.chdir(temp_root)
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            from fastapi.testclient import TestClient
            from sqlmodel import Session, select

            from apps.api.db.session import engine
            from apps.api.main import app
            from apps.api.models import AgentRun, Approval, ChannelEvent, utc_now
            from apps.api.modules.approvals.delivery import delivery_retry_policy

            with TestClient(app) as client:
                expect_json(
                    client.post(
                        "/api/auth/bootstrap",
                        json={
                            "username": "connector_admin",
                            "display_name": "连接器验收管理员",
                            "password": ADMIN_PASSWORD,
                        },
                    ),
                    200,
                    "bootstrap",
                )

                feishu_payload = build_feishu_payload()
                feishu_receive = expect_json(
                    client.post("/api/channels/feishu/webhook", json=feishu_payload),
                    200,
                    "feishu receive",
                )
                record(
                    checks,
                    "feishu_receive",
                    feishu_receive.get("message_count") == 1 and bool(feishu_receive.get("message_ids")),
                    "Feishu callback enters MessageEvent and routing without external network access.",
                )
                feishu_duplicate = expect_json(
                    client.post("/api/channels/feishu/webhook", json=feishu_payload),
                    200,
                    "duplicate Feishu receive",
                )
                record(
                    checks,
                    "feishu_message_idempotency",
                    feishu_duplicate.get("message_count") == 0 and not feishu_duplicate.get("message_ids"),
                    "The same Feishu message ID is ignored when the platform retries delivery.",
                )
                with Session(engine) as session:
                    approval = session.exec(select(Approval).order_by(Approval.id.desc())).first()
                    approval_id = int(approval.id or 0) if approval else 0
                    if approval:
                        session.add(
                            AgentRun(
                                tenant_id=approval.tenant_id,
                                agent_type="feishu_send_adapter",
                                status="success",
                                model_output_json={"channel": "feishu", "mode": "real"},
                                action_json={"approval_id": approval_id, "action_type": "send_approval_reply"},
                                created_at=utc_now(),
                            )
                        )
                        session.commit()
                card_callback = expect_json(
                    client.post("/api/channels/feishu/webhook", json=build_feishu_card_callback_payload(approval_id)),
                    200,
                    "feishu approval card callback",
                )
                with Session(engine) as session:
                    updated_approval = session.get(Approval, approval_id)
                    callback_event = session.exec(
                        select(ChannelEvent)
                        .where(ChannelEvent.channel_type == "feishu", ChannelEvent.event_type == "feishu.approval_card.callback")
                        .order_by(ChannelEvent.id.desc())
                    ).first()
                record(
                    checks,
                    "feishu_card_callback",
                    is_raw_replacement_card(card_callback)
                    and completed_card_actions(card_callback) == ["已通过", "查看详情"]
                    and detail_button_url(card_callback) == f"https://workbuddy.example.test/#approvals?id={approval_id}"
                    and updated_approval is not None
                    and updated_approval.status == "approved"
                    and callback_event is not None,
                    "Feishu approval callbacks return a raw replacement card, update the original card, and expose a working detail URL.",
                )

                rejected_receive = expect_json(
                    client.post(
                        "/api/channels/feishu/webhook",
                        json=build_feishu_payload(
                            event_id="connector-feishu-rejected-event-001",
                            message_id="connector-feishu-rejected-message-001",
                        ),
                    ),
                    200,
                    "Feishu rejected-card source receive",
                )
                with Session(engine) as session:
                    rejected_approval = session.exec(
                        select(Approval)
                        .where(Approval.status == "pending_review")
                        .order_by(Approval.id.desc())
                    ).first()
                    rejected_approval_id = int(rejected_approval.id or 0) if rejected_approval else 0
                rejected_callback = expect_json(
                    client.post(
                        "/api/channels/feishu/webhook",
                        json=build_feishu_card_callback_payload(
                            rejected_approval_id,
                            decision="rejected",
                            event_id="connector-feishu-card-callback-rejected-001",
                        ),
                    ),
                    200,
                    "Feishu rejected approval card callback",
                )
                with Session(engine) as session:
                    rejected_approval = session.get(Approval, rejected_approval_id)
                record(
                    checks,
                    "feishu_card_rejection",
                    rejected_receive.get("message_count") == 1
                    and is_raw_replacement_card(rejected_callback)
                    and completed_card_actions(rejected_callback) == ["已拒绝", "查看详情"]
                    and rejected_approval is not None
                    and rejected_approval.status == "rejected",
                    "Feishu rejection callbacks use the same valid raw-card response contract.",
                )

                wecom_receive = expect_json(
                    client.post("/api/channels/wecom/webhook", json=build_wecom_payload()),
                    200,
                    "wecom receive",
                )
                record(
                    checks,
                    "wecom_receive",
                    wecom_receive.get("mode") == "json_debug" and bool(wecom_receive.get("message_ids")),
                    "WeCom debug callback enters the same business workflow.",
                )

                feishu_mock = expect_json(
                    client.post(
                        "/api/channels/feishu/mock-send",
                        json={"chat_id": "acceptance-chat", "text": "飞书安全模拟发送"},
                    ),
                    200,
                    "feishu mock send",
                )
                wecom_mock = expect_json(
                    client.post(
                        "/api/channels/wecom/mock-send",
                        json={"target_type": "user", "target_id": "acceptance-user", "text": "企微安全模拟发送"},
                    ),
                    200,
                    "wecom mock send",
                )
                record(
                    checks,
                    "mock_send_safety",
                    feishu_mock.get("mode") == "mock"
                    and feishu_mock.get("sent") is False
                    and wecom_mock.get("mode") == "mock"
                    and wecom_mock.get("sent") is False,
                    "Both connector mock sends create audit runs and never contact external platforms.",
                )

                missing_phrase = client.post(
                    "/api/channels/feishu/test-send",
                    json={"chat_id": "blocked", "text": "blocked", "confirm_real_send": True},
                )
                disabled_send = client.post(
                    "/api/channels/wecom/test-send",
                    json={
                        "target_type": "user",
                        "target_id": "blocked",
                        "text": "blocked",
                        "confirm_real_send": True,
                        "authorization_phrase": AUTHORIZATION_PHRASE,
                    },
                )
                record(
                    checks,
                    "real_send_gate",
                    missing_phrase.status_code == 400
                    and "authorization_phrase" in missing_phrase.text
                    and disabled_send.status_code == 400
                    and "ENABLE_EXTERNAL_SEND=false" in disabled_send.text,
                    "Real diagnostics sends require the exact phrase and remain blocked by the global switch.",
                )

                with Session(engine) as session:
                    retry_payload = build_feishu_payload(
                        event_id="connector-feishu-retry-event-001",
                        message_id="connector-feishu-retry-message-001",
                    )
                    event = ChannelEvent(
                        tenant_id=1,
                        channel_type="feishu",
                        event_type="feishu.webhook.parse.failed",
                        external_event_id="connector-acceptance-failed-event",
                        status="failed",
                        raw_json={"raw_payload": retry_payload},
                    )
                    session.add(event)
                    session.commit()
                    session.refresh(event)
                    event_id = int(event.id or 0)

                retry = expect_json(client.post(f"/api/channel-events/{event_id}/retry"), 200, "receive retry")
                record(
                    checks,
                    "receive_retry",
                    retry.get("status") == "success" and bool(retry.get("message_ids")),
                    "A stored failed Feishu callback can be replayed into the import workflow.",
                )

                with Session(engine) as session:
                    recent_failure = AgentRun(
                        tenant_id=1,
                        agent_type="feishu_send_adapter",
                        status="failed",
                        model_output_json={"error": "temporary acceptance failure"},
                        action_json={"delivery_attempt": 1},
                        created_at=utc_now(),
                    )
                    old_failure = AgentRun(
                        tenant_id=1,
                        agent_type="wecom_send_adapter",
                        status="failed",
                        model_output_json={"error": "old acceptance failure"},
                        action_json={"delivery_attempt": 2},
                        created_at=utc_now() - timedelta(minutes=10),
                    )
                    recent_policy = delivery_retry_policy(recent_failure, 1)
                    old_policy = delivery_retry_policy(old_failure, 2)
                record(
                    checks,
                    "delivery_retry_policy",
                    recent_policy.get("retry_allowed") is False
                    and int(recent_policy.get("retry_after_seconds") or 0) > 0
                    and old_policy.get("retry_allowed") is True
                    and old_policy.get("next_attempt") == 3,
                    "Delivery retry enforces cooldown and permits the next attempt after backoff.",
                )

                feishu_diagnostics = expect_json(
                    client.get("/api/channels/feishu/diagnostics/full"),
                    200,
                    "feishu diagnostics",
                )
                wecom_diagnostics = expect_json(
                    client.get("/api/channels/wecom/diagnostics/full"),
                    200,
                    "wecom diagnostics",
                )
                record(
                    checks,
                    "safe_acceptance_summary",
                    feishu_diagnostics.get("safe_acceptance", {}).get("safe_verified") is True
                    and wecom_diagnostics.get("safe_acceptance", {}).get("safe_verified") is True
                    and feishu_diagnostics.get("safe_acceptance", {}).get("automated_real_send") is False
                    and wecom_diagnostics.get("safe_acceptance", {}).get("automated_real_send") is False,
                    "Both diagnostics pages expose a safe verification result without claiming real-send completion.",
                )
                record(
                    checks,
                    "feishu_card_callback_diagnostics",
                    feishu_diagnostics.get("card_callback", {}).get("ready") is True
                    and feishu_diagnostics.get("card_callback", {}).get("callback_url") == "https://workbuddy.example.test/api/channels/feishu/webhook"
                    and "目标回调服务当前未在线" in str(feishu_diagnostics.get("card_callback", {}).get("feishu_error_when_offline") or ""),
                    "Feishu diagnostics explain approval-card callback reachability and the offline callback error.",
                )
                record(
                    checks,
                    "workflow_traces",
                    int(feishu_diagnostics.get("acceptance_summary", {}).get("ready") or 0) >= 1
                    and int(wecom_diagnostics.get("acceptance_summary", {}).get("ready") or 0) >= 1,
                    "Both received messages reach a traceable business object and approval workflow.",
                )
                record(
                    checks,
                    "isolated_artifacts",
                    (temp_root / "connector-acceptance.db").exists()
                    and not (ROOT / "connector-acceptance.db").exists(),
                    "Connector acceptance leaves real local data and secrets untouched.",
                )
    except Exception as exc:
        print(f"[fatal] connector_acceptance: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_cwd)

    failed = [check for check in checks if not check[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} connector acceptance check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nConnector acceptance checks passed ({len(checks)} checks).")
    return 0


def configure_isolated_runtime(temp_root: Path) -> None:
    os.environ.update(
        {
            "WORKBUDDY_ENVIRONMENT": "local",
            "WORKBUDDY_DATABASE_URL": f"sqlite:///{temp_root / 'connector-acceptance.db'}",
            "WORKBUDDY_AUTH_SECRET_PATH": str(temp_root / "auth-secret.txt"),
            "WORKBUDDY_FEISHU_STREAM_STATUS_PATH": str(temp_root / "feishu-worker-status.json"),
            "WORKBUDDY_FEISHU_APP_ID": "cli_acceptance_feishu",
            "WORKBUDDY_FEISHU_APP_SECRET": "acceptance-secret",
            "WORKBUDDY_FEISHU_VERIFICATION_TOKEN": "acceptance-token",
            "WORKBUDDY_PUBLIC_BASE_URL": "https://workbuddy.example.test",
            "WORKBUDDY_WECOM_CORP_ID": "ww_acceptance",
            "WORKBUDDY_WECOM_AGENT_ID": "1000002",
            "WORKBUDDY_WECOM_SECRET": "acceptance-secret",
            "WORKBUDDY_WECOM_TOKEN": "acceptance-token",
            "WORKBUDDY_ENABLE_REAL_IM_ADAPTERS": "true",
            "WORKBUDDY_ENABLE_EXTERNAL_SEND": "false",
            "WORKBUDDY_ENABLE_BACKGROUND_JOBS": "false",
            "WORKBUDDY_LLM_PROVIDER": "mock",
            "WORKBUDDY_LLM_API_KEY": "",
        }
    )


def write_fake_worker_status(temp_root: Path) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    payload = {
        "status": "running",
        "pid": os.getpid(),
        "updated_at": now,
        "last_heartbeat_at": now,
        "heartbeat_count": 1,
    }
    (temp_root / "feishu-worker-status.json").write_text(json.dumps(payload), encoding="utf-8")


def build_feishu_payload(
    *,
    event_id: str = "connector-feishu-event-001",
    message_id: str = "connector-feishu-message-001",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "token": "acceptance-token",
            "create_time": "1781220000000",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_connector_acceptance"},
                "sender_name": "飞书验收用户",
            },
            "message": {
                "message_id": message_id,
                "chat_id": "oc_connector_acceptance",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "系统登录失败无法使用，请尽快处理"}, ensure_ascii=False),
                "create_time": "1781220000000",
            },
        },
    }


def build_feishu_card_callback_payload(
    approval_id: int,
    *,
    decision: str = "approved",
    event_id: str = "connector-feishu-card-callback-001",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "card.action.trigger",
            "token": "acceptance-token",
            "create_time": "1781220000000",
        },
        "event": {
            "operator": {"open_id": "ou_connector_acceptance", "name": "飞书验收用户"},
            "action": {
                "value": {
                    "source": "workbuddy_approval_card",
                    "approval_id": approval_id,
                    "decision": decision,
                }
            },
        },
    }


def build_wecom_payload() -> dict[str, Any]:
    return {
        "MsgType": "text",
        "FromUserName": "wecom_connector_acceptance",
        "Content": "系统登录失败无法使用，请尽快处理",
        "CreateTime": "1781220000",
        "MsgId": "connector-wecom-message-001",
    }


def completed_card_actions(payload: dict[str, Any]) -> list[str]:
    card = replacement_card_data(payload)
    elements = card.get("elements") if isinstance(card.get("elements"), list) else []
    action = next((item for item in elements if isinstance(item, dict) and item.get("tag") == "action"), {})
    actions = action.get("actions") if isinstance(action.get("actions"), list) else []
    return [
        str((item.get("text") or {}).get("content"))
        for item in actions
        if isinstance(item, dict) and isinstance(item.get("text"), dict)
    ]


def detail_button_url(payload: dict[str, Any]) -> str | None:
    card = replacement_card_data(payload)
    elements = card.get("elements") if isinstance(card.get("elements"), list) else []
    action = next((item for item in elements if isinstance(item, dict) and item.get("tag") == "action"), {})
    actions = action.get("actions") if isinstance(action.get("actions"), list) else []
    detail = next(
        (
            item
            for item in actions
            if isinstance(item, dict) and (item.get("text") or {}).get("content") == "查看详情"
        ),
        {},
    )
    return str(detail.get("url")) if detail.get("url") else None


def is_raw_replacement_card(payload: dict[str, Any]) -> bool:
    card_wrapper = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    card = card_wrapper.get("data") if isinstance(card_wrapper.get("data"), dict) else {}
    return (
        isinstance(payload.get("toast"), dict)
        and card_wrapper.get("type") == "raw"
        and isinstance(card.get("config"), dict)
        and isinstance(card.get("header"), dict)
        and isinstance(card.get("elements"), list)
    )


def replacement_card_data(payload: dict[str, Any]) -> dict[str, Any]:
    card_wrapper = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    return card_wrapper.get("data") if isinstance(card_wrapper.get("data"), dict) else {}


def expect_json(response: Any, expected_status: int, label: str) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:600]}")
    return response.json()


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
