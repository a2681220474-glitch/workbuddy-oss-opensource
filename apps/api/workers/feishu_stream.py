from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

from sqlmodel import Session, select

from apps.api.core.config import Settings, get_settings
from apps.api.db.session import engine, init_db
from apps.api.models import BEIJING_TZ, AgentRun, Tenant
from apps.api.modules.adapters.feishu import parse_feishu_stream_event
from apps.api.modules.channels.service import record_channel_event
from apps.api.modules.channels.stream_status import write_feishu_stream_status
from apps.api.modules.imports.service import import_records
from apps.api.shared.structured_logging import configure_service_logging, log_event


logger = logging.getLogger("workbuddy.feishu_stream")

MESSAGE_RECEIVE_EVENT = "im.message.receive_v1"
BOT_ADDED_EVENT = "im.chat.member.bot.added_v1"
BOT_DELETED_EVENT = "im.chat.member.bot.deleted_v1"
BOT_P2P_ENTERED_EVENT = "im.chat.access_event.bot_p2p_chat_entered_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Feishu long-connection event worker.")
    parser.add_argument("--check", action="store_true", help="Validate configuration and SDK imports without connecting.")
    args = parser.parse_args()

    configure_service_logging("feishu-worker")
    settings = get_settings()
    validate_settings(settings)
    configure_certificates()
    import_lark_sdk()

    if args.check:
        log_event(logger, "feishu_stream_check", status="ok")
        return

    write_feishu_stream_status(
        "starting",
        app_id=mask_value(settings.feishu_app_id),
        events=supported_events(),
    )
    init_db()
    try:
        client = build_stream_client(settings)
        write_feishu_stream_status(
            "running",
            app_id=mask_value(settings.feishu_app_id),
            events=supported_events(),
            note="Worker process is running. Feishu console validation succeeds only while this process stays online.",
            heartbeat=True,
        )
        start_status_heartbeat(settings)
        log_event(logger, "feishu_stream_start", app_id=mask_value(settings.feishu_app_id))
        client.start()
    except Exception as exc:
        write_feishu_stream_status("failed", app_id=mask_value(settings.feishu_app_id), error=str(exc))
        raise


def validate_settings(settings: Settings) -> None:
    missing = []
    if not settings.feishu_app_id:
        missing.append("FEISHU_APP_ID")
    if not settings.feishu_app_secret:
        missing.append("FEISHU_APP_SECRET")
    if missing:
        raise RuntimeError(f"Missing required Feishu stream settings: {', '.join(missing)}.")
    if not settings.enable_real_im_adapters:
        raise RuntimeError("Set ENABLE_REAL_IM_ADAPTERS=true before starting the Feishu stream worker.")


def configure_certificates() -> None:
    try:
        import certifi
    except ImportError:
        return
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)


def import_lark_sdk():
    try:
        import lark_oapi as lark
        from lark_oapi.ws import Client as FeishuWsClient
    except ImportError as exc:
        raise RuntimeError("Missing lark-oapi. Install API dependencies before starting the stream worker.") from exc
    return lark, FeishuWsClient


def build_stream_client(settings: Settings):
    lark, FeishuWsClient = import_lark_sdk()
    event_handler = build_event_handler(lark, settings)
    return FeishuWsClient(settings.feishu_app_id, settings.feishu_app_secret, event_handler=event_handler)


def build_event_handler(lark: Any, settings: Settings):
    builder = lark.EventDispatcherHandler.builder(settings.feishu_verification_token, settings.feishu_encrypt_key or "")
    handlers: dict[str, tuple[str, Callable[[Any], None]]] = {
        "register_p2_im_message_receive_v1": (MESSAGE_RECEIVE_EVENT, handle_event(MESSAGE_RECEIVE_EVENT)),
        "register_p2_im_chat_member_bot_added_v1": (BOT_ADDED_EVENT, handle_event(BOT_ADDED_EVENT)),
        "register_p2_im_chat_member_bot_deleted_v1": (BOT_DELETED_EVENT, handle_event(BOT_DELETED_EVENT)),
        "register_p2_im_chat_access_event_bot_p2p_chat_entered_v1": (
            BOT_P2P_ENTERED_EVENT,
            handle_event(BOT_P2P_ENTERED_EVENT),
        ),
    }
    for method_name, (event_type, handler) in handlers.items():
        register = getattr(builder, method_name, None)
        if register is None:
            logger.warning("lark-oapi SDK does not expose %s; %s will be ignored.", method_name, event_type)
            continue
        returned = register(handler)
        builder = returned or builder
        logger.info("Registered Feishu stream handler for %s.", event_type)
    return builder.build()


