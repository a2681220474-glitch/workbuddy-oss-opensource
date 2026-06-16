from __future__ import annotations

from typing import Any
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.core.config import get_settings
from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.modules.audit.service import append_audit_log
from apps.api.modules.channels.feishu import recent_feishu_activity
from apps.api.modules.channels.wecom import recent_wecom_activity
from apps.api.modules.channels.stream_status import read_feishu_stream_status
from apps.api.modules.release_audit.service import build_release_audit
from apps.api.shared.runtime_status import runtime_stack_snapshot
from sqlmodel import select

from apps.api.models import Conversation
from apps.api.modules.config_center.settings_store import get_default_send_mode, set_default_send_mode
from apps.api.modules.config_center.secret_store import (
    ENV_LINE_RE,
    LOCAL_RUNTIME_ENV_PATH,
    SECRET_ENV_KEYS,
    env_keys_for_canonical_secrets,
    migrate_plaintext_secrets,
    remove_secret_lines,
    rotate_master_key,
    save_encrypted_secrets,
    secret_storage_status,
)
from apps.api.shared.llm import smoke_test_llm


router = APIRouter()


def ensure_admin(role: str) -> None:
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can change system configuration.")


class DefaultSendModeUpdate(BaseModel):
    default_send_mode: str = Field(pattern="^(mock|real)$")


class LLMRuntimeUpdate(BaseModel):
    provider: str = Field(default="mock", max_length=80)
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="workbuddy-demo", max_length=200)
    api_key: str | None = Field(default=None, max_length=2000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class LLMSmokeTestRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=2000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)


class RuntimePolicyUpdate(BaseModel):
    enable_real_im_adapters: bool
    enable_external_send: bool


class FeishuRuntimeUpdate(BaseModel):
    app_id: str = Field(default="", max_length=200)
    app_secret: str | None = Field(default=None, max_length=2000)
    verification_token: str | None = Field(default=None, max_length=2000)
    encrypt_key: str | None = Field(default=None, max_length=2000)
    api_base_url: str = Field(default="https://open.feishu.cn", max_length=500)
    approval_chat_id: str = Field(default="", max_length=200)


class WeComRuntimeUpdate(BaseModel):
    corp_id: str = Field(default="", max_length=200)
    agent_id: str = Field(default="", max_length=200)
    secret: str | None = Field(default=None, max_length=2000)
    token: str | None = Field(default=None, max_length=2000)
    encoding_aes_key: str | None = Field(default=None, max_length=2000)


class DingTalkRuntimeUpdate(BaseModel):
    client_id: str = Field(default="", max_length=200)
    client_secret: str | None = Field(default=None, max_length=2000)
    robot_code: str = Field(default="", max_length=300)
    webhook_secret: str | None = Field(default=None, max_length=2000)


