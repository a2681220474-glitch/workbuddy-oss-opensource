import type {
  AgentRun,
  Approval,
  ApprovalCardPreview,
  ApprovalContext,
  ApprovalDecision,
  ApprovalSendPreview,
  AuditLog,
  AdapterImportResult,
  AdapterPreviewResult,
  BusinessObjectCenter,
  BusinessObjectDetail,
  Candidate,
  CandidateMatchAnalysis,
  CandidateWorkflow,
  CommunityOverview,
  ConfigStatus,
  SecretStorageOperationResult,
  DashboardSummary,
  DemoPrepareResult,
  EntityId,
  ImportPayload,
  ImportResult,
  KnowledgeGap,
  KnowledgeGapDetail,
  KnowledgeGraphResponse,
  KnowledgeItem,
  KnowledgeItemDetail,
  KnowledgeImportConfirmResult,
  KnowledgeImportPayload,
  KnowledgeImportPreviewResult,
  KnowledgeObsidianExport,
  KnowledgeQualityDashboard,
  KnowledgeSearchPayload,
  KnowledgeSearchResponse,
  Lead,
  LeadDraft,
  LeadScorecard,
  LeadWorkflow,
  LLMSmokeTestResult,
  MessageEvent,
  MessageRerunResult,
  OperationsSummary,
  PageResult,
  Report,
  RuntimeConfigSaveResult,
  FollowupTask,
  FeishuChannelEvent,
  FeishuConversation,
  FeishuDiagnostics,
  FeishuSendTestResult,
  SafeDemoModeResult,
  FeishuStatus,
  LocalUser,
  WeComDiagnostics,
  WorkbenchSummary,
  Ticket,
  TicketKnowledgeSuggestion,
  TicketWorkflow,
  AuthBootstrapStatus,
  AuthSession
} from "../types";

const DEFAULT_API_BASE_URL = "/api";
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");

const rawApiBaseUrl = configuredApiBaseUrl ?? DEFAULT_API_BASE_URL;
let authExpiredEventDispatched = false;

export const API_BASE_URL = rawApiBaseUrl.startsWith("/")
  ? `${window.location.origin}${rawApiBaseUrl}`
  : rawApiBaseUrl;

interface RequestOptions extends RequestInit {
  query?: Record<string, string | number | boolean | undefined>;
}

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const url = new URL(path, API_BASE_URL);
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { query, headers, body, ...init } = options;
  const response = await fetch(buildUrl(path, query), {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...headers
    },
    body
  });

  if (!response.ok) {
    const detail = await response.text();
    if (response.status === 401 && !path.startsWith("/api/auth/") && !authExpiredEventDispatched) {
      authExpiredEventDispatched = true;
      window.dispatchEvent(new CustomEvent("workbuddy:auth-expired"));
    }
    throw new ApiError(response.status, parseErrorMessage(detail) || response.statusText);
  }

  if (path === "/api/auth/me") {
    authExpiredEventDispatched = false;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function parseErrorMessage(detail: string) {
  if (!detail) return "";
  try {
    const payload = JSON.parse(detail) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => {
          if (!item || typeof item !== "object") return "";
          const detailItem = item as { loc?: unknown[]; msg?: unknown };
          const field = Array.isArray(detailItem.loc) ? detailItem.loc[detailItem.loc.length - 1] : "";
          const message = typeof detailItem.msg === "string" ? detailItem.msg : "";
          return [fieldLabel(String(field || "")), translateValidationMessage(message)].filter(Boolean).join("：");
        })
        .filter(Boolean)
        .join("。");
    }
    if (payload.detail && typeof payload.detail === "object") {
      const nested = payload.detail as { message?: unknown; advice?: unknown };
      const message = typeof nested.message === "string" ? nested.message : "";
      const advice = typeof nested.advice === "string" ? nested.advice : "";
      return [message, advice].filter(Boolean).join("。");
    }
  } catch {
    return detail;
  }
  return detail;
}

function fieldLabel(field: string) {
  const labels: Record<string, string> = {
    username: "用户名",
    display_name: "显示名",
    password: "密码",
    new_password: "新密码",
    current_password: "当前密码",
  };
  return labels[field] ?? field;
}

function translateValidationMessage(message: string) {
  if (!message) return "";
  if (message.includes("at least 8 characters") || message.includes("at least 8")) {
    return "至少需要 8 位";
  }
  if (message.includes("String should have at least 8 characters")) {
    return "至少需要 8 位";
  }
  if (message.includes("String should have at least 1 character")) {
    return "不能为空";
  }
  if (message.includes("Field required")) {
    return "不能为空";
  }
  return message;
}

