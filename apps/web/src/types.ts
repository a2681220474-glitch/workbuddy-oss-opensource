export type EntityId = string | number;

export interface LocalUser {
  id: EntityId;
  tenant_id?: EntityId;
  username?: string;
  display_name?: string;
  role?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AuthBootstrapStatus {
  needs_bootstrap?: boolean;
  password_user_count?: number;
  active_user_count?: number;
  bootstrap_username?: string;
}

export interface AuthSession {
  status?: string;
  user?: LocalUser;
}

export interface LocalUserSummary {
  id: EntityId;
  username?: string;
  display_name?: string;
  role?: string;
  status?: string;
}

export interface MessageEvent {
  id?: EntityId;
  event_id?: string;
  tenant_id?: string;
  channel?: string;
  conversation_id?: string;
  conversation_type?: string;
  sender_id?: string;
  sender_name?: string;
  message_id?: string;
  message_type?: string;
  text?: string;
  timestamp?: string;
  intent?: string;
  target_agent?: string;
  risk_level?: string;
  confidence?: number;
  agent_run_id?: EntityId;
  related_objects?: RelatedObject[];
  created_at?: string;
  received_at?: string;
  normalized_json?: Record<string, unknown>;
  raw_json?: Record<string, unknown>;
  channel_label?: string;
  sender_display_name?: string;
  sender_short_id?: string;
  conversation_display_name?: string;
  conversation_short_id?: string;
  message_type_label?: string;
  traceable_non_text?: boolean;
  non_text_summary?: string;
  message_tracking?: Record<string, unknown>;
  has_related_objects?: boolean;
}

export interface RelatedObject {
  type: string;
  id: EntityId;
  label: string;
}

export interface MessageRerunResult {
  message_id?: EntityId;
  replayed_from_run_id?: EntityId;
  agent_run_id?: EntityId;
  approval_count?: number;
  target_agent?: string;
  intent?: string;
  confidence?: number;
  risk_level?: string;
  cleaned?: Record<string, number>;
  related_objects?: RelatedObject[];
  before?: ReplaySnapshot;
  after?: ReplaySnapshot;
  changed?: Record<string, boolean>;
}

export interface ReplaySnapshot {
  agent_run_id?: EntityId;
  target_agent?: string;
  intent?: string;
  confidence?: number;
  risk_level?: string;
  reason?: string;
  related_objects?: RelatedObject[];
}

export interface Ticket {
  id: EntityId;
  title?: string;
  customer_name?: string;
  category?: string;
  status?: string;
  priority?: string;
  source_message_id?: EntityId;
  summary?: string;
  created_at?: string;
  updated_at?: string;
}

export interface TicketWorkflow {
  statuses?: Array<{
    value: string;
    label: string;
    next: string[];
  }>;
  transitions?: Record<string, string[]>;
  sla_hours?: Record<string, number>;
}

export interface TicketKnowledgeSuggestion {
  ticket_id?: EntityId;
  status?: "hit" | "miss" | string;
  matches?: Array<{
    id?: EntityId;
    title?: string;
    category?: string;
    score?: number;
    answer?: string;
  }>;
  suggested_question?: string;
  suggested_answer?: string;
}

export interface Lead {
  id: EntityId;
  customer_name?: string;
  company?: string;
  interest?: string;
  stage?: string;
  score?: number;
  priority?: string;
  next_step?: string;
  source_message_id?: EntityId;
  created_at?: string;
  updated_at?: string;
}

export interface LeadWorkflow {
  stages?: Array<{
    value: string;
    label: string;
    next: string[];
  }>;
  transitions?: Record<string, string[]>;
  score_dimensions?: string[];
}

export interface LeadScorecard {
  lead_id?: EntityId;
  score?: number;
  computed_score?: number;
  dimensions?: Record<string, number>;
  reasons?: string[];
  priority?: string;
  stalled?: boolean;
}

export interface LeadDraft {
  lead_id?: EntityId;
  draft_content?: string;
  next_step?: string;
  requires_approval?: boolean;
  recommended_stage?: string;
  scorecard?: LeadScorecard;
}

export interface CommunityOverview {
  summary?: {
    community_messages?: number;
    community_conversations?: number;
    high_intent_users?: number;
    unanswered_questions?: number;
    risk_messages?: number;
    open_tasks?: number;
  };
  conversations?: Array<{
    conversation_id?: EntityId;
    name?: string;
    message_count?: number;
    high_intent_count?: number;
    unanswered_count?: number;
    risk_count?: number;
    open_task_count?: number;
    latest_message?: string;
    latest_at?: string;
    activity_score?: number;
  }>;
  high_intent_users?: Array<{
    id?: EntityId;
    customer_name?: string;
    interest?: string;
    score?: number;
    stage?: string;
    next_step?: string;
    source_message_id?: EntityId;
  }>;
  unanswered_questions?: Array<{
    id?: EntityId;
    question?: string;
    suggested_answer?: string;
    status?: string;
    occurrence_count?: number;
    source_message_id?: EntityId;
  }>;
  risk_messages?: Array<{
    id?: EntityId;
    sender_name?: string;
    text?: string;
    conversation_id?: EntityId;
    conversation_name?: string;
    received_at?: string;
    risk_level?: string;
  }>;
  tasks?: Array<{
    id?: EntityId;
    title?: string;
    status?: string;
    priority?: string;
    due_hint?: string;
    summary?: string;
    source_message_id?: EntityId;
    related_object_type?: string;
    related_object_id?: EntityId;
    created_at?: string;
    updated_at?: string;
    completed_at?: string;
  }>;
}

export interface Approval {
  id: EntityId;
  status?: string;
  action_type?: string;
  target_channel?: string;
  original_message?: string;
  original_sender_name?: string;
  original_sender_display_name?: string;
  original_conversation_display_name?: string;
  intent?: string;
  target_agent?: string;
  risk_level?: string;
  confidence?: number;
  draft_content?: string;
  final_content?: string;
  business_object_type?: string;
  business_object_id?: EntityId;
  business_object_label?: string;
  delivery_status?: string;
  delivery_channel?: string;
  delivery_mode?: string;
  delivery_error?: string;
  delivery_advice?: string;
  delivery_chat_id?: string;
  delivery_feishu_message_id?: string;
  delivery_request_uuid?: string;
  delivery_attempts?: number;
  last_delivery_at?: string;
  agent_run_id?: EntityId;
  created_at?: string;
  updated_at?: string;
}

export interface ApprovalSendPreview {
  sendable?: boolean;
  mode?: "real" | "mock" | "disabled" | "blocked" | "sent" | "retry_wait" | "retry_limit" | string;
  channel?: string | null;
  severity?: "info" | "warning" | "error" | string;
  title?: string;
  message?: string;
  policy?: Record<string, unknown>;
  content_preview?: string;
  delivery_attempts?: number;
  previous_delivery_status?: string | null;
  max_delivery_attempts?: number;
  retry_allowed?: boolean;
  retry_after_seconds?: number;
  next_retry_at?: string | null;
  next_attempt?: number | null;
  retry_title?: string;
  retry_message?: string;
}

export interface ApprovalCardPreview {
  sendable?: boolean;
  config_ready?: boolean;
  mode?: string;
  target_chat_id?: string | null;
  missing?: string[];
  card?: Record<string, unknown>;
  send_preview?: ApprovalSendPreview;
}

export interface ApprovalDeliveryHistoryItem {
  id?: EntityId;
  status?: string;
  channel?: string;
  mode?: string;
  chat_id?: string;
  target_type?: string;
  target_id?: string;
  feishu_message_id?: string;
  request_uuid?: string;
  error?: string;
  advice?: string;
  attempt?: number;
  created_at?: string;
}

export interface ApprovalCardHistoryItem {
  id?: EntityId;
  status?: string;
  mode?: string;
  chat_id?: string;
  request_uuid?: string;
  decision?: string;
  callback?: boolean;
  event_id?: string;
  toast?: string;
  error?: string;
  created_at?: string;
}

export interface FollowupTask {
  id: EntityId;
  title?: string;
  task_type?: string;
  status?: string;
  priority?: string;
  related_object_type?: string;
  related_object_id?: EntityId;
  assignee_user_id?: EntityId;
  assignee_username?: string;
  assignee_name?: string;
  assignee_user?: LocalUserSummary | null;
  due_hint?: string;
  due_at?: string;
  summary?: string;
  source_message_id?: EntityId;
  agent_run_id?: EntityId;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  is_overdue?: boolean;
}

export interface ProcessingRecord {
  id?: EntityId;
  object_type?: string;
  object_id?: EntityId;
  action_type?: string;
  status?: string;
  assignee_user_id?: EntityId;
  assignee_username?: string;
  assignee_name?: string;
  assignee_user?: LocalUserSummary | null;
  due_hint?: string;
  due_at?: string;
  next_step?: string;
  note?: string;
  operator_user_id?: EntityId;
  operator_username?: string;
  operator_name?: string;
  operator_user?: LocalUserSummary | null;
  created_at?: string;
}

export interface AuditLog {
  id?: EntityId;
  tenant_id?: EntityId;
  action_type?: string;
  scope_type?: string;
  scope_id?: EntityId;
  object_type?: string;
  object_id?: EntityId;
  operator_user_id?: EntityId;
  operator_username?: string;
  operator_name?: string;
  operator_user?: LocalUserSummary | null;
  status?: string;
  summary?: string;
  detail_json?: Record<string, unknown>;
  created_at?: string;
}

export interface BusinessObjectTimelineItem {
  key?: string;
  type?: string;
  title?: string;
  description?: string;
  created_at?: string;
  target?: {
    type?: string;
    id?: EntityId;
  };
  metadata?: Record<string, unknown>;
}

export interface AgentDefinition {
  name?: string;
  responsibility?: string;
  inputs?: string[];
  outputs?: string[];
  llm_usage?: string;
  failure_handling?: string;
  approval_policy?: string;
}

export interface BusinessObjectDetail {
  object_type?: string;
  object_id?: EntityId;
  label?: string;
  object?: Record<string, unknown>;
  source_message?: MessageEvent | null;
  agent_run?: AgentRun | null;
  agent_definition?: AgentDefinition;
  approvals?: Approval[];
  processing_records?: ProcessingRecord[];
  related_objects?: RelatedObject[];
  timeline?: BusinessObjectTimelineItem[];
}

export interface ApprovalContext {
  approval?: Approval;
  business_object?: BusinessObjectDetail | null;
  knowledge_references?: Array<{
    type?: string;
    id?: EntityId;
    title?: string;
    category?: string;
    score?: number;
    reasons?: string[];
    snippet?: string;
    hit_id?: EntityId;
  }>;
  send_preview?: ApprovalSendPreview;
  delivery_history?: ApprovalDeliveryHistoryItem[];
  card_preview?: ApprovalCardPreview;
  card_history?: ApprovalCardHistoryItem[];
}

export interface Candidate {
  id: EntityId;
  source_message_id?: EntityId;
  agent_run_id?: EntityId;
  name?: string;
  role?: string;
  stage?: string;
  match_score?: number;
  summary?: string;
  interview_questions_json?: Array<Record<string, unknown>>;
  onboarding_checklist_json?: Array<Record<string, unknown>>;
  created_at?: string;
  updated_at?: string;
}

export interface CandidateWorkflow {
  stages?: Array<{ value: string; label: string; next?: string[] }>;
  transitions?: Record<string, string[]>;
}

export interface CandidateMatchAnalysis {
  candidate_id?: EntityId;
  score?: number;
  role?: string;
  stage?: string;
  dimensions?: Record<string, number>;
  strengths?: string[];
  risks?: string[];
  gaps?: string[];
  recommendation?: string;
  interview_questions?: Array<Record<string, unknown>>;
  onboarding_checklist?: Array<Record<string, unknown>>;
}

export interface KnowledgeGap {
  id: EntityId;
  source_message_id?: EntityId;
  agent_run_id?: EntityId;
  question?: string;
  suggested_answer?: string;
  category?: string;
  occurrence_count?: number;
  status?: string;
  examples_json?: Array<Record<string, unknown>>;
  created_at?: string;
  updated_at?: string;
}

export interface KnowledgeItem {
  id: EntityId;
  source_gap_id?: EntityId;
  title?: string;
  answer?: string;
  category?: string;
  status?: string;
  review_due_at?: string | null;
  last_reviewed_at?: string | null;
  quality_status?: string;
  quality_score?: number;
  created_at?: string;
  updated_at?: string;
}

export interface KnowledgeSourceReference {
  type?: string;
  id?: EntityId;
  label?: string;
  summary?: string;
  created_at?: string | null;
}

export interface KnowledgeItemVersion {
  id?: EntityId | null;
  item_id?: EntityId;
  version_no?: number;
  title?: string;
  answer?: string;
  category?: string;
  status?: string;
  change_type?: string;
  change_summary?: string;
  created_at?: string;
}

export interface KnowledgeHit {
  id?: EntityId;
  item_id?: EntityId;
  source_object_type?: string;
  source_object_id?: EntityId;
  query_text?: string;
  score?: number;
  answer_snapshot?: string;
  status?: string;
  created_at?: string;
}

export interface KnowledgeGraphNode {
  id: string;
  kind: string;
  label: string;
  object_type?: string;
  object_id?: EntityId;
  status?: string;
  category?: string;
  summary?: string;
  score?: number;
  created_at?: string;
}

export interface KnowledgeGraphEdge {
  id: string;
  source: string;
  target: string;
  type: "source_of" | "created_from" | "hit_by" | "same_category" | "version_of" | string;
  label?: string;
}

export interface KnowledgeGraphResponse {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  summary?: {
    node_count?: number;
    edge_count?: number;
    knowledge_items?: number;
    knowledge_gaps?: number;
    hits?: number;
  };
}

export interface KnowledgeObsidianExportFile {
  path: string;
  content: string;
}

export interface KnowledgeObsidianExport {
  format?: string;
  file_count?: number;
  files: KnowledgeObsidianExportFile[];
}

export interface KnowledgeQualityItem {
  item: KnowledgeItem;
  hit_count?: number;
  average_hit_score?: number;
  computed_quality_status?: string;
  reason?: string;
}

export interface KnowledgeQualityDashboard {
  summary?: {
    total_items?: number;
    published_items?: number;
    expired_items?: number;
    review_due_soon?: number;
    optimization_candidates?: number;
    archive_suggestions?: number;
    pending_gaps?: number;
    repeated_gaps?: number;
    average_quality_score?: number;
  };
  expired_items?: KnowledgeQualityItem[];
  review_due_soon?: KnowledgeQualityItem[];
  optimization_candidates?: KnowledgeQualityItem[];
  archive_suggestions?: KnowledgeQualityItem[];
  gap_quality?: {
    pending_gaps?: KnowledgeGap[];
    repeated_gaps?: KnowledgeGap[];
  };
  items?: KnowledgeQualityItem[];
  rules?: Record<string, string>;
}

export interface KnowledgeSearchPayload {
  query: string;
  category?: string;
  limit?: number;
  include_drafts?: boolean;
  record_hit?: boolean;
  source_object_type?: string;
  source_object_id?: number;
}

export interface KnowledgeSearchMatch {
  item: KnowledgeItem;
  score: number;
  keyword_score?: number;
  semantic_score?: number;
  quality_score?: number;
  retrieval_mode?: string;
  reasons?: string[];
  snippet?: string;
  citation?: string;
  source_reference?: Record<string, unknown>;
  recorded_hit_id?: EntityId | null;
}

export interface KnowledgeSearchResponse {
  query: string;
  total_candidates: number;
  matches: KnowledgeSearchMatch[];
}

export interface KnowledgeTimelineEvent {
  type?: string;
  title?: string;
  description?: string;
  created_at?: string;
}

export interface KnowledgeGapDetail {
  type?: "knowledge_gap";
  gap?: KnowledgeGap;
  source_references?: KnowledgeSourceReference[];
  related_items?: KnowledgeItem[];
  processing_records?: Array<Record<string, unknown>>;
  timeline?: KnowledgeTimelineEvent[];
}

export interface KnowledgeItemDetail {
  type?: "knowledge_item";
  item?: KnowledgeItem;
  source_gap?: KnowledgeGap | null;
  source_references?: KnowledgeSourceReference[];
  versions?: KnowledgeItemVersion[];
  hit_summary?: {
    total?: number;
    latest_at?: string | null;
    average_score?: number;
  };
  hits?: KnowledgeHit[];
  processing_records?: Array<Record<string, unknown>>;
  timeline?: KnowledgeTimelineEvent[];
}

export interface Report {
  id: EntityId;
  agent_run_id?: EntityId;
  report_type?: string;
  scope_type?: string;
  scope_id?: string;
  title?: string;
  summary?: string;
  metrics_json?: Record<string, unknown>;
  sections_json?: Array<{
    title?: string;
    items?: string[];
  }>;
  source_message_ids?: EntityId[];
  created_at?: string;
}

export interface BusinessObjectCenter {
  counts?: Record<string, number>;
  recent?: Record<string, Array<{
    id?: EntityId;
    label?: string;
    created_at?: string;
  }>>;
}

export interface OperationsSummary {
  support?: {
    open_tickets?: number;
    high_priority_open_tickets?: number;
    stale_open_tickets?: number;
    next_ticket_ids?: EntityId[];
  };
  sales?: {
    funnel?: Record<string, number>;
    top_leads?: Array<{
      id?: EntityId;
      customer_name?: string;
      stage?: string;
      score?: number;
      next_step?: string;
    }>;
  };
  knowledge?: {
    pending_gaps?: number;
    accepted_gaps?: number;
    ignored_gaps?: number;
  };
  reports?: {
    total?: number;
    latest?: Array<{
      id?: EntityId;
      title?: string;
      report_type?: string;
    }>;
  };
  tasks?: {
    todo?: number;
    done?: number;
  };
  agent_overview?: Array<{
    agent_type?: string;
    label?: string;
    object_count?: number;
    pending_count?: number;
    risk_count?: number;
    approval_count?: number;
    report_count?: number;
    entry?: string;
  }>;
  risk_inbox?: {
    total?: number;
    support_risks?: EntityId[];
    sales_risks?: EntityId[];
    knowledge_risks?: EntityId[];
    approval_risks?: EntityId[];
  };
}

export interface WorkbenchSummary {
  current_user?: LocalUserSummary;
  summary?: Record<string, number>;
  my_tasks?: FollowupTask[];
  my_overdue_tasks?: FollowupTask[];
  unassigned_tasks?: FollowupTask[];
  my_pending_approvals?: Approval[];
  recent_activity?: AuditLog[];
}

export interface AgentRun {
  id: EntityId;
  tenant_id?: EntityId;
  agent_type?: string;
  agent_name?: string;
  target_agent?: string;
  intent?: string;
  status?: string;
  confidence?: number;
  model_provider?: string;
  model_name?: string;
  prompt_version?: string;
  latency_ms?: number;
  token_usage?: number;
  tokens_used?: number;
  cost_usd?: number;
  requires_approval?: boolean;
  input_text?: string;
  output_text?: string;
  message_id?: EntityId;
  risk_level?: string;
  error_message?: string;
  action_json?: unknown;
  model_output_json?: unknown;
  prompt_json?: unknown;
  created_at?: string;
}

export interface DashboardSummary {
  message_count?: number;
  pending_approval_count?: number;
  ticket_count?: number;
  lead_count?: number;
  task_count?: number;
  candidate_count?: number;
  knowledge_gap_count?: number;
  knowledge_item_count?: number;
  report_count?: number;
  agent_run_count?: number;
  today_import_count?: number;
}

export interface FeishuStatus {
  channel?: string;
  configured?: boolean;
  real_im_adapters_enabled?: boolean;
  external_send_enabled?: boolean;
  send_mode?: "mock" | "real" | string;
  stream_worker?: {
    status?: string;
    running?: boolean;
    updated_at?: string;
    last_heartbeat_at?: string;
    seconds_since_heartbeat?: number;
    heartbeat_count?: number;
    health_level?: string;
    health_message?: string;
    receiving_real_messages?: boolean;
    last_success_at?: string;
    last_failure_at?: string;
    last_error?: string;
    recent_events?: Array<Record<string, unknown>>;
    recent_errors?: Array<Record<string, unknown>>;
    run_command?: string;
    compose_command?: string;
    check_command?: string;
    recovery_steps?: string[];
    app_id?: string;
    note?: string;
  };
  recent?: {
    last_event?: Record<string, unknown> | null;
    last_message?: Record<string, unknown> | null;
    last_send?: Record<string, unknown> | null;
  };
  production_readiness?: FeishuProductionReadiness;
}

export interface FeishuProductionReadiness {
  ready?: boolean;
  receive_ready?: boolean;
  send_ready?: boolean;
  blocking_failed?: number;
  warning_failed?: number;
  checks?: Array<{
    key?: string;
    label?: string;
    ok?: boolean;
    status?: string;
    severity?: string;
    message?: string;
  }>;
  acceptance_steps?: string[];
}

export interface FeishuConversation {
  id: EntityId;
  channel?: string;
  name?: string;
  type?: string;
  external_conversation_id?: string;
  short_id?: string;
  bound_agent?: string;
  send_mode?: string;
  last_message_at?: string;
  created_at?: string;
  message_count?: number;
  latest_message?: {
    id?: EntityId;
    text?: string;
    sender_name?: string;
    received_at?: string;
  } | null;
}

export interface DemoPrepareResult {
  status?: string;
  deleted_local_demo?: Record<string, number>;
  imported_batches?: Array<Record<string, unknown>>;
  created_from_import?: Record<string, number>;
  business_object_counts?: Record<string, number>;
  business_object_total?: number;
  promoted_knowledge_items?: Array<{
    gap_id?: EntityId;
    item_id?: EntityId;
    title?: string;
  }>;
  generated_reports?: Array<{
    id?: EntityId;
    report_type?: string;
    title?: string;
  }>;
  validation_report?: {
    title?: string;
    passed?: number;
    total?: number;
    ready_for_beta?: boolean;
    checks?: Array<{
      key?: string;
      label?: string;
      status?: string;
      detail?: string;
    }>;
  };
  restored_conversations?: Array<{
    id?: EntityId;
    name?: string;
    bound_agent?: string;
    send_mode?: string;
  }>;
  next_message?: string;
  recommended_flow?: Array<{
    label?: string;
    target?: string;
  }>;
}

export interface ConfigStatus {
  app?: {
    name?: string;
    environment?: string;
    database?: string;
    database_backend?: string;
    database_persistence?: string;
    database_connected?: boolean;
    redis_configured?: boolean;
    redis_connected?: boolean;
    deployment_mode?: string;
  };
  llm?: {
    provider?: string;
    model?: string;
    base_url?: string;
    mode?: string;
    configured?: boolean;
    real_configured?: boolean;
    base_url_configured?: boolean;
    api_key_configured?: boolean;
    timeout_seconds?: number;
    supported_providers?: string[];
    config_keys?: string[];
  };
  global_policy?: {
    enable_real_im_adapters?: boolean;
    enable_external_send?: boolean;
    enable_background_jobs?: boolean;
    background_queue_driver?: string;
    default_send_mode?: string;
    effective_send_mode?: string;
    real_send_requires_env?: boolean;
  };
  runtime_stack?: {
    status?: string;
    timezone?: string;
    database?: {
      backend?: string;
      label?: string;
      configured?: boolean;
      url_masked?: string;
      persistence?: string;
      connected?: boolean;
      status?: string;
      advice?: string | null;
      error?: string;
    };
    backup?: {
      backend?: string;
      backup_dir?: string;
      ready?: boolean;
      status?: string;
      latest_backup?: string | null;
      latest_backup_size_bytes?: number | null;
      create_command?: string;
      verify_command?: string;
      restore_plan_command?: string;
      restore_sqlite_command?: string;
      advice?: string;
    };
    redis?: {
      configured?: boolean;
      connected?: boolean;
      status?: string;
      url_masked?: string;
      advice?: string | null;
      error?: string;
      host?: string;
      port?: number;
      db?: string;
    };
    background_jobs?: {
      enabled?: boolean;
      queue_driver?: string;
      ready?: boolean;
      status?: string;
      dependency_ready?: boolean;
      advice?: string;
      scheduled_jobs?: string[];
      worker?: Record<string, unknown>;
    };
    logs?: {
      log_dir?: string;
      ready?: boolean;
      files?: Array<{
        name?: string;
        path?: string;
        size_bytes?: number;
        updated_at?: string;
      }>;
      tail_command?: string;
      check_command?: string;
      advice?: string;
    };
    deployment?: {
      mode?: string;
      compose_services?: string[];
      compose_up_command?: string;
      compose_api_command?: string;
      local_api_command?: string;
      local_web_command?: string;
      local_feishu_worker_command?: string;
      local_runtime_jobs_command?: string;
      backup_create_command?: string;
      backup_verify_command?: string;
      backup_restore_plan_command?: string;
      logs_tail_command?: string;
      logs_check_command?: string;
    };
  };
  release_audit?: ReleaseAudit;
  secret_storage?: SecretStorageStatus;
  channels?: ChannelStatus[];
}

export interface ReleaseAudit {
  version?: string;
  status?: string;
  local_code_ready?: boolean;
  formal_private_use_ready?: boolean;
  summary?: {
    total?: number;
    completed?: number;
    manual_required?: number;
    deployment_required?: number;
    local_gaps?: number;
  };
  baselines?: Array<{
    number?: number;
    title?: string;
    status?: string;
    status_label?: string;
    detail?: string;
    target?: string;
  }>;
  stop_development?: {
    phase_one?: {
      label?: string;
      status?: string;
      local_code_ready?: boolean;
      message?: string;
    };
    phase_two?: {
      label?: string;
      status?: string;
      message?: string;
    };
  };
  runtime_boundary?: {
    environment?: string;
    database_backend?: string;
    redis_connected?: boolean;
    background_jobs_ready?: boolean;
    secret_storage_healthy?: boolean;
    remote_ecs_deployed_version?: string;
  };
  connector_evidence?: {
    historical_receive_events?: Record<string, number>;
    historical_real_sends?: Record<string, number>;
    new_real_validation_completed?: boolean;
    new_real_validation_requires_authorization?: boolean;
    validated_at?: string;
    validated_version?: string;
    validated_items?: string[];
  };
  deployment_evidence?: {
    postgres_restore_drill_completed?: boolean;
    completed_at?: string;
    backup_size_bytes?: number;
    backup_sha256?: string;
    restored_public_tables?: number;
    restored_messages?: number;
    restored_approvals?: number;
    alembic_version?: string;
    temporary_database_removed?: boolean;
  };
  formal_closure?: {
    status?: string;
    label?: string;
    aggregate_check_command?: string;
    release_track?: string;
    message?: string;
    maintenance_boundary?: {
      mode?: string;
      allowed_changes?: string[];
      blocked_changes?: string[];
      requires_authorization?: string[];
    };
  };
  next_actions?: string[];
}

export interface SecretStorageStatus {
  backend?: string;
  store_path?: string;
  key_path?: string;
  store_exists?: boolean;
  key_exists?: boolean;
  key_file_mode?: string | null;
  key_permissions_secure?: boolean;
  encrypted_key_count?: number;
  encrypted_keys?: string[];
  plaintext_key_count?: number;
  plaintext_keys?: string[];
  migration_required?: boolean;
  healthy?: boolean;
  error?: string | null;
}

export interface SecretStorageOperationResult {
  status?: string;
  migrated_keys?: string[];
  rotated_keys?: string[];
  backup_path?: string | null;
  secrets_masked?: boolean;
  secret_storage?: SecretStorageStatus;
}

export interface SafeDemoModeResult {
  status?: string;
  default_send_mode?: string;
  updated_conversation_count?: number;
  effective_send_mode?: string;
  notes?: string[];
}

export interface ChannelStatus {
  channel?: string;
  label?: string;
  configured?: boolean;
  adapter_status?: string;
  real_adapter_enabled?: boolean;
  external_send_enabled?: boolean;
  worker?: Record<string, unknown> | null;
  recent?: FeishuStatus["recent"] | null;
  capabilities?: Record<string, boolean | string>;
  config_keys?: string[];
  webhook_path?: string;
  setup_status?: string;
  runtime_values?: Record<string, string | boolean | number | undefined>;
}

export interface RuntimeConfigSaveResult {
  status?: string;
  settings_file?: string;
  saved_keys?: string[];
  secrets_masked?: boolean;
  api_reloaded?: boolean;
  restart_hint?: string;
}

export interface LLMSmokeTestResult {
  ok?: boolean;
  provider?: string;
  model?: string;
  mode?: string;
  latency_ms?: number;
  message?: string;
  error?: string;
  error_type?: string;
  advice?: string;
  finish_reason?: string;
  base_url_configured?: boolean;
  api_key_configured?: boolean;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  certificate?: {
    certifi_available?: boolean;
    ca_bundle?: string | null;
    advice?: string;
  };
}

export interface FeishuDiagnostics {
  configured?: boolean;
  external_send_enabled?: boolean;
  send_mode?: "mock" | "real" | string;
  api_base_url?: string;
  public_base_url?: string;
  webhook_path?: string;
  card_callback?: {
    ready?: boolean;
    status?: string;
    webhook_path?: string;
    public_base_url?: string;
    callback_url?: string | null;
    diagnosis?: string;
    feishu_error_when_offline?: string;
    requirements?: string[];
    next_steps?: string[];
  };
  checks?: Record<string, string>;
  token?: {
    checked?: boolean;
    status?: string;
    masked?: string;
    error?: string;
    code?: string | number;
    advice?: string;
  };
  send_requirements?: string[];
  stream_worker?: FeishuStatus["stream_worker"] & Record<string, unknown>;
  recent?: FeishuStatus["recent"];
  recent_channel_events?: FeishuChannelEvent[];
  recent_agent_runs?: FeishuAgentRun[];
  business_trace?: FeishuBusinessTrace;
  acceptance_traces?: FeishuAcceptanceTrace[];
  acceptance_summary?: {
    total?: number;
    complete?: number;
    ready?: number;
    needs_attention?: number;
  };
  receive_requirements?: string[];
  card_callback_requirements?: string[];
  production_notes?: string[];
  production_readiness?: FeishuProductionReadiness;
  safe_acceptance?: ConnectorSafeAcceptance;
}

export interface WeComDiagnostics {
  configured?: boolean;
  external_send_enabled?: boolean;
  send_mode?: "mock" | "real" | string;
  webhook_path?: string;
  callback_mode?: string;
  checks?: Record<string, string>;
  token?: {
    checked?: boolean;
    status?: string;
    masked?: string;
    error?: string;
    code?: string | number;
    advice?: string;
  };
  recent?: FeishuStatus["recent"];
  recent_channel_events?: FeishuChannelEvent[];
  recent_agent_runs?: FeishuAgentRun[];
  business_trace?: FeishuBusinessTrace;
  acceptance_traces?: FeishuAcceptanceTrace[];
  acceptance_summary?: {
    total?: number;
    complete?: number;
    ready?: number;
    needs_attention?: number;
  };
  callback_requirements?: string[];
  send_requirements?: string[];
  production_notes?: string[];
  production_readiness?: FeishuProductionReadiness;
  safe_acceptance?: ConnectorSafeAcceptance;
}

export interface ConnectorSafeAcceptance {
  status?: "safe_verified" | "needs_attention" | string;
  safe_verified?: boolean;
  automated_real_send?: boolean;
  real_send_requires_manual_authorization?: boolean;
  authorization_phrase?: string;
  real_send_evidence?: {
    agent_run_id?: EntityId;
    status?: string;
    created_at?: string;
  } | null;
  checks?: Array<{
    key: string;
    label: string;
    ok?: boolean;
    status?: string;
    message?: string;
  }>;
  next_action?: string;
}

export interface FeishuChannelEvent {
  id?: EntityId;
  channel_type?: string;
  channel_label?: string;
  event_type?: string;
  external_event_id?: string;
  status?: string;
  conversation_external_id?: string;
  actor_external_id?: string;
  created_at?: string;
  raw_json?: Record<string, unknown>;
  links?: {
    message_id?: EntityId | null;
    conversation_id?: EntityId | null;
    agent_run_ids?: EntityId[];
  };
  related_message?: {
    id?: EntityId;
    text?: string;
    sender_name?: string;
    received_at?: string;
  } | null;
  related_conversation?: {
    id?: EntityId;
    name?: string;
    external_conversation_id?: string;
  } | null;
  related_agent_runs?: Array<{
    id?: EntityId;
    agent_type?: string;
    status?: string;
    created_at?: string;
  }>;
  retry?: {
    retryable?: boolean;
    attempts?: number;
    next_attempt?: number;
    reason?: string | null;
  };
}

export interface FeishuAgentRun {
  id?: EntityId;
  message_id?: EntityId;
  agent_type?: string;
  status?: string;
  risk_level?: string;
  confidence?: number;
  error_message?: string;
  prompt_json?: Record<string, unknown>;
  model_output_json?: Record<string, unknown>;
  action_json?: Record<string, unknown>;
  links?: {
    message_id?: EntityId;
    approval_id?: EntityId;
    lead_id?: EntityId;
    ticket_id?: EntityId;
    task_id?: EntityId;
  };
  created_at?: string;
}

export interface FeishuBusinessTrace {
  message?: {
    id?: EntityId;
    sender_name?: string;
    text?: string;
    received_at?: string;
  } | null;
  conversation?: {
    id?: EntityId;
    name?: string;
    type?: string;
    external_conversation_id?: string;
    bound_agent?: string;
    send_mode?: string;
  } | null;
  agent_run?: FeishuAgentRun | null;
  business_objects?: Array<{
    type?: string;
    id?: EntityId;
    label?: string;
    target?: string;
  }>;
  approvals?: Array<{
    id?: EntityId;
    status?: string;
    label?: string;
    created_at?: string;
  }>;
  send_run?: FeishuAgentRun | null;
}

export interface FeishuAcceptanceTrace {
  message?: {
    id?: EntityId;
    sender_name?: string;
    sender_external_id?: string;
    text?: string;
    message_type?: string;
    message_type_label?: string;
    traceable_non_text?: boolean;
    received_at?: string;
  } | null;
  message_tracking?: {
    message_type?: string;
    message_type_label?: string;
    traceable_non_text?: boolean;
    summary?: string;
    details?: Record<string, unknown>;
  };
  conversation?: FeishuBusinessTrace["conversation"];
  agent_run?: FeishuAgentRun | null;
  business_objects?: FeishuBusinessTrace["business_objects"];
  approvals?: FeishuBusinessTrace["approvals"];
  send_runs?: FeishuSendTestResult[];
  timeline_checks?: Array<{
    object_type?: string;
    object_id?: EntityId;
    timeline_count?: number;
    timeline_types?: string[];
    ok?: boolean;
  }>;
  status?: "complete" | "ready" | "needs_action" | "blocked" | string;
  next_action?: string;
  checklist?: {
    message_tracked?: boolean;
    routed?: boolean;
    business_object_created?: boolean;
    approval_created?: boolean;
    timeline_ready?: boolean;
    send_completed?: boolean;
  };
}

export interface FeishuSendTestResult {
  sent?: boolean;
  mode?: string;
  reason?: string;
  channel?: string;
  chat_id?: string;
  target_type?: string;
  target_id?: string;
  text?: string;
  request_uuid?: string;
  feishu_message_id?: string;
  result?: Record<string, unknown>;
}

export interface AdapterPreviewResult {
  channel?: string;
  channel_label?: string;
  supported?: boolean;
  mode?: string;
  event_type?: string;
  message_event_preview?: {
    channel?: string;
    text?: string;
    sender_name?: string;
    sender_external_id?: string;
    conversation_id?: string;
    conversation_name?: string;
    conversation_type?: string;
    message_type?: string;
    external_message_id?: string;
    timestamp?: string | null;
    raw_payload?: Record<string, unknown>;
  };
  notes?: string[];
}

export interface AdapterImportResult {
  status?: string;
  batch?: {
    id?: EntityId;
    source?: string;
    status?: string;
    imported_count?: number;
    skipped_count?: number;
    error_count?: number;
  };
  messages?: MessageEvent[];
  traces?: AdapterImportTrace[];
  notes?: string[];
}

export interface AdapterImportTrace {
  message_id?: EntityId;
  agent_run_id?: EntityId;
  agent_type?: string;
  approval_ids?: EntityId[];
  approvals?: Approval[];
  related_objects?: RelatedObject[];
}

export interface ImportPayload {
  source_type: "csv" | "json" | "text";
  filename?: string;
  content: string;
}

export interface ImportResult {
  import_id?: EntityId;
  imported_count?: number;
  message_count?: number;
  created_tickets?: number;
  created_leads?: number;
  created_candidates?: number;
  created_knowledge_gaps?: number;
  created_approvals?: number;
  agent_runs?: number;
  errors?: string[];
  [key: string]: unknown;
}

export interface KnowledgeImportPayload {
  source_type: "markdown" | "faq" | "csv";
  filename?: string;
  content: string;
  default_category?: string;
  default_mode?: "item" | "gap";
  publish?: boolean;
}

export interface KnowledgeImportPreviewRow {
  row_index: number;
  mode: "item" | "gap" | string;
  title: string;
  question: string;
  answer: string;
  category: string;
  status: string;
  source_excerpt: string;
  warnings?: string[];
}

export interface KnowledgeImportPreviewResult {
  source_type: string;
  filename?: string;
  total_rows: number;
  rows: KnowledgeImportPreviewRow[];
  warnings?: string[];
}

export interface KnowledgeImportConfirmResult {
  batch?: Record<string, unknown>;
  created_items?: KnowledgeItem[];
  created_gaps?: KnowledgeGap[];
  preview?: KnowledgeImportPreviewResult;
}

export interface PageResult<T> {
  items: T[];
  total: number;
}

export type ApprovalDecision = "approved" | "rejected" | "edited";
