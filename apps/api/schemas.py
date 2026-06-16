from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.api.shared.timezone import beijing_iso


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_encoders={datetime: beijing_iso})


class TenantRead(ORMModel):
    id: int
    key: str
    name: str
    created_at: datetime


class LocalUserRead(ORMModel):
    id: int
    tenant_id: int
    username: str
    display_name: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class LocalUserSummary(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    status: str


class LocalUserCreate(BaseModel):
    username: str
    display_name: str
    role: str = Field(default="handler", pattern="^(admin|approver|handler|readonly)$")
    password: str = Field(min_length=8, max_length=200)


class LocalUserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(admin|approver|handler|readonly)$")
    status: Optional[str] = Field(default=None, pattern="^(active|disabled)$")
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class AuthBootstrapStatusRead(BaseModel):
    needs_bootstrap: bool
    password_user_count: int
    active_user_count: int
    bootstrap_username: str = "local_admin"


class AuthBootstrapRequest(BaseModel):
    username: str = Field(default="local_admin", min_length=1, max_length=80)
    display_name: Optional[str] = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AuthChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class AuthSessionRead(BaseModel):
    status: str
    user: LocalUserRead


class MessageEventRead(ORMModel):
    id: int
    event_id: str
    tenant_id: int
    channel_id: int
    conversation_id: int
    external_message_id: str
    sender_external_id: str
    sender_name: str
    message_type: str
    text: str
    normalized_json: dict[str, Any]
    raw_json: dict[str, Any]
    received_at: datetime


class RelatedObjectRead(BaseModel):
    type: str
    id: int
    label: str


class MessageEventEnrichedRead(MessageEventRead):
    channel_label: Optional[str] = None
    sender_display_name: Optional[str] = None
    sender_short_id: Optional[str] = None
    conversation_display_name: Optional[str] = None
    conversation_short_id: Optional[str] = None
    message_type_label: Optional[str] = None
    traceable_non_text: bool = False
    non_text_summary: Optional[str] = None
    message_tracking: dict[str, Any] = Field(default_factory=dict)
    intent: Optional[str] = None
    target_agent: Optional[str] = None
    risk_level: Optional[str] = None
    confidence: Optional[float] = None
    agent_run_id: Optional[int] = None
    has_related_objects: bool = False
    related_objects: list[RelatedObjectRead] = Field(default_factory=list)


class AgentRunRead(ORMModel):
    id: int
    tenant_id: int
    message_id: Optional[int]
    agent_type: str
    status: str
    prompt_version: str
    prompt_json: dict[str, Any]
    model_provider: str
    model_name: str
    model_output_json: dict[str, Any]
    action_json: dict[str, Any]
    confidence: float
    risk_level: str
    latency_ms: int
    tokens_used: int
    cost_usd: float
    error_message: Optional[str]
    created_at: datetime


class ApprovalRead(ORMModel):
    id: int
    tenant_id: int
    agent_run_id: Optional[int]
    status: str
    draft_content: str
    final_content: Optional[str]
    operator_id: Optional[int]
    operated_at: Optional[datetime]
    sent_at: Optional[datetime]
    reject_reason: Optional[str]
    created_at: datetime


class ApprovalEnrichedRead(ApprovalRead):
    original_message: Optional[str] = None
    original_sender_name: Optional[str] = None
    original_sender_display_name: Optional[str] = None
    original_conversation_display_name: Optional[str] = None
    intent: Optional[str] = None
    target_agent: Optional[str] = None
    risk_level: Optional[str] = None
    confidence: Optional[float] = None
    action_type: str = "send_draft_to_approval"
    business_object_type: Optional[str] = None
    business_object_id: Optional[int] = None
    business_object_label: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_channel: Optional[str] = None
    delivery_mode: Optional[str] = None
    delivery_error: Optional[str] = None
    delivery_advice: Optional[str] = None
    delivery_chat_id: Optional[str] = None
    delivery_feishu_message_id: Optional[str] = None
    delivery_request_uuid: Optional[str] = None
    delivery_attempts: int = 0
    last_delivery_at: Optional[datetime] = None


class ApprovalUpdate(BaseModel):
    status: str = Field(pattern="^(pending_review|approved|edited|rejected|sent)$")
    final_content: Optional[str] = None
    operator_id: Optional[int] = None
    reject_reason: Optional[str] = None


class TicketRead(ORMModel):
    id: int
    tenant_id: int
    source_message_id: Optional[int]
    agent_run_id: Optional[int]
    title: str
    customer_name: str
    category: str
    priority: str
    status: str
    summary: str
    created_at: datetime
    updated_at: datetime


class TicketUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(open|in_progress|waiting_customer|resolved|closed)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")


class TicketKnowledgeCreate(BaseModel):
    mode: str = Field(default="gap", pattern="^(gap|item)$")
    category: str = "support"
    answer: Optional[str] = None
    publish: bool = False


class SlaConfigUpdate(BaseModel):
    critical: Optional[int] = Field(default=None, ge=1, le=240)
    high: Optional[int] = Field(default=None, ge=1, le=240)
    medium: Optional[int] = Field(default=None, ge=1, le=240)
    low: Optional[int] = Field(default=None, ge=1, le=240)


class LeadRead(ORMModel):
    id: int
    tenant_id: int
    source_message_id: Optional[int]
    agent_run_id: Optional[int]
    customer_name: str
    company: Optional[str]
    interest: str
    stage: str
    score: int
    priority: str
    summary: str
    next_step: str
    created_at: datetime
    updated_at: datetime


class LeadUpdate(BaseModel):
    stage: Optional[str] = Field(default=None, pattern="^(new|potential|contacted|qualified|proposal|negotiation|won|lost)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    next_step: Optional[str] = None


class LeadApprovalDraftCreate(BaseModel):
    draft_content: Optional[str] = None
    next_step: Optional[str] = None


class FollowupTaskRead(ORMModel):
    id: int
    tenant_id: int
    source_message_id: Optional[int]
    agent_run_id: Optional[int]
    title: str
    task_type: str
    status: str
    priority: str
    related_object_type: Optional[str]
    related_object_id: Optional[int]
    assignee_user_id: Optional[int]
    assignee_username: Optional[str]
    assignee_name: Optional[str]
    assignee_user: Optional[LocalUserSummary] = None
    due_hint: Optional[str]
    due_at: Optional[datetime]
    is_overdue: bool = False
    summary: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class FollowupTaskUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(todo|in_progress|waiting|done|cancelled)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    due_hint: Optional[str] = None
    due_at: Optional[datetime] = None
    summary: Optional[str] = None


class ProcessingRecordRead(ORMModel):
    id: int
    tenant_id: int
    object_type: str
    object_id: int
    action_type: str
    status: Optional[str]
    assignee_user_id: Optional[int]
    assignee_username: Optional[str]
    assignee_name: Optional[str]
    assignee_user: Optional[LocalUserSummary] = None
    due_hint: Optional[str]
    due_at: Optional[datetime]
    next_step: Optional[str]
    note: str
    operator_user_id: Optional[int]
    operator_username: Optional[str]
    operator_name: str
    operator_user: Optional[LocalUserSummary] = None
    created_at: datetime


class ProcessingRecordCreate(BaseModel):
    action_type: str = Field(default="note", pattern="^(note|assign|status_change|next_step|complete|cancel)$")
    status: Optional[str] = None
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    due_hint: Optional[str] = None
    due_at: Optional[datetime] = None
    next_step: Optional[str] = None
    note: str = ""
    operator_name: Optional[str] = None


class AuditLogRead(ORMModel):
    id: int
    tenant_id: int
    action_type: str
    scope_type: str
    scope_id: Optional[int]
    object_type: Optional[str]
    object_id: Optional[int]
    operator_user_id: Optional[int]
    operator_username: Optional[str]
    operator_name: str
    status: Optional[str]
    summary: str
    detail_json: dict[str, Any]
    created_at: datetime
    operator_user: Optional[LocalUserSummary] = None


class WorkbenchSummary(BaseModel):
    current_user: LocalUserSummary
    summary: dict[str, int]
    my_tasks: list[FollowupTaskRead]
    my_overdue_tasks: list[FollowupTaskRead]
    unassigned_tasks: list[FollowupTaskRead]
    my_pending_approvals: list[ApprovalEnrichedRead]
    recent_activity: list[AuditLogRead]


class CandidateRead(ORMModel):
    id: int
    tenant_id: int
    source_message_id: Optional[int]
    agent_run_id: Optional[int]
    name: str
    role: str
    stage: str
    match_score: int
    summary: str
    interview_questions_json: list[dict[str, Any]]
    onboarding_checklist_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class CandidateUpdate(BaseModel):
    stage: Optional[str] = Field(default=None, pattern="^(screening|interview|offer|onboarding|hired|rejected)$")
    match_score: Optional[int] = Field(default=None, ge=0, le=100)
    summary: Optional[str] = None


class CandidateChecklistUpdate(BaseModel):
    completed: bool


class KnowledgeGapRead(ORMModel):
    id: int
    tenant_id: int
    source_message_id: Optional[int]
    agent_run_id: Optional[int]
    question: str
    suggested_answer: str
    category: str
    occurrence_count: int
    status: str
    examples_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class KnowledgeItemRead(ORMModel):
    id: int
    tenant_id: int
    source_gap_id: Optional[int]
    title: str
    answer: str
    category: str
    status: str
    review_due_at: Optional[datetime]
    last_reviewed_at: Optional[datetime]
    quality_status: str
    quality_score: int
    created_at: datetime
    updated_at: datetime


class KnowledgeItemUpdate(BaseModel):
    title: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|pending_review|published|archived)$")
    change_summary: Optional[str] = None
    review_due_at: Optional[datetime] = None
    last_reviewed_at: Optional[datetime] = None
    quality_status: Optional[str] = Field(default=None, pattern="^(healthy|needs_review|expired|needs_optimization|archive_suggested)$")
    quality_score: Optional[int] = Field(default=None, ge=0, le=100)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    category: Optional[str] = None
    limit: int = Field(default=8, ge=1, le=30)
    include_drafts: bool = False
    record_hit: bool = True
    source_object_type: str = Field(default="manual_search", max_length=50)
    source_object_id: Optional[int] = None


class KnowledgeSearchMatch(BaseModel):
    item: KnowledgeItemRead
    score: int
    keyword_score: int
    semantic_score: float
    quality_score: int
    retrieval_mode: str = "hybrid"
    reasons: list[str]
    snippet: str
    citation: str
    source_reference: dict[str, Any]
    recorded_hit_id: Optional[int] = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    total_candidates: int
    matches: list[KnowledgeSearchMatch]


class KnowledgeVersionRollbackRequest(BaseModel):
    change_summary: Optional[str] = Field(default=None, max_length=500)


class KnowledgeHitFeedbackRequest(BaseModel):
    status: str = Field(pattern="^(useful|not_useful)$")
    note: Optional[str] = Field(default=None, max_length=500)


class ReportRead(ORMModel):
    id: int
    tenant_id: int
    agent_run_id: Optional[int]
    report_type: str
    scope_type: str
    scope_id: Optional[str]
    title: str
    summary: str
    metrics_json: dict[str, Any]
    sections_json: list[dict[str, Any]]
    source_message_ids: list[int]
    created_at: datetime


class ImportRecord(BaseModel):
    text: str
    sender_name: str = "未知用户"
    sender_external_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    conversation_id: str = "demo-conversation"
    conversation_name: str = "Demo Conversation"
    conversation_type: str = "group"
    channel: str = "local_json"
    message_type: str = "text"
    external_message_id: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class JSONImportRequest(BaseModel):
    source: str = "json"
    records: list[ImportRecord]


class RawImportRequest(BaseModel):
    source_type: str = Field(default="json", pattern="^(csv|json|text)$")
    filename: Optional[str] = None
    content: str


class KnowledgeImportRequest(BaseModel):
    source_type: str = Field(default="markdown", pattern="^(markdown|faq|csv)$")
    filename: Optional[str] = None
    content: str
    default_category: str = "general"
    default_mode: str = Field(default="item", pattern="^(item|gap)$")
    publish: bool = False


class KnowledgeImportPreviewRow(BaseModel):
    row_index: int
    mode: str
    title: str
    question: str
    answer: str
    category: str
    status: str
    source_excerpt: str
    warnings: list[str] = []


class KnowledgeImportPreviewResult(BaseModel):
    source_type: str
    filename: Optional[str]
    total_rows: int
    rows: list[KnowledgeImportPreviewRow]
    warnings: list[str] = []


class KnowledgeImportConfirmResult(BaseModel):
    batch: "ImportBatchRead"
    created_items: list[KnowledgeItemRead]
    created_gaps: list[KnowledgeGapRead]
    preview: KnowledgeImportPreviewResult


class ImportBatchRead(ORMModel):
    id: int
    tenant_id: int
    source: str
    filename: Optional[str]
    status: str
    total_rows: int
    imported_count: int
    skipped_count: int
    error_count: int
    metadata_json: dict[str, Any]
    created_at: datetime
    completed_at: Optional[datetime]


class ImportResult(BaseModel):
    batch: ImportBatchRead
    messages: list[MessageEventRead]


class DashboardSummary(BaseModel):
    messages: int
    tickets: int
    leads: int
    approvals_pending: int
    agent_runs: int
    today_imports: int = 0


class FrontendDashboardSummary(BaseModel):
    message_count: int
    pending_approval_count: int
    ticket_count: int
    lead_count: int
    task_count: int = 0
    candidate_count: int = 0
    knowledge_gap_count: int = 0
    knowledge_item_count: int = 0
    report_count: int = 0
    agent_run_count: int
    today_import_count: int = 0


class DemoResetResult(BaseModel):
    deleted: dict[str, int]
    imported_batches: list[ImportBatchRead]
    message_count: int
    ticket_count: int
    lead_count: int
    task_count: int
    approval_count: int
    agent_run_count: int
