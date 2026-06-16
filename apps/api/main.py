import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session, func, select

from apps.api.core.config import get_settings
from apps.api.db.session import engine, init_db
from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AgentRun, Approval, Candidate, FollowupTask, ImportBatch, KnowledgeGap, KnowledgeItem, Lead, LocalUser, MessageEvent, Report, Ticket
from apps.api.shared.runtime_status import runtime_stack_snapshot
from apps.api.shared.structured_logging import configure_service_logging, log_event
from apps.api.schemas import DashboardSummary, FrontendDashboardSummary
from apps.api.modules.agent_runs.router import router as agent_runs_router
from apps.api.modules.audit.router import router as audit_router
from apps.api.modules.approvals.router import router as approvals_router
from apps.api.modules.adapters.preview import router as adapters_preview_router
from apps.api.modules.auth.router import router as auth_router
from apps.api.modules.business_objects.router import router as business_objects_router
from apps.api.modules.candidates.router import router as candidates_router
from apps.api.modules.channel_events.router import router as channel_events_router
from apps.api.modules.channels.feishu import router as feishu_channel_router
from apps.api.modules.channels.generic import router as generic_channel_router
from apps.api.modules.channels.wecom import router as wecom_channel_router
from apps.api.modules.config_center.router import router as config_center_router
from apps.api.modules.conversations.router import router as conversations_router
from apps.api.modules.community.router import router as community_router
from apps.api.modules.demo.router import router as demo_router
from apps.api.modules.imports.router import router as imports_router
from apps.api.modules.knowledge.router import router as knowledge_router
from apps.api.modules.leads.router import router as leads_router
from apps.api.modules.messages.router import router as messages_router
from apps.api.modules.reports.router import router as reports_router
from apps.api.modules.tasks.router import router as tasks_router
from apps.api.modules.tickets.router import router as tickets_router
from apps.api.modules.users.router import router as users_router
from apps.api.modules.workbench.router import router as workbench_router
from apps.api.modules.auth.service import read_session_payload
from apps.api.version import APP_VERSION