def handle_event(event_type: str) -> Callable[[Any], None]:
    def _handler(data: Any) -> None:
        payload: dict[str, Any] | None = None
        try:
            payload = event_payload_to_dict(data)
            result = process_stream_payload(payload, event_type)
            logger.info("Processed Feishu stream event: %s", json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:  # noqa: BLE001 - keep the long connection alive after one bad event.
            record_stream_failure(event_type, str(exc), payload)
            write_feishu_stream_status(
                "running",
                app_id=mask_value(get_settings().feishu_app_id),
                events=supported_events(),
                last_event_type=event_type,
                last_error=str(exc),
                append_error=worker_error_summary(event_type, str(exc), payload),
            )
            logger.exception("Failed to process Feishu stream event: %s", event_type)

    return _handler


def record_stream_failure(event_type: str, error: str, payload: dict[str, Any] | None = None) -> None:
    try:
        with Session(engine) as session:
            tenant = get_demo_tenant(session)
            payload_hash = payload_digest(payload or {"event_type": event_type, "error": error})
            record_channel_event(
                session=session,
                tenant=tenant,
                channel_type="feishu",
                event_type="feishu.stream.process.failed",
                status="failed",
                payload={
                    "event_id": f"feishu.stream.process.failed:{event_type}:{payload_hash}",
                    "source_event_type": event_type,
                    "error": error,
                    "raw_payload": payload,
                    "payload_hash": payload_hash,
                },
            )
            record_worker_run(
                session=session,
                tenant=tenant,
                event_type=event_type,
                status="failed",
                output={"error": error, "payload_hash": payload_hash},
            )
    except Exception:  # noqa: BLE001 - failure recording must not kill the stream handler.
        logger.exception("Failed to record Feishu stream processing failure.")


def process_stream_payload(payload: dict[str, Any], event_type: str) -> dict[str, Any]:
    result = parse_feishu_stream_event(payload, event_type)
    with Session(engine) as session:
        tenant = get_demo_tenant(session)
        if result.kind == "message" and result.record is not None:
            batch, messages = import_records(
                session=session,
                tenant=tenant,
                records=[result.record],
                source="feishu_stream",
                filename="feishu-stream",
            )
            write_feishu_stream_status(
                "running",
                app_id=mask_value(get_settings().feishu_app_id),
                events=supported_events(),
                last_event_type=event_type,
                last_message_ids=[message.id for message in messages],
                heartbeat=True,
                append_event=worker_event_summary(
                    event_type,
                    status="success",
                    kind="message",
                    message_ids=[message.id for message in messages],
                    batch_id=batch.id,
                ),
            )
            record_worker_run(
                session=session,
                tenant=tenant,
                event_type=event_type,
                status="success",
                message_id=messages[0].id if messages else None,
                output={"message_ids": [message.id for message in messages], "batch_id": batch.id},
            )
            return {
                "status": "ok",
                "kind": "message",
                "batch_id": batch.id,
                "message_count": len(messages),
                "message_ids": [message.id for message in messages],
            }

        if result.kind == "channel_event":
            event = record_channel_event(
                session=session,
                tenant=tenant,
                channel_type="feishu",
                event_type=result.reason or event_type,
                payload=payload,
            )
            write_feishu_stream_status(
                "running",
                app_id=mask_value(get_settings().feishu_app_id),
                events=supported_events(),
                last_event_type=event_type,
                last_channel_event_id=event.id,
                heartbeat=True,
                append_event=worker_event_summary(
                    event_type,
                    status="success",
                    kind="channel_event",
                    channel_event_id=event.id,
                ),
            )
            record_worker_run(
                session=session,
                tenant=tenant,
                event_type=event_type,
                status="success",
                output={"channel_event_id": event.id},
            )
            return {"status": "ok", "kind": "channel_event", "channel_event_id": event.id}

    write_feishu_stream_status(
        "running",
        app_id=mask_value(get_settings().feishu_app_id),
        events=supported_events(),
        last_event_type=event_type,
        last_ignored_reason=result.reason,
        heartbeat=True,
        append_event=worker_event_summary(event_type, status="ignored", kind=result.kind, reason=result.reason),
    )
    with Session(engine) as session:
        tenant = get_demo_tenant(session)
        record_worker_run(
            session=session,
            tenant=tenant,
            event_type=event_type,
            status="ignored",
            output={"reason": result.reason},
        )
    return {"status": "ignored", "kind": result.kind, "reason": result.reason}


def record_worker_run(
    session: Session,
    tenant: Tenant,
    event_type: str,
    status: str,
    output: dict[str, Any],
    message_id: int | None = None,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant.id,
        message_id=message_id,
        agent_type="feishu_stream_worker",
        status=status,
        prompt_version="v0.15.3-stream-observability-v1",
        prompt_json={"event_type": event_type},
        model_provider="local",
        model_name="feishu-stream",
        model_output_json=output,
        action_json={"action_type": "receive_feishu_event", "event_type": event_type},
        confidence=1.0 if status == "success" else 0.0,
        risk_level="low",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def supported_events() -> list[str]:
    return [MESSAGE_RECEIVE_EVENT, BOT_ADDED_EVENT, BOT_DELETED_EVENT, BOT_P2P_ENTERED_EVENT]


def start_status_heartbeat(settings: Settings, interval_seconds: int = 30) -> None:
    def _loop() -> None:
        while True:
            time.sleep(interval_seconds)
            try:
                write_feishu_stream_status(
                    "running",
                    app_id=mask_value(settings.feishu_app_id),
                    events=supported_events(),
                    heartbeat=True,
                    note="Worker heartbeat is fresh. No event may mean Feishu has not delivered new messages yet.",
                )
            except Exception:  # noqa: BLE001 - heartbeat failures should not kill the worker.
                logger.exception("Failed to write Feishu stream heartbeat.")

    thread = threading.Thread(target=_loop, name="feishu-stream-heartbeat", daemon=True)
    thread.start()


def worker_event_summary(event_type: str, *, status: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "status": status,
        "kind": kind,
        "occurred_at": now_iso(),
        **extra,
    }


def worker_error_summary(event_type: str, error: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "status": "failed",
        "error": error,
        "payload_hash": payload_digest(payload or {"event_type": event_type, "error": error}),
        "occurred_at": now_iso(),
        "recovery_hint": "查看最近错误和 ChannelEvent；确认飞书事件权限、Encrypt Key、消息类型解析和 API 配置后重启 worker。",
    }


def payload_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    from datetime import datetime

    return datetime.now(BEIJING_TZ).isoformat()


def mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:6]}...{value[-4:]}"


def get_demo_tenant(session: Session) -> Tenant:
    settings = get_settings()
    tenant = session.exec(select(Tenant).where(Tenant.key == settings.demo_tenant_key)).first()
    if tenant is None:
        raise RuntimeError(f"Tenant not found: {settings.demo_tenant_key}. Run API startup or init_db first.")
    return tenant


def event_payload_to_dict(data: Any) -> dict[str, Any]:
    lark, _ = import_lark_sdk()
    try:
        marshaled = lark.JSON.marshal(data)
    except Exception:  # noqa: BLE001 - fall back to Python object introspection below.
        marshaled = data

    if isinstance(marshaled, str):
        return json.loads(marshaled)
    if isinstance(marshaled, dict):
        return marshaled
    if hasattr(marshaled, "to_dict"):
        return marshaled.to_dict()
    if hasattr(marshaled, "__dict__"):
        return object_to_plain_dict(marshaled)
    raise TypeError(f"Unsupported Feishu event payload type: {type(data)!r}")


def object_to_plain_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: object_to_plain_dict(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [object_to_plain_dict(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: object_to_plain_dict(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


if __name__ == "__main__":
    main()