@router.get("/status")
def config_status(session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    settings = get_settings()
    feishu_stream = read_feishu_stream_status()
    default_send_mode = get_default_send_mode(session, tenant.id)
    llm_provider = settings.llm_provider.strip().lower() or "mock"
    llm_mode = "mock" if llm_provider in {"mock", "demo", "local"} else "real"
    runtime_stack = runtime_stack_snapshot(settings)
    secrets = secret_storage_status()
    return {
        "app": {
            "name": settings.app_name,
            "environment": settings.environment,
            "database": runtime_stack["database"]["label"],
            "database_backend": runtime_stack["database"]["backend"],
            "database_persistence": runtime_stack["database"]["persistence"],
            "database_connected": runtime_stack["database"]["connected"],
            "redis_configured": runtime_stack["redis"]["configured"],
            "redis_connected": runtime_stack["redis"]["connected"],
            "deployment_mode": runtime_stack["deployment"]["mode"],
        },
        "llm": {
            "provider": llm_provider,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
            "mode": llm_mode,
            "configured": settings.llm_configured,
            "real_configured": settings.llm_real_configured,
            "base_url_configured": bool(settings.llm_base_url),
            "api_key_configured": bool(settings.llm_api_key),
            "timeout_seconds": settings.llm_timeout_seconds,
            "supported_providers": ["mock", "openai_compatible", "deepseek", "qwen", "moonshot"],
            "config_keys": ["LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"],
        },
        "global_policy": {
            "enable_real_im_adapters": settings.enable_real_im_adapters,
            "enable_external_send": settings.enable_external_send,
            "enable_background_jobs": settings.enable_background_jobs,
            "background_queue_driver": settings.background_queue_driver,
            "default_send_mode": default_send_mode,
            "effective_send_mode": "real" if default_send_mode == "real" and settings.enable_external_send else "mock",
            "real_send_requires_env": default_send_mode == "real" and not settings.enable_external_send,
        },
        "runtime_stack": runtime_stack,
        "release_audit": build_release_audit(
            session,
            tenant.id,
            settings,
            runtime=runtime_stack,
            secret_status=secrets,
        ),
        "secret_storage": secrets,
        "channels": [
            {
                "channel": "feishu",
                "label": "飞书",
                "configured": settings.feishu_configured,
                "adapter_status": "stream_ready" if feishu_stream.get("running") else "configured" if settings.feishu_configured else "not_configured",
                "real_adapter_enabled": settings.enable_real_im_adapters,
                "external_send_enabled": settings.enable_external_send,
                "worker": feishu_stream,
                "recent": recent_feishu_activity(session, tenant.id),
                "config_keys": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN", "FEISHU_ENCRYPT_KEY"],
                "webhook_path": "/api/channels/feishu/webhook",
                "setup_status": "ready" if settings.feishu_configured else "missing_credentials",
                "runtime_values": {
                    "app_id": settings.feishu_app_id,
                    "api_base_url": settings.feishu_api_base_url,
                    "approval_chat_id": settings.feishu_approval_chat_id,
                    "app_secret_configured": bool(settings.feishu_app_secret),
                    "verification_token_configured": bool(settings.feishu_verification_token),
                    "encrypt_key_configured": bool(settings.feishu_encrypt_key),
                },
                "capabilities": {
                    "receive_event": True,
                    "normalize_message": True,
                    "send_message": True,
                    "send_approval_card": bool(settings.feishu_approval_chat_id),
                    "resolve_user": True,
                    "resolve_conversation": True,
                    "encrypted_callback": True,
                },
            },
            {
                "channel": "wecom",
                "label": "企业微信",
                "configured": settings.wecom_configured,
                "adapter_status": "callback_ready" if settings.wecom_configured and settings.wecom_token else "configured" if settings.wecom_configured else "ready_to_configure",
                "real_adapter_enabled": settings.enable_real_im_adapters and settings.wecom_configured,
                "external_send_enabled": settings.enable_external_send,
                "worker": None,
                "recent": recent_wecom_activity(session, tenant.id),
                "config_keys": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET", "WECOM_TOKEN", "WECOM_ENCODING_AES_KEY"],
                "webhook_path": "/api/channels/wecom/webhook",
                "setup_status": "ready_for_callback" if settings.wecom_configured and settings.wecom_token else "credentials_ready" if settings.wecom_configured else "waiting_for_credentials",
                "runtime_values": {
                    "corp_id": settings.wecom_corp_id,
                    "agent_id": settings.wecom_agent_id,
                    "secret_configured": bool(settings.wecom_secret),
                    "token_configured": bool(settings.wecom_token),
                    "encoding_aes_key_configured": bool(settings.wecom_encoding_aes_key),
                    "callback_mode": "encrypted" if settings.wecom_encoding_aes_key else "plain_or_compat",
                },
                "capabilities": {
                    "receive_event": settings.wecom_configured,
                    "normalize_message": True,
                    "send_message": settings.wecom_configured,
                    "resolve_user": False,
                    "resolve_conversation": False,
                },
            },
            {
                "channel": "dingtalk",
                "label": "钉钉",
                "configured": settings.dingtalk_configured,
                "adapter_status": "configured" if settings.dingtalk_configured else "ready_to_configure",
                "real_adapter_enabled": settings.enable_real_im_adapters and settings.dingtalk_configured,
                "external_send_enabled": False,
                "worker": None,
                "recent": None,
                "config_keys": ["DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET", "DINGTALK_ROBOT_CODE", "DINGTALK_WEBHOOK_SECRET"],
                "webhook_path": "/api/channels/dingtalk/webhook",
                "setup_status": "credentials_ready" if settings.dingtalk_configured else "waiting_for_credentials",
                "runtime_values": {
                    "client_id": settings.dingtalk_client_id,
                    "robot_code": settings.dingtalk_robot_code,
                    "client_secret_configured": bool(settings.dingtalk_client_secret),
                    "webhook_secret_configured": bool(settings.dingtalk_webhook_secret),
                },
                "capabilities": {
                    "receive_event": settings.dingtalk_configured,
                    "normalize_message": True,
                    "send_message": False,
                    "resolve_user": False,
                    "resolve_conversation": False,
                },
            },
        ],
    }


@router.patch("/runtime/llm")
def update_llm_runtime(payload: LLMRuntimeUpdate, session: SessionDep, tenant: TenantDep, current_user: CurrentUserDep) -> dict[str, Any]:
    ensure_admin(current_user.role)
    saved_keys = save_local_runtime_env(
        {
            "LLM_PROVIDER": payload.provider.strip() or "mock",
            "LLM_BASE_URL": payload.base_url.strip(),
            "LLM_API_KEY": payload.api_key,
            "LLM_MODEL": payload.model.strip() or "workbuddy-demo",
            "LLM_TIMEOUT_SECONDS": payload.timeout_seconds,
        }
    )
    append_audit_log(
        session,
        tenant.id,
        "runtime_llm_updated",
        f"{current_user.display_name} 更新模型运行配置",
        operator=current_user,
        scope_type="config",
        object_type="runtime_llm",
        status="saved",
        detail_json={"saved_keys": saved_keys, "provider": payload.provider, "model": payload.model, "base_url": payload.base_url},
    )
    session.commit()
    return runtime_saved_response(saved_keys)


@router.post("/runtime/llm/smoke-test")
def smoke_test_llm_runtime(
    current_user: CurrentUserDep,
    payload: LLMSmokeTestRequest | None = None,
) -> dict[str, Any]:
    ensure_admin(current_user.role)
    body = payload or LLMSmokeTestRequest()
    return smoke_test_llm(
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        timeout_seconds=body.timeout_seconds,
    )


@router.patch("/runtime/policy")
def update_runtime_policy(payload: RuntimePolicyUpdate, session: SessionDep, tenant: TenantDep, current_user: CurrentUserDep) -> dict[str, Any]:
    ensure_admin(current_user.role)
    saved_keys = save_local_runtime_env(
        {
            "ENABLE_REAL_IM_ADAPTERS": payload.enable_real_im_adapters,
            "ENABLE_EXTERNAL_SEND": payload.enable_external_send,
        }
    )
    append_audit_log(
        session,
        tenant.id,
        "runtime_policy_updated",
        f"{current_user.display_name} 更新全局发送策略",
        operator=current_user,
        scope_type="config",
        object_type="runtime_policy",
        status="saved",
        detail_json={
            "saved_keys": saved_keys,
            "enable_real_im_adapters": payload.enable_real_im_adapters,
            "enable_external_send": payload.enable_external_send,
        },
    )
    session.commit()
    return runtime_saved_response(saved_keys)


@router.patch("/runtime/channels/{channel}")
def update_channel_runtime(
    channel: Literal["feishu", "wecom", "dingtalk"],
    payload: dict[str, Any],
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    ensure_admin(current_user.role)
    if channel == "feishu":
        feishu_payload = FeishuRuntimeUpdate.model_validate(payload)
        saved_keys = save_local_runtime_env(
            {
                "FEISHU_APP_ID": feishu_payload.app_id.strip(),
                "FEISHU_APP_SECRET": feishu_payload.app_secret,
                "FEISHU_VERIFICATION_TOKEN": feishu_payload.verification_token,
                "FEISHU_ENCRYPT_KEY": feishu_payload.encrypt_key,
                "FEISHU_API_BASE_URL": feishu_payload.api_base_url.strip() or "https://open.feishu.cn",
                "FEISHU_APPROVAL_CHAT_ID": feishu_payload.approval_chat_id.strip(),
            }
        )
        append_audit_log(
            session,
            tenant.id,
            "channel_runtime_updated",
            f"{current_user.display_name} 更新飞书配置",
            operator=current_user,
            scope_type="config",
            object_type="channel_feishu",
            status="saved",
            detail_json={"saved_keys": saved_keys, "app_id": feishu_payload.app_id, "approval_chat_id": feishu_payload.approval_chat_id},
        )
        session.commit()
        return runtime_saved_response(saved_keys, restart_hint="飞书长连接 Worker 需要重启后才会使用新密钥。")
    if channel == "wecom":
        wecom_payload = WeComRuntimeUpdate.model_validate(payload)
        saved_keys = save_local_runtime_env(
            {
                "WECOM_CORP_ID": wecom_payload.corp_id.strip(),
                "WECOM_AGENT_ID": wecom_payload.agent_id.strip(),
                "WECOM_SECRET": wecom_payload.secret,
                "WECOM_TOKEN": wecom_payload.token,
                "WECOM_ENCODING_AES_KEY": wecom_payload.encoding_aes_key,
            }
        )
        append_audit_log(
            session,
            tenant.id,
            "channel_runtime_updated",
            f"{current_user.display_name} 更新企微配置",
            operator=current_user,
            scope_type="config",
            object_type="channel_wecom",
            status="saved",
            detail_json={"saved_keys": saved_keys, "corp_id": wecom_payload.corp_id, "agent_id": wecom_payload.agent_id},
        )
        session.commit()
        return runtime_saved_response(saved_keys)
    dingtalk_payload = DingTalkRuntimeUpdate.model_validate(payload)
    saved_keys = save_local_runtime_env(
        {
            "DINGTALK_CLIENT_ID": dingtalk_payload.client_id.strip(),
            "DINGTALK_CLIENT_SECRET": dingtalk_payload.client_secret,
            "DINGTALK_ROBOT_CODE": dingtalk_payload.robot_code.strip(),
            "DINGTALK_WEBHOOK_SECRET": dingtalk_payload.webhook_secret,
        }
    )
    append_audit_log(
        session,
        tenant.id,
        "channel_runtime_updated",
        f"{current_user.display_name} 更新钉钉配置",
        operator=current_user,
        scope_type="config",
        object_type="channel_dingtalk",
        status="saved",
        detail_json={"saved_keys": saved_keys, "client_id": dingtalk_payload.client_id, "robot_code": dingtalk_payload.robot_code},
    )
    session.commit()
    return runtime_saved_response(saved_keys)


@router.patch("/default-send-mode")
def update_default_send_mode(
    payload: DefaultSendModeUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    ensure_admin(current_user.role)
    try:
        setting = set_default_send_mode(session, tenant.id, payload.default_send_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = get_settings()
    append_audit_log(
        session,
        tenant.id,
        "default_send_mode_updated",
        f"{current_user.display_name} 切换默认发送模式为 {setting.value}",
        operator=current_user,
        scope_type="config",
        object_type="default_send_mode",
        status=setting.value,
        detail_json={"effective_send_mode": "real" if setting.value == "real" and settings.enable_external_send else "mock"},
    )
    session.commit()
    return {
        "default_send_mode": setting.value,
        "effective_send_mode": "real" if setting.value == "real" and settings.enable_external_send else "mock",
        "enable_external_send": settings.enable_external_send,
        "real_send_requires_env": setting.value == "real" and not settings.enable_external_send,
    }


def save_local_runtime_env(updates: dict[str, str | int | bool | None]) -> list[str]:
    existing_lines = LOCAL_RUNTIME_ENV_PATH.read_text(encoding="utf-8").splitlines() if LOCAL_RUNTIME_ENV_PATH.exists() else []
    normalized_updates: dict[str, str] = {}
    secret_updates: dict[str, str] = {}
    for key, value in updates.items():
        if value is None:
            continue
        if key in SECRET_ENV_KEYS and value == "":
            continue
        if isinstance(value, bool):
            normalized_updates[key] = "true" if value else "false"
        else:
            text_value = str(value).replace("\n", "").replace("\r", "")
            if key in SECRET_ENV_KEYS:
                secret_updates[key] = text_value
            else:
                normalized_updates[key] = text_value

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        match = ENV_LINE_RE.match(line)
        if not match:
            new_lines.append(line)
            continue
        key = match.group(1)
        if key in normalized_updates:
            new_lines.append(f"{key}={normalized_updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    missing_keys = [key for key in normalized_updates if key not in seen]
    if missing_keys and new_lines and new_lines[-1].strip():
        new_lines.append("")
    for key in missing_keys:
        new_lines.append(f"{key}={normalized_updates[key]}")

    if normalized_updates:
        LOCAL_RUNTIME_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_RUNTIME_ENV_PATH.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
        LOCAL_RUNTIME_ENV_PATH.chmod(0o600)
    encrypted_keys = save_encrypted_secrets(secret_updates)
    remove_secret_lines(LOCAL_RUNTIME_ENV_PATH, env_keys_for_canonical_secrets(set(encrypted_keys)))
    get_settings.cache_clear()
    return [*normalized_updates.keys(), *encrypted_keys]


def runtime_saved_response(saved_keys: list[str], restart_hint: str | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": "saved",
        "settings_file": str(LOCAL_RUNTIME_ENV_PATH),
        "secret_store": "apps/api/data/runtime_secrets.json",
        "saved_keys": saved_keys,
        "secrets_masked": True,
        "api_reloaded": True,
    }
    if restart_hint:
        response["restart_hint"] = restart_hint
    return response


@router.post("/runtime/secrets/migrate")
def migrate_runtime_secrets(
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    ensure_admin(current_user.role)
    result = migrate_plaintext_secrets()
    get_settings.cache_clear()
    append_audit_log(
        session,
        tenant.id,
        "runtime_secrets_migrated",
        f"{current_user.display_name} 迁移本地敏感配置到加密仓库",
        operator=current_user,
        scope_type="config",
        object_type="runtime_secrets",
        status=str(result["status"]),
        detail_json={"migrated_keys": result["migrated_keys"]},
    )
    session.commit()
    return {**result, "secret_storage": secret_storage_status(), "secrets_masked": True}


@router.post("/runtime/secrets/rotate-key")
def rotate_runtime_secret_key(
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    ensure_admin(current_user.role)
    result = rotate_master_key()
    get_settings.cache_clear()
    append_audit_log(
        session,
        tenant.id,
        "runtime_secret_key_rotated",
        f"{current_user.display_name} 轮换本地敏感配置主密钥",
        operator=current_user,
        scope_type="config",
        object_type="runtime_secrets",
        status=str(result["status"]),
        detail_json={"rotated_keys": result["rotated_keys"]},
    )
    session.commit()
    return {**result, "secret_storage": secret_storage_status(), "secrets_masked": True}


@router.post("/safe-demo-mode")
def enable_safe_demo_mode(session: SessionDep, tenant: TenantDep, current_user: CurrentUserDep) -> dict[str, Any]:
    ensure_admin(current_user.role)
    setting = set_default_send_mode(session, tenant.id, "mock")
    conversations = session.exec(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.send_mode == "real",
        )
    ).all()
    for conversation in conversations:
        conversation.send_mode = "mock"
        session.add(conversation)
    append_audit_log(
        session,
        tenant.id,
        "safe_demo_mode_enabled",
        f"{current_user.display_name} 启用安全演示模式",
        operator=current_user,
        scope_type="config",
        object_type="safe_demo_mode",
        status="mock",
        detail_json={"updated_conversation_count": len(conversations)},
    )
    session.commit()
    return {
        "status": "safe_demo_mode_enabled",
        "default_send_mode": setting.value,
        "updated_conversation_count": len(conversations),
        "effective_send_mode": "mock",
        "notes": [
            "全局默认发送模式已切换为模拟发送。",
            "所有显式真实发送的会话策略已切换为模拟发送。",
            "环境变量 ENABLE_EXTERNAL_SEND 不会被页面修改；如需真实外发，请手动配置环境并重启服务。",
        ],
    }