settings = get_settings()
app = FastAPI(title=settings.app_name, version=APP_VERSION)
logger = logging.getLogger("workbuddy.api")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ADMIN_ONLY_UNSAFE_PREFIXES = (
    "/api/users",
    "/api/config",
    "/api/demo",
    "/api/imports",
    "/api/messages",
    "/api/channel-events",
    "/api/agent-runs",
    "/api/conversations",
)
APPROVER_UNSAFE_PREFIXES = ("/api/approvals", "/api/business-objects")
HANDLER_UNSAFE_PREFIXES = (
    "/api/business-objects",
    "/api/tickets",
    "/api/leads",
    "/api/tasks",
    "/api/candidates",
    "/api/community",
    "/api/knowledge",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    configure_service_logging("api")
    init_db()
    log_event(logger, "api_startup", version=APP_VERSION, environment=settings.environment)


@app.middleware("http")
async def auth_gate_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    if path == "/health" or path.startswith("/api/auth/"):
        return await call_next(request)
    if path.startswith("/api/channels/") and path.endswith("/webhook"):
        return await call_next(request)

    session_token = request.cookies.get(settings.auth_cookie_name)
    if session_token and read_session_payload(session_token):
        return await call_next(request)
    if settings.environment == "local" and request.headers.get("X-WorkBuddy-User"):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    return await call_next(request)


@app.middleware("http")
async def rbac_gate_middleware(request: Request, call_next):
    path = request.url.path
    if request.method not in UNSAFE_METHODS:
        return await call_next(request)
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    if path.startswith("/api/channels/") and path.endswith("/webhook"):
        return await call_next(request)

    user = resolve_request_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    if not role_can_write_path(user.role, path):
        return JSONResponse(status_code=403, content={"detail": "Current role is not allowed to perform this action."})
    request.state.current_user_role = user.role
    return await call_next(request)


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(logger, "http_request_failed", method=request.method, path=request.url.path, latency_ms=latency_ms, error=str(exc))
        raise
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    log_event(logger, "http_request", method=request.method, path=request.url.path, status_code=response.status_code, latency_ms=latency_ms)
    return response


@app.get("/health")
def health() -> dict[str, object]:
    runtime = runtime_stack_snapshot(settings)
    return {
        "status": runtime["status"],
        "app": settings.app_name,
        "environment": settings.environment,
        "version": APP_VERSION,
        "timezone": runtime["timezone"],
        "database": runtime["database"],
        "backup": runtime["backup"],
        "redis": runtime["redis"],
        "background_jobs": runtime["background_jobs"],
        "logs": runtime["logs"],
        "channels": runtime["channels"],
    }


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(session: SessionDep, tenant: TenantDep) -> DashboardSummary:
    return DashboardSummary(
        messages=count_rows(session, MessageEvent, MessageEvent.tenant_id == tenant.id),
        tickets=count_rows(session, Ticket, Ticket.tenant_id == tenant.id),
        leads=count_rows(session, Lead, Lead.tenant_id == tenant.id),
        approvals_pending=count_rows(
            session,
            Approval,
            Approval.tenant_id == tenant.id,
            Approval.status == "pending_review",
        ),
        agent_runs=count_rows(session, AgentRun, AgentRun.tenant_id == tenant.id),
        today_imports=count_rows(session, ImportBatch, ImportBatch.tenant_id == tenant.id),
    )


@app.get("/api/dashboard", response_model=FrontendDashboardSummary)
def dashboard_frontend(session: SessionDep, tenant: TenantDep) -> FrontendDashboardSummary:
    summary = dashboard_summary(session, tenant)
    return FrontendDashboardSummary(
        message_count=summary.messages,
        pending_approval_count=summary.approvals_pending,
        ticket_count=summary.tickets,
        lead_count=summary.leads,
        task_count=count_rows(session, FollowupTask, FollowupTask.tenant_id == tenant.id),
        candidate_count=count_rows(session, Candidate, Candidate.tenant_id == tenant.id),
        knowledge_gap_count=count_rows(session, KnowledgeGap, KnowledgeGap.tenant_id == tenant.id),
        knowledge_item_count=count_rows(session, KnowledgeItem, KnowledgeItem.tenant_id == tenant.id),
        report_count=count_rows(session, Report, Report.tenant_id == tenant.id),
        agent_run_count=summary.agent_runs,
        today_import_count=summary.today_imports,
    )


def count_rows(session: SessionDep, model, *where_clauses) -> int:
    statement = select(func.count()).select_from(model).where(*where_clauses)
    return session.exec(statement).one()


def resolve_request_user(request: Request) -> LocalUser | None:
    session_token = request.cookies.get(settings.auth_cookie_name)
    with Session(engine) as session:
        if session_token:
            payload = read_session_payload(session_token)
            if payload and payload.get("user_id") is not None:
                user = session.get(LocalUser, int(payload["user_id"]))
                if user is not None and user.status == "active":
                    return user
        if settings.environment == "local":
            header_user = request.headers.get("X-WorkBuddy-User")
            if header_user:
                return session.exec(
                    select(LocalUser).where(
                        LocalUser.status == "active",
                        (LocalUser.username == header_user) | (LocalUser.display_name == header_user),
                    )
                ).first()
    return None


def role_can_write_path(role: str | None, path: str) -> bool:
    if role == "admin":
        return True
    if role == "readonly":
        return False
    if path.startswith(ADMIN_ONLY_UNSAFE_PREFIXES):
        return False
    if role == "approver":
        return path.startswith(APPROVER_UNSAFE_PREFIXES)
    if role == "handler":
        return path.startswith(HANDLER_UNSAFE_PREFIXES)
    return False


app.include_router(imports_router, prefix="/api/imports", tags=["imports"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(workbench_router, prefix="/api/workbench", tags=["workbench"])
app.include_router(audit_router, prefix="/api/audit-logs", tags=["audit"])
app.include_router(feishu_channel_router, prefix="/api/channels/feishu", tags=["channels-feishu"])
app.include_router(wecom_channel_router, prefix="/api/channels/wecom", tags=["channels-wecom"])
app.include_router(generic_channel_router, prefix="/api/channels", tags=["channels"])
app.include_router(channel_events_router, prefix="/api/channel-events", tags=["channel-events"])
app.include_router(adapters_preview_router, prefix="/api/adapters", tags=["adapters"])
app.include_router(config_center_router, prefix="/api/config", tags=["config"])
app.include_router(conversations_router, prefix="/api/conversations", tags=["conversations"])
app.include_router(business_objects_router, prefix="/api/business-objects", tags=["business-objects"])
app.include_router(messages_router, prefix="/api/messages", tags=["messages"])
app.include_router(tickets_router, prefix="/api/tickets", tags=["tickets"])
app.include_router(leads_router, prefix="/api/leads", tags=["leads"])
app.include_router(community_router, prefix="/api/community", tags=["community"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(candidates_router, prefix="/api/candidates", tags=["candidates"])
app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
app.include_router(approvals_router, prefix="/api/approvals", tags=["approvals"])
app.include_router(agent_runs_router, prefix="/api/agent-runs", tags=["agent-runs"])
app.include_router(demo_router, prefix="/api/demo", tags=["demo"])
