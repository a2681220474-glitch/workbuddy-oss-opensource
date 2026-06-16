from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from apps.api.dependencies import CurrentUserDep, SessionDep, TenantDep
from apps.api.models import Candidate, utc_now
from apps.api.modules.audit.service import append_audit_log
from apps.api.schemas import CandidateChecklistUpdate, CandidateRead, CandidateUpdate


router = APIRouter()

CANDIDATE_STAGES = [
    {"value": "screening", "label": "筛选", "next": ["interview", "rejected"]},
    {"value": "interview", "label": "面试", "next": ["offer", "rejected", "screening"]},
    {"value": "offer", "label": "Offer", "next": ["onboarding", "rejected", "interview"]},
    {"value": "onboarding", "label": "入职", "next": ["hired", "rejected"]},
    {"value": "hired", "label": "已入职", "next": []},
    {"value": "rejected", "label": "淘汰", "next": ["screening"]},
]


@router.get("", response_model=list[CandidateRead])
def list_candidates(session: SessionDep, tenant: TenantDep, stage: str | None = None) -> list[Candidate]:
    statement = select(Candidate).where(Candidate.tenant_id == tenant.id)
    if stage:
        statement = statement.where(Candidate.stage == stage)
    statement = statement.order_by(Candidate.created_at.desc(), Candidate.id.desc())
    return list(session.exec(statement).all())


@router.get("/workflow")
def candidate_workflow() -> dict[str, Any]:
    return {
        "stages": CANDIDATE_STAGES,
        "transitions": {stage["value"]: stage["next"] for stage in CANDIDATE_STAGES},
    }


@router.patch("/{candidate_id}", response_model=CandidateRead)
def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Candidate:
    candidate = get_candidate(session, tenant.id, candidate_id)
    if payload.stage is not None:
        allowed = {stage["value"] for stage in CANDIDATE_STAGES}
        if payload.stage not in allowed:
            raise HTTPException(status_code=400, detail="Invalid candidate stage")
        candidate.stage = payload.stage
    if payload.match_score is not None:
        candidate.match_score = payload.match_score
    if payload.summary is not None:
        candidate.summary = payload.summary
    candidate.updated_at = utc_now()
    session.add(candidate)
    append_audit_log(
        session,
        tenant.id,
        "candidate_updated",
        f"{current_user.display_name} 更新候选人 #{candidate.id}",
        operator=current_user,
        scope_type="candidate",
        scope_id=candidate.id,
        object_type="candidate",
        object_id=candidate.id,
        status=candidate.stage,
        detail_json={"match_score": candidate.match_score},
    )
    session.commit()
    session.refresh(candidate)
    return candidate


@router.get("/{candidate_id}/match-analysis")
def candidate_match_analysis(candidate_id: int, session: SessionDep, tenant: TenantDep) -> dict[str, Any]:
    candidate = get_candidate(session, tenant.id, candidate_id)
    dimensions = score_dimensions(candidate)
    strengths = candidate_strengths(candidate)
    risks = candidate_risks(candidate)
    gaps = candidate_gaps(candidate)
    recommendation = recommendation_for(candidate, dimensions, risks)
    return {
        "candidate_id": candidate.id,
        "score": candidate.match_score,
        "role": candidate.role,
        "stage": candidate.stage,
        "dimensions": dimensions,
        "strengths": strengths,
        "risks": risks,
        "gaps": gaps,
        "recommendation": recommendation,
        "interview_questions": candidate.interview_questions_json,
        "onboarding_checklist": candidate.onboarding_checklist_json,
    }