function normalizeList<T>(payload: T[] | { items?: T[]; data?: T[]; total?: number; count?: number }): PageResult<T> {
  if (Array.isArray(payload)) {
    return { items: payload, total: payload.length };
  }

  const items = payload.items ?? payload.data ?? [];
  return {
    items,
    total: payload.total ?? payload.count ?? items.length
  };
}

export const api = {
  getAuthBootstrapStatus: async () => request<AuthBootstrapStatus>("/api/auth/bootstrap-status"),
  bootstrapAuth: async (payload: { username?: string; display_name?: string; password: string }) =>
    request<AuthSession>("/api/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  login: async (payload: { username: string; password: string }) =>
    request<AuthSession>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  logout: async () =>
    request<{ status: string }>("/api/auth/logout", {
      method: "POST"
    }),
  changePassword: async (payload: { current_password: string; new_password: string }) =>
    request<{ status: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getCurrentUser: async () => request<LocalUser>("/api/auth/me"),
  getLocalUsers: async () =>
    normalizeList(await request<LocalUser[] | { items?: LocalUser[]; total?: number }>("/api/users")),
  createLocalUser: async (payload: { username: string; display_name: string; role: string; password: string }) =>
    request<LocalUser>("/api/users", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateLocalUser: async (id: EntityId, payload: { display_name?: string; role?: string; status?: string; password?: string }) =>
    request<LocalUser>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getDashboard: async () => request<DashboardSummary>("/api/dashboard"),
  getWorkbenchSummary: async () => request<WorkbenchSummary>("/api/workbench/me"),
  getAuditLogs: async (params: { action_type?: string; scope_type?: string; object_type?: string; operator_user_id?: EntityId; limit?: number } = {}) =>
    normalizeList(
      await request<AuditLog[] | { items?: AuditLog[]; total?: number }>("/api/audit-logs", {
        query: params
      })
    ),
  getConfigStatus: async () => request<ConfigStatus>("/api/config/status"),
  updateDefaultSendMode: async (defaultSendMode: "mock" | "real") =>
    request<ConfigStatus["global_policy"]>("/api/config/default-send-mode", {
      method: "PATCH",
      body: JSON.stringify({ default_send_mode: defaultSendMode })
    }),
  enableSafeDemoMode: async () =>
    request<SafeDemoModeResult>("/api/config/safe-demo-mode", {
      method: "POST"
    }),
  updateLlmRuntime: async (payload: { provider: string; base_url?: string; model: string; api_key?: string; timeout_seconds?: number }) =>
    request<RuntimeConfigSaveResult>("/api/config/runtime/llm", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  smokeTestLlmRuntime: async (payload: { provider?: string; base_url?: string; model?: string; api_key?: string; timeout_seconds?: number }) =>
    request<LLMSmokeTestResult>("/api/config/runtime/llm/smoke-test", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateRuntimePolicy: async (payload: { enable_real_im_adapters: boolean; enable_external_send: boolean }) =>
    request<RuntimeConfigSaveResult>("/api/config/runtime/policy", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  updateChannelRuntime: async (channel: "feishu" | "wecom" | "dingtalk", payload: Record<string, unknown>) =>
    request<RuntimeConfigSaveResult>(`/api/config/runtime/channels/${channel}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  migrateRuntimeSecrets: async () =>
    request<SecretStorageOperationResult>("/api/config/runtime/secrets/migrate", {
      method: "POST"
    }),
  rotateRuntimeSecretKey: async () =>
    request<SecretStorageOperationResult>("/api/config/runtime/secrets/rotate-key", {
      method: "POST"
    }),
  getFeishuStatus: async () => request<FeishuStatus>("/api/channels/feishu/status"),
  getFeishuDiagnostics: async (checkToken = false) =>
    request<FeishuDiagnostics>("/api/channels/feishu/diagnostics/full", {
      query: { check_token: checkToken }
    }),
  getWeComDiagnostics: async (checkToken = false) =>
    request<WeComDiagnostics>("/api/channels/wecom/diagnostics/full", {
      query: { check_token: checkToken }
    }),
  getFeishuConversations: async () =>
    normalizeList(await request<FeishuConversation[] | { items?: FeishuConversation[]; total?: number }>("/api/conversations/feishu")),
  getConversations: async (channel = "all") =>
    normalizeList(
      await request<FeishuConversation[] | { items?: FeishuConversation[]; total?: number }>("/api/conversations", {
        query: { channel }
      })
    ),
  updateConversationPolicy: async (id: FeishuConversation["id"], payload: { bound_agent?: string; send_mode?: string }) =>
    request<FeishuConversation>(`/api/conversations/${id}/policy`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  bulkUpdateConversationPolicy: async (payload: { channel?: string; ids?: Array<string | number>; bound_agent?: string; send_mode?: string }) =>
    request<{ updated_count?: number; items?: FeishuConversation[] }>("/api/conversations/policy/bulk", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getChannelEvents: async (params: { channel?: string; status?: string; relation?: string; limit?: number } = {}) =>
    normalizeList(
      await request<FeishuChannelEvent[] | { items?: FeishuChannelEvent[]; total?: number }>("/api/channel-events", {
        query: params
      })
    ),
  retryChannelEvent: async (id: EntityId) =>
    request<Record<string, unknown>>(`/api/channel-events/${id}/retry`, {
      method: "POST"
    }),
  previewAdapterPayload: async (payload: { channel: string; payload: Record<string, unknown> }) =>
    request<AdapterPreviewResult>("/api/adapters/preview", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  importAdapterPayload: async (payload: { channel: string; payload: Record<string, unknown> }) =>
    request<AdapterImportResult>("/api/adapters/import", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  mockFeishuSend: async (payload: { chat_id?: string; text?: string }) =>
    request<FeishuSendTestResult>("/api/channels/feishu/mock-send", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  realFeishuTestSend: async (payload: { chat_id: string; text: string; confirm_real_send: true; authorization_phrase: string }) =>
    request<FeishuSendTestResult>("/api/channels/feishu/test-send", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  mockWeComSend: async (payload: { target_type?: "user" | "chat"; target_id?: string; text?: string }) =>
    request<FeishuSendTestResult>("/api/channels/wecom/mock-send", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  realWeComTestSend: async (payload: { target_type: "user" | "chat"; target_id: string; text: string; confirm_real_send: true; authorization_phrase: string }) =>
    request<FeishuSendTestResult>("/api/channels/wecom/test-send", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getMessages: async () => normalizeList(await request<MessageEvent[] | { items?: MessageEvent[]; data?: MessageEvent[]; total?: number }>("/api/messages/enriched")),
  rerunMessage: async (id: EntityId) =>
    request<MessageRerunResult>(`/api/messages/${id}/rerun`, {
      method: "POST"
    }),
  getTickets: async (params: { status?: string; priority?: string } = {}) =>
    normalizeList(
      await request<Ticket[] | { items?: Ticket[]; data?: Ticket[]; total?: number }>("/api/tickets", {
        query: params
      })
    ),
  updateTicket: async (id: Ticket["id"], payload: { status?: string; priority?: string }) =>
    request<Ticket>(`/api/tickets/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getTicketWorkflow: async () => request<TicketWorkflow>("/api/tickets/workflow"),
  getSlaConfig: async () => request<Record<string, number>>("/api/tickets/sla-config"),
  updateSlaConfig: async (payload: Record<string, number>) =>
    request<Record<string, number>>("/api/tickets/sla-config", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getTicketKnowledgeSuggestions: async (id: Ticket["id"]) =>
    request<TicketKnowledgeSuggestion>(`/api/tickets/${id}/knowledge-suggestions`),
  createKnowledgeFromTicket: async (id: Ticket["id"], payload: { mode: "gap" | "item"; category?: string; answer?: string; publish?: boolean }) =>
    request<KnowledgeGap | KnowledgeItem>(`/api/tickets/${id}/knowledge`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getLeads: async (params: { stage?: string; priority?: string } = {}) =>
    normalizeList(
      await request<Lead[] | { items?: Lead[]; data?: Lead[]; total?: number }>("/api/leads", {
        query: params
      })
    ),
  updateLead: async (id: Lead["id"], payload: { stage?: string; priority?: string; next_step?: string }) =>
    request<Lead>(`/api/leads/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getLeadWorkflow: async () => request<LeadWorkflow>("/api/leads/workflow"),
  getLeadScorecard: async (id: Lead["id"]) => request<LeadScorecard>(`/api/leads/${id}/scorecard`),
  getLeadDraft: async (id: Lead["id"]) => request<LeadDraft>(`/api/leads/${id}/draft`),
  createLeadApprovalDraft: async (id: Lead["id"], payload: { draft_content?: string; next_step?: string }) =>
    request<{ lead_id?: EntityId; approval_id?: EntityId; agent_run_id?: EntityId; next_step?: string }>(`/api/leads/${id}/approval-draft`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getCommunityOverview: async () => request<CommunityOverview>("/api/community/overview"),
  completeCommunityTask: async (id: EntityId) =>
    request<{ task_id?: EntityId; status?: string }>(`/api/community/tasks/${id}/complete`, {
      method: "POST"
    }),
  createCommunityApprovalDraft: async (id: EntityId, payload: { draft_content?: string }) =>
    request<{ message_id?: EntityId; approval_id?: EntityId; agent_run_id?: EntityId }>(`/api/community/messages/${id}/approval-draft`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getTasks: async (params: { status?: string; assignee_name?: string; assignee_user_id?: EntityId; overdue?: boolean } = {}) =>
    normalizeList(await request<FollowupTask[] | { items?: FollowupTask[]; data?: FollowupTask[]; total?: number }>("/api/tasks", {
      query: params
    })),
  updateTask: async (id: FollowupTask["id"], payload: { status?: string; priority?: string; assignee_user_id?: EntityId; assignee_name?: string; due_hint?: string; due_at?: string | null; summary?: string }) =>
    request<FollowupTask>(`/api/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getBusinessObjects: async () => request<BusinessObjectCenter>("/api/business-objects"),
  getBusinessObjectDetail: async (type: string, id: EntityId) =>
    request<BusinessObjectDetail>(`/api/business-objects/${type}/${id}`),
  createProcessingRecord: async (type: string, id: EntityId, payload: { action_type?: string; status?: string; assignee_user_id?: EntityId; assignee_name?: string; due_hint?: string; due_at?: string | null; next_step?: string; note?: string; operator_name?: string }) =>
    request<BusinessObjectDetail["processing_records"] extends Array<infer T> ? T : never>(`/api/business-objects/${type}/${id}/records`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getOperationsSummary: async () => request<OperationsSummary>("/api/business-objects/operations-summary"),
  getCandidates: async (params: { stage?: string } = {}) =>
    normalizeList(
      await request<Candidate[] | { items?: Candidate[]; data?: Candidate[]; total?: number }>("/api/candidates", {
        query: params
      })
    ),
  getCandidateWorkflow: async () => request<CandidateWorkflow>("/api/candidates/workflow"),
  updateCandidate: async (id: Candidate["id"], payload: { stage?: string; match_score?: number; summary?: string }) =>
    request<Candidate>(`/api/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getCandidateMatchAnalysis: async (id: Candidate["id"]) => request<CandidateMatchAnalysis>(`/api/candidates/${id}/match-analysis`),
  updateCandidateChecklistItem: async (id: Candidate["id"], itemIndex: number, completed: boolean) =>
    request<Candidate>(`/api/candidates/${id}/checklist/${itemIndex}`, {
      method: "POST",
      body: JSON.stringify({ completed })
    }),
  getKnowledgeGaps: async (status = "", category = "") =>
    normalizeList(
      await request<KnowledgeGap[] | { items?: KnowledgeGap[]; data?: KnowledgeGap[]; total?: number }>("/api/knowledge/gaps", {
        query: { status, category }
      })
    ),
  getKnowledgeItems: async (status = "", category = "") =>
    normalizeList(
      await request<KnowledgeItem[] | { items?: KnowledgeItem[]; data?: KnowledgeItem[]; total?: number }>("/api/knowledge/items", {
        query: { status, category }
      })
    ),
  getKnowledgeGapDetail: async (id: KnowledgeGap["id"]) =>
    request<KnowledgeGapDetail>(`/api/knowledge/gaps/${id}`),
  getKnowledgeItemDetail: async (id: KnowledgeItem["id"]) =>
    request<KnowledgeItemDetail>(`/api/knowledge/items/${id}`),
  getKnowledgeGraph: async (category = "", status = "") =>
    request<KnowledgeGraphResponse>("/api/knowledge/graph", {
      query: { category, status }
    }),
  getKnowledgeQuality: async (category = "") =>
    request<KnowledgeQualityDashboard>("/api/knowledge/quality", {
      query: { category }
    }),
  searchKnowledge: async (payload: KnowledgeSearchPayload) =>
    request<KnowledgeSearchResponse>("/api/knowledge/search", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  rebuildKnowledgeIndex: async () =>
    request<{ model: string; dimensions: number; indexed_items: number }>("/api/knowledge/index/rebuild", {
      method: "POST"
    }),
  rollbackKnowledgeVersion: async (itemId: KnowledgeItem["id"], versionId: EntityId, changeSummary?: string) =>
    request<KnowledgeItem>(`/api/knowledge/items/${itemId}/versions/${versionId}/rollback`, {
      method: "POST",
      body: JSON.stringify({ change_summary: changeSummary })
    }),
  updateKnowledgeHitFeedback: async (hitId: EntityId, status: "useful" | "not_useful", note?: string) =>
    request<{ hit: Record<string, unknown>; item: KnowledgeItem; feedback: string }>(`/api/knowledge/hits/${hitId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ status, note })
    }),
  exportKnowledgeObsidianDraft: async (category = "") =>
    request<KnowledgeObsidianExport>("/api/knowledge/obsidian-export", {
      query: { category }
    }),
  acceptKnowledgeGap: async (id: KnowledgeGap["id"]) =>
    request<KnowledgeItem>(`/api/knowledge/gaps/${id}/accept`, {
      method: "POST"
    }),
  ignoreKnowledgeGap: async (id: KnowledgeGap["id"]) =>
    request<KnowledgeGap>(`/api/knowledge/gaps/${id}/ignore`, {
      method: "POST"
    }),
  updateKnowledgeItem: async (id: KnowledgeItem["id"], payload: { title?: string; answer?: string; category?: string; status?: string; change_summary?: string; review_due_at?: string | null; last_reviewed_at?: string | null; quality_status?: string; quality_score?: number }) =>
    request<KnowledgeItem>(`/api/knowledge/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getReports: async (reportType = "") =>
    normalizeList(
      await request<Report[] | { items?: Report[]; data?: Report[]; total?: number }>("/api/reports", {
        query: { report_type: reportType }
      })
    ),
  generateReport: async (reportType: string) =>
    request<Report>("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({ report_type: reportType })
    }),
  getApprovals: async (params: { status?: string; target_agent?: string; business_object_type?: string } = {}) =>
    normalizeList(
      await request<Approval[] | { items?: Approval[]; data?: Approval[]; total?: number }>("/api/approvals/enriched", {
        query: params
      })
    ),
  getAgentRuns: async (params: { agent_type?: string; status?: string; message_id?: EntityId; business_object_type?: string; business_object_id?: EntityId } = {}) =>
    normalizeList(
      await request<AgentRun[] | { items?: AgentRun[]; data?: AgentRun[]; total?: number }>("/api/agent-runs", {
        query: params
      })
    ),
  getAgentRun: async (id: EntityId) => request<AgentRun>(`/api/agent-runs/${id}`),
  replayAgentRun: async (id: EntityId) =>
    request<MessageRerunResult>(`/api/agent-runs/${id}/replay`, {
      method: "POST"
    }),
  importMessages: async (payload: ImportPayload) =>
    request<ImportResult>("/api/imports/messages", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  previewKnowledgeImport: async (payload: KnowledgeImportPayload) =>
    request<KnowledgeImportPreviewResult>("/api/imports/knowledge/preview", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  confirmKnowledgeImport: async (payload: KnowledgeImportPayload) =>
    request<KnowledgeImportConfirmResult>("/api/imports/knowledge/confirm", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  decideApproval: async (id: Approval["id"], decision: ApprovalDecision, finalContent?: string) =>
    request<Approval>(`/api/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        final_content: finalContent
      })
    }),
  sendApproval: async (id: Approval["id"]) =>
    request<Approval>(`/api/approvals/${id}/send`, {
      method: "POST"
    }),
  previewApprovalSend: async (id: Approval["id"]) =>
    request<ApprovalSendPreview>(`/api/approvals/${id}/send-preview`),
  previewApprovalCard: async (id: Approval["id"]) =>
    request<ApprovalCardPreview>(`/api/approvals/${id}/feishu-card-preview`),
  sendApprovalCard: async (id: Approval["id"], confirmRealSend = false) =>
    request<Record<string, unknown>>(`/api/approvals/${id}/feishu-card`, {
      method: "POST",
      body: JSON.stringify({ confirm_real_send: confirmRealSend })
    }),
  getApprovalContext: async (id: Approval["id"]) =>
    request<ApprovalContext>(`/api/approvals/${id}/context`),
  resetDemo: async () =>
    request<Record<string, unknown>>("/api/demo/reset", {
      method: "POST"
    }),
  prepareDemo: async () =>
    request<DemoPrepareResult>("/api/demo/prepare", {
      method: "POST"
    })
};

export { ApiError };
