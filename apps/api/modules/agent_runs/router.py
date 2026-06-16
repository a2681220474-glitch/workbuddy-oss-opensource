from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import SessionDep, TenantDep
from apps.api.models import AgentRun, Candidate, FollowupTask, KnowledgeGap, Lead, MessageEvent, Ticket
from apps.api.modules.messages.replay import replay_message_route
from apps.api.schemas import AgentRunRead


router = APIRouter()


@router.get("", response_model=list[AgentRunRead])
def list_agent_runs(
    session: SessionDep,
    tenant: TenantDep,
    agent_type: str | None = None,
    status: str | None = None,
    message_id: int | None = None,
    business_object_type: str | None = None,
    business_object_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentRun]:
    statement = select(AgentRun).where(AgentRun.tenant_id == tenant.id)
    if agent_type:
        statement = statement.where(AgentRun.agent_type == agent_type)
    if status:
        statement = statement.where(AgentRun.status == status)
    if message_id:
        statement = statement.where(AgentRun.message_id == message_id)
    object_run_ids = run_ids_for_business_object(session, tenant.id, business_object_type, business_object_id)
    if object_run_ids is not None:
        if not object_run_ids:
            return []
        statement = statement.where(AgentRun.id.in_(object_run_ids))  # type: ignore[union-attr]
    statement = statement.order_by(AgentRun.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(statement).all())


@router.get("/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: int, session: SessionDep, tenant: TenantDep) -> AgentRun:
    run = session.get(AgentRun, run_id)
    if run is None or run.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    return run


@router.post("/{run_id}/replay")
def replay_agent_run(run_id: int, session: SessionDep, tenant: TenantDep) -> dict:
    run = session.get(AgentRun, run_id)
    if run is None or run.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    if run.message_id is None:
        raise HTTPException(status_code=400, detail="This AgentRun is not linked to a message and cannot be replayed")
    message = session.get(MessageEvent, run.message_id)
    if message is None or message.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Linked message not found")
    return replay_message_route(session=session, tenant_id=tenant.id, message=message, source_run=run)


def run_ids_for_business_object(session, tenant_id: int, object_type: str | None, object_id: int | None) -> list[int] | None:
    if not object_type:
        return None
    models = {
        "ticket": Ticket,
        "lead": Lead,
        "task": FollowupTask,
        "candidate": Candidate,
        "knowledge_gap": KnowledgeGap,
    }
    model = models.get(object_type)
    if model is None:
        return []
    statement = select(model).where(model.tenant_id == tenant_id)
    if object_id is not None:
        statement = statement.where(model.id == object_id)
    rows = session.exec(statement).all()
    return [row.agent_run_id for row in rows if row.agent_run_id is not None]