@router.post("/{candidate_id}/checklist/{item_index}", response_model=CandidateRead)
def update_checklist_item(
    candidate_id: int,
    item_index: int,
    payload: CandidateChecklistUpdate,
    session: SessionDep,
    tenant: TenantDep,
    current_user: CurrentUserDep,
) -> Candidate:
    candidate = get_candidate(session, tenant.id, candidate_id)
    checklist = list(candidate.onboarding_checklist_json or [])
    if item_index < 0 or item_index >= len(checklist):
        raise HTTPException(status_code=404, detail="Checklist item not found")
    item = dict(checklist[item_index])
    item["completed"] = payload.completed
    item["status"] = "done" if payload.completed else "todo"
    item["completed_at"] = utc_now().isoformat() if payload.completed else None
    checklist[item_index] = item
    candidate.onboarding_checklist_json = checklist
    candidate.updated_at = utc_now()
    session.add(candidate)
    append_audit_log(
        session,
        tenant.id,
        "candidate_checklist_updated",
        f"{current_user.display_name} 更新候选人 #{candidate.id} 入职清单",
        operator=current_user,
        scope_type="candidate",
        scope_id=candidate.id,
        object_type="candidate",
        object_id=candidate.id,
        status=candidate.stage,
        detail_json={"item_index": item_index, "completed": payload.completed},
    )
    session.commit()
    session.refresh(candidate)
    return candidate


def get_candidate(session, tenant_id: int, candidate_id: int) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or candidate.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def score_dimensions(candidate: Candidate) -> dict[str, int]:
    text = f"{candidate.role} {candidate.summary}".lower()
    base = candidate.match_score
    return {
        "role_fit": bounded(base + keyword_delta(text, ["岗位", "负责", "项目", "经验"], 8)),
        "experience_depth": bounded(45 + keyword_delta(text, ["3年", "5年", "多年", "负责过", "主导"], 18)),
        "collaboration": bounded(50 + keyword_delta(text, ["跨部门", "协作", "推进", "沟通"], 15)),
        "motivation": bounded(50 + keyword_delta(text, ["想", "希望", "加入", "面试", "入职"], 14)),
        "risk": bounded(100 - keyword_delta(text, ["不合适", "拒绝", "暂不", "离职原因不清晰"], 30)),
    }


def keyword_delta(text: str, keywords: list[str], delta: int) -> int:
    return delta if any(keyword.lower() in text for keyword in keywords) else 0


def bounded(value: int) -> int:
    return max(0, min(100, int(value)))


def candidate_strengths(candidate: Candidate) -> list[str]:
    strengths = []
    text = candidate.summary
    if candidate.match_score >= 70:
        strengths.append("整体匹配分较高，建议优先推进。")
    if any(keyword in text for keyword in ["项目", "负责", "主导", "经验"]):
        strengths.append("简历文本包含项目或负责经历，可围绕真实贡献追问。")
    if candidate.stage in {"offer", "onboarding", "hired"}:
        strengths.append("候选人已进入后段流程，适合重点检查入职风险。")
    return strengths or ["当前信息较少，建议先补充 JD 要求和简历要点。"]


def candidate_risks(candidate: Candidate) -> list[str]:
    risks = []
    text = candidate.summary
    if candidate.match_score < 60:
        risks.append("匹配分偏低，建议确认核心能力是否满足岗位要求。")
    if candidate.role == "待确认岗位":
        risks.append("岗位尚未确认，后续面试题和入职清单需要 HR 复核。")
    if any(keyword in text for keyword in ["不合适", "拒绝", "暂不"]):
        risks.append("文本出现负向信号，推进前需要确认候选人意愿。")
    return risks


def candidate_gaps(candidate: Candidate) -> list[str]:
    gaps = []
    text = candidate.summary
    if not any(keyword in text for keyword in ["项目", "经历", "经验"]):
        gaps.append("缺少项目经历细节。")
    if not any(keyword in text for keyword in ["期望", "薪资", "到岗", "入职"]):
        gaps.append("缺少期望薪资或到岗时间。")
    if not candidate.interview_questions_json:
        gaps.append("缺少面试问题。")
    return gaps


def recommendation_for(candidate: Candidate, dimensions: dict[str, int], risks: list[str]) -> str:
    if candidate.stage == "rejected":
        return "已淘汰，建议保留原因并停止外部推进。"
    if candidate.stage == "hired":
        return "已入职，建议归档招聘记录并跟进入职体验。"
    if candidate.match_score >= 75 and not risks:
        return "建议推进到下一阶段，并保留结构化面试记录。"
    if dimensions["risk"] < 70 or risks:
        return "建议先补充风险信息，再决定是否推进。"
    return "建议 HR 复核岗位匹配点后推进。"
