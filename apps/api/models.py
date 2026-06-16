from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(BEIJING_TZ)


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True, max_length=80)
    name: str = Field(max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class Channel(SQLModel, table=True):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("tenant_id", "type", "account_id", name="uq_channel_account"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    type: str = Field(default="local", max_length=50, index=True)
    name: str = Field(default="Local Import", max_length=200)
    account_id: str = Field(default="local", max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class RuntimeSetting(SQLModel, table=True):
    __tablename__ = "runtime_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_runtime_setting_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    key: str = Field(max_length=120, index=True)
    value: str = Field(default="", max_length=500)
    updated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class LocalUser(SQLModel, table=True):
    __tablename__ = "local_users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_local_user_username"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    username: str = Field(max_length=80, index=True)
    display_name: str = Field(max_length=120)
    password_hash: Optional[str] = Field(default=None, max_length=500)
    role: str = Field(default="admin", max_length=30, index=True)
    status: str = Field(default="active", max_length=30, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelEvent(SQLModel, table=True):
    __tablename__ = "channel_events"
    __table_args__ = (UniqueConstraint("tenant_id", "external_event_id", name="uq_channel_event_external"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    channel_type: str = Field(default="feishu", max_length=50, index=True)
    event_type: str = Field(max_length=120, index=True)
    external_event_id: str = Field(max_length=200, index=True)
    conversation_external_id: Optional[str] = Field(default=None, max_length=200, index=True)
    actor_external_id: Optional[str] = Field(default=None, max_length=200, index=True)
    status: str = Field(default="received", max_length=30, index=True)
    raw_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ExternalUser(SQLModel, table=True):
    __tablename__ = "external_users"
    __table_args__ = (UniqueConstraint("tenant_id", "channel", "external_user_id", name="uq_external_user"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    channel: str = Field(default="feishu", max_length=50, index=True)
    external_user_id: str = Field(max_length=200, index=True)
    name: str = Field(default="", max_length=200)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    email: Optional[str] = Field(default=None, max_length=200)
    mobile: Optional[str] = Field(default=None, max_length=80)
    raw_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_synced_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "channel_id", "external_conversation_id", name="uq_conversation_external"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    channel_id: int = Field(foreign_key="channels.id", index=True)
    external_conversation_id: str = Field(max_length=200, index=True)
    type: str = Field(default="group", max_length=30)
    name: str = Field(default="Demo Conversation", max_length=200)
    bound_agent: Optional[str] = Field(default=None, max_length=80)
    send_mode: str = Field(default="inherit", max_length=30, index=True)
    last_message_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class MessageEvent(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("tenant_id", "external_message_id", name="uq_message_external"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: str = Field(index=True, max_length=120)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    channel_id: int = Field(foreign_key="channels.id", index=True)
    conversation_id: int = Field(foreign_key="conversations.id", index=True)
    external_message_id: str = Field(max_length=200, index=True)
    sender_external_id: str = Field(max_length=200, index=True)
    sender_name: str = Field(max_length=200)
    message_type: str = Field(default="text", max_length=30)
    text: str = Field(default="")
    normalized_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    raw_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    received_at: datetime = Field(default_factory=utc_now, index=True)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_type: str = Field(max_length=80, index=True)
    status: str = Field(default="success", max_length=30, index=True)
    prompt_version: str = Field(default="phase0-rules-v1", max_length=80)
    prompt_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    model_provider: str = Field(default="local", max_length=80)
    model_name: str = Field(default="rule-engine", max_length=100)
    model_output_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    action_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    confidence: float = Field(default=0.0)
    risk_level: str = Field(default="low", max_length=20)
    latency_ms: int = Field(default=0)
    tokens_used: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Approval(SQLModel, table=True):
    __tablename__ = "approvals"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    status: str = Field(default="pending_review", max_length=30, index=True)
    draft_content: str = Field(default="")
    final_content: Optional[str] = None
    operator_id: Optional[int] = None
    operated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    title: str = Field(max_length=240)
    customer_name: str = Field(default="未知客户", max_length=200)
    category: str = Field(default="support", max_length=80, index=True)
    priority: str = Field(default="medium", max_length=30, index=True)
    status: str = Field(default="open", max_length=30, index=True)
    summary: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    customer_name: str = Field(default="未知客户", max_length=200)
    company: Optional[str] = Field(default=None, max_length=200)
    interest: str = Field(default="业务咨询", max_length=240)
    stage: str = Field(default="new", max_length=50, index=True)
    score: int = Field(default=50, index=True)
    priority: str = Field(default="medium", max_length=30, index=True)
    summary: str = Field(default="")
    next_step: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class FollowupTask(SQLModel, table=True):
    __tablename__ = "followup_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    title: str = Field(max_length=240)
    task_type: str = Field(default="followup", max_length=50, index=True)
    status: str = Field(default="todo", max_length=30, index=True)
    priority: str = Field(default="medium", max_length=30, index=True)
    related_object_type: Optional[str] = Field(default=None, max_length=50, index=True)
    related_object_id: Optional[int] = Field(default=None, index=True)
    assignee_user_id: Optional[int] = Field(default=None, index=True)
    assignee_username: Optional[str] = Field(default=None, max_length=80, index=True)
    assignee_name: Optional[str] = Field(default=None, max_length=120)
    due_hint: Optional[str] = Field(default=None, max_length=120)
    due_at: Optional[datetime] = Field(default=None, index=True)
    summary: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None

    @property
    def is_overdue(self) -> bool:
        if self.due_at is None or self.status in {"done", "cancelled"}:
            return False
        due_at = self.due_at if self.due_at.tzinfo else self.due_at.replace(tzinfo=BEIJING_TZ)
        return due_at < utc_now()


class ProcessingRecord(SQLModel, table=True):
    __tablename__ = "processing_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    object_type: str = Field(max_length=50, index=True)
    object_id: int = Field(index=True)
    action_type: str = Field(default="note", max_length=50, index=True)
    status: Optional[str] = Field(default=None, max_length=50, index=True)
    assignee_user_id: Optional[int] = Field(default=None, index=True)
    assignee_username: Optional[str] = Field(default=None, max_length=80, index=True)
    assignee_name: Optional[str] = Field(default=None, max_length=120)
    due_hint: Optional[str] = Field(default=None, max_length=120)
    due_at: Optional[datetime] = Field(default=None, index=True)
    next_step: Optional[str] = Field(default=None, max_length=500)
    note: str = Field(default="")
    operator_user_id: Optional[int] = Field(default=None, index=True)
    operator_username: Optional[str] = Field(default=None, max_length=80, index=True)
    operator_name: str = Field(default="本地账号", max_length=120)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    action_type: str = Field(max_length=80, index=True)
    scope_type: str = Field(default="system", max_length=80, index=True)
    scope_id: Optional[int] = Field(default=None, index=True)
    object_type: Optional[str] = Field(default=None, max_length=80, index=True)
    object_id: Optional[int] = Field(default=None, index=True)
    operator_user_id: Optional[int] = Field(default=None, index=True)
    operator_username: Optional[str] = Field(default=None, max_length=80, index=True)
    operator_name: str = Field(default="系统", max_length=120)
    status: Optional[str] = Field(default=None, max_length=40, index=True)
    summary: str = Field(default="", max_length=500)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Candidate(SQLModel, table=True):
    __tablename__ = "candidates"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    name: str = Field(default="未知候选人", max_length=200)
    role: str = Field(default="待确认岗位", max_length=200)
    stage: str = Field(default="new", max_length=50, index=True)
    match_score: int = Field(default=50, index=True)
    summary: str = Field(default="")
    interview_questions_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    onboarding_checklist_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeGap(SQLModel, table=True):
    __tablename__ = "knowledge_gaps"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    question: str = Field(max_length=500)
    suggested_answer: str = Field(default="")
    category: str = Field(default="general", max_length=80, index=True)
    occurrence_count: int = Field(default=1)
    status: str = Field(default="pending", max_length=30, index=True)
    examples_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeItem(SQLModel, table=True):
    __tablename__ = "knowledge_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source_gap_id: Optional[int] = Field(default=None, foreign_key="knowledge_gaps.id", index=True)
    title: str = Field(max_length=240)
    answer: str = Field(default="")
    category: str = Field(default="general", max_length=80, index=True)
    status: str = Field(default="draft", max_length=30, index=True)
    review_due_at: Optional[datetime] = Field(default=None, index=True)
    last_reviewed_at: Optional[datetime] = Field(default=None, index=True)
    quality_status: str = Field(default="healthy", max_length=40, index=True)
    quality_score: int = Field(default=80, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeItemVersion(SQLModel, table=True):
    __tablename__ = "knowledge_item_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    item_id: int = Field(foreign_key="knowledge_items.id", index=True)
    version_no: int = Field(default=1, index=True)
    title: str = Field(max_length=240)
    answer: str = Field(default="")
    category: str = Field(default="general", max_length=80, index=True)
    status: str = Field(default="draft", max_length=30, index=True)
    change_type: str = Field(default="snapshot", max_length=50, index=True)
    change_summary: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class KnowledgeEmbedding(SQLModel, table=True):
    __tablename__ = "knowledge_embeddings"
    __table_args__ = (UniqueConstraint("tenant_id", "item_id", name="uq_knowledge_embedding_item"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    item_id: int = Field(foreign_key="knowledge_items.id", index=True)
    model: str = Field(default="workbuddy-local-hash-v1", max_length=80, index=True)
    dimensions: int = Field(default=192)
    vector_json: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    content_hash: str = Field(max_length=64, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class KnowledgeHit(SQLModel, table=True):
    __tablename__ = "knowledge_hits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", "source_object_type", "source_object_id", name="uq_knowledge_hit_source"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    item_id: int = Field(foreign_key="knowledge_items.id", index=True)
    source_object_type: str = Field(default="ticket", max_length=50, index=True)
    source_object_id: int = Field(index=True)
    query_text: str = Field(default="")
    score: int = Field(default=0, index=True)
    answer_snapshot: str = Field(default="")
    status: str = Field(default="suggested", max_length=30, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    agent_run_id: Optional[int] = Field(default=None, foreign_key="agent_runs.id", index=True)
    report_type: str = Field(max_length=80, index=True)
    scope_type: str = Field(default="tenant", max_length=80, index=True)
    scope_id: Optional[str] = Field(default=None, max_length=200, index=True)
    title: str = Field(max_length=240)
    summary: str = Field(default="")
    metrics_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    sections_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    source_message_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ImportBatch(SQLModel, table=True):
    __tablename__ = "import_batches"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    source: str = Field(default="local", max_length=50, index=True)
    filename: Optional[str] = Field(default=None, max_length=240)
    status: str = Field(default="completed", max_length=30, index=True)
    total_rows: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    completed_at: Optional[datetime] = None
