from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from apps.api.modules.config_center.secret_store import load_encrypted_secret_fields, load_runtime_setting_fields


class Settings(BaseSettings):
    app_name: str = Field(
        default="WorkBuddy OSS API",
        validation_alias=AliasChoices("WORKBUDDY_APP_NAME", "APP_NAME"),
    )
    environment: str = Field(
        default="local",
        validation_alias=AliasChoices("WORKBUDDY_ENVIRONMENT", "APP_ENV"),
    )
    database_url: str = Field(
        default="sqlite:///./apps/api/data/workbuddy.db",
        validation_alias=AliasChoices("WORKBUDDY_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_REDIS_URL", "REDIS_URL"),
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias=AliasChoices("WORKBUDDY_CORS_ORIGINS", "CORS_ORIGINS"),
    )
    public_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_PUBLIC_BASE_URL", "PUBLIC_BASE_URL", "API_PUBLIC_BASE_URL"),
    )
    demo_tenant_key: str = Field(
        default="tenant_demo",
        validation_alias=AliasChoices("WORKBUDDY_DEMO_TENANT_KEY", "DEMO_TENANT_KEY"),
    )
    demo_tenant_name: str = Field(
        default="Demo Tenant",
        validation_alias=AliasChoices("WORKBUDDY_DEMO_TENANT_NAME", "DEMO_TENANT_NAME"),
    )
    enable_real_im_adapters: bool = Field(
        default=False,
        validation_alias=AliasChoices("WORKBUDDY_ENABLE_REAL_IM_ADAPTERS", "ENABLE_REAL_IM_ADAPTERS"),
    )
    enable_external_send: bool = Field(
        default=False,
        validation_alias=AliasChoices("WORKBUDDY_ENABLE_EXTERNAL_SEND", "ENABLE_EXTERNAL_SEND"),
    )
    enable_background_jobs: bool = Field(
        default=False,
        validation_alias=AliasChoices("WORKBUDDY_ENABLE_BACKGROUND_JOBS", "ENABLE_BACKGROUND_JOBS"),
    )
    background_queue_driver: str = Field(
        default="database_polling",
        validation_alias=AliasChoices("WORKBUDDY_BACKGROUND_QUEUE_DRIVER", "BACKGROUND_QUEUE_DRIVER"),
    )
    background_jobs_status_path: str = Field(
        default="apps/api/data/runtime_jobs_status.json",
        validation_alias=AliasChoices("WORKBUDDY_BACKGROUND_JOBS_STATUS_PATH", "BACKGROUND_JOBS_STATUS_PATH"),
    )
    background_jobs_interval_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("WORKBUDDY_BACKGROUND_JOBS_INTERVAL_SECONDS", "BACKGROUND_JOBS_INTERVAL_SECONDS"),
    )
    llm_provider: str = Field(
        default="mock",
        validation_alias=AliasChoices("WORKBUDDY_LLM_PROVIDER", "WORKBUDDY_LLM_MODE", "LLM_PROVIDER"),
    )
    llm_model: str = Field(
        default="workbuddy-demo",
        validation_alias=AliasChoices("WORKBUDDY_LLM_MODEL", "LLM_MODEL", "OPENAI_MODEL"),
    )
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_LLM_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_timeout_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("WORKBUDDY_LLM_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"),
    )
    feishu_app_id: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_APP_ID", "FEISHU_APP_ID", "LARK_APP_ID"),
    )
    feishu_app_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_APP_SECRET", "FEISHU_APP_SECRET", "LARK_APP_SECRET"),
    )
    feishu_verification_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WORKBUDDY_FEISHU_VERIFICATION_TOKEN",
            "FEISHU_VERIFICATION_TOKEN",
            "LARK_VERIFICATION_TOKEN",
        ),
    )
    feishu_encrypt_key: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_ENCRYPT_KEY", "FEISHU_ENCRYPT_KEY", "LARK_ENCRYPT_KEY"),
    )
    feishu_api_base_url: str = Field(
        default="https://open.feishu.cn",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_API_BASE_URL", "FEISHU_API_BASE_URL", "LARK_API_BASE_URL"),
    )
    feishu_stream_status_path: str = Field(
        default="apps/api/data/feishu_stream_status.json",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_STREAM_STATUS_PATH", "FEISHU_STREAM_STATUS_PATH"),
    )
    feishu_approval_chat_id: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_FEISHU_APPROVAL_CHAT_ID", "FEISHU_APPROVAL_CHAT_ID"),
    )
    wecom_corp_id: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_WECOM_CORP_ID", "WECOM_CORP_ID"),
    )
    wecom_agent_id: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_WECOM_AGENT_ID", "WECOM_AGENT_ID"),
    )
    wecom_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_WECOM_SECRET", "WECOM_SECRET"),
    )
    wecom_token: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_WECOM_TOKEN", "WECOM_TOKEN"),
    )
    wecom_encoding_aes_key: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_WECOM_ENCODING_AES_KEY", "WECOM_ENCODING_AES_KEY"),
    )
    dingtalk_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_ID"),
    )
    dingtalk_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_DINGTALK_CLIENT_SECRET", "DINGTALK_CLIENT_SECRET"),
    )
    dingtalk_robot_code: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_DINGTALK_ROBOT_CODE", "DINGTALK_ROBOT_CODE"),
    )
    dingtalk_webhook_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_DINGTALK_WEBHOOK_SECRET", "DINGTALK_WEBHOOK_SECRET"),
    )
    auth_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WORKBUDDY_AUTH_SECRET", "AUTH_SECRET"),
    )
    auth_secret_path: str = Field(
        default="apps/api/data/auth_secret.txt",
        validation_alias=AliasChoices("WORKBUDDY_AUTH_SECRET_PATH", "AUTH_SECRET_PATH"),
    )
    auth_session_ttl_hours: int = Field(
        default=168,
        validation_alias=AliasChoices("WORKBUDDY_AUTH_SESSION_TTL_HOURS", "AUTH_SESSION_TTL_HOURS"),
    )
    auth_cookie_name: str = Field(
        default="workbuddy_session",
        validation_alias=AliasChoices("WORKBUDDY_AUTH_COOKIE_NAME", "AUTH_COOKIE_NAME"),
    )

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "apps/api/.env", "apps/api/.env.local"),
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def feishu_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    @property
    def llm_configured(self) -> bool:
        provider = self.llm_provider.strip().lower()
        if provider in {"", "mock", "demo", "local"}:
            return True
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def llm_real_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def wecom_configured(self) -> bool:
        return bool(self.wecom_corp_id and self.wecom_agent_id and self.wecom_secret)

    @property
    def dingtalk_configured(self) -> bool:
        return bool(self.dingtalk_client_id and self.dingtalk_client_secret)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    runtime_fields = load_runtime_setting_fields()
    if runtime_fields:
        settings = settings.model_copy(update=runtime_fields)
    encrypted_fields = load_encrypted_secret_fields()
    if encrypted_fields:
        settings = settings.model_copy(update=encrypted_fields)
    return settings
