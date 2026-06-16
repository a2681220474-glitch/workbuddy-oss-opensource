"""Recruiting and onboarding scenario agent for v0.9 Alpha."""

from __future__ import annotations

import re
from typing import Any, Mapping


def build_recruiting_actions(message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    text = _message_text(message)
    entities = dict(route.get("entities") or {})
    recruiting_intent = str(entities.get("recruiting_intent") or "resume_screening")
    candidate_fields = _candidate_fields(text, message, recruiting_intent)
    draft_reply = _draft_reply(recruiting_intent, candidate_fields)

    actions = [
        {
            "action_type": "create_candidate",
            "priority": "normal",
            "requires_approval": False,
            "reason": f"Recruiting route detected {recruiting_intent}; create a candidate record.",
            "business_object": {"type": "candidate", "fields": candidate_fields},
            "next_steps": ["确认候选人岗位", "补充简历要点", "安排面试或进入入职清单"],
        },
        {
            "action_type": "create_onboarding_task",
            "priority": "normal",
            "requires_approval": False,
            "reason": "Recruiting workflow needs an explicit HR follow-up task.",
            "business_object": {
                "type": "task",
                "fields": {
                    "title": _task_title(recruiting_intent, candidate_fields),
                    "status": "todo",
                    "task_type": "recruiting_followup",
                    "related_object_type": "candidate",
                    "source_message_id": message.get("id") or message.get("message_id"),
                    "summary": candidate_fields["summary"],
                    "due_hint": "本周",
                },
            },
            "next_steps": ["HR 跟进候选人", "确认面试或入职材料"],
        },
        {
            "action_type": "send_draft_to_approval",
            "priority": "normal",
            "requires_approval": True,
            "reason": "Candidate-facing HR reply must be reviewed before sending.",
            "business_object": {
                "type": "approval",
                "fields": {
                    "approval_type": "external_reply",
                    "channel": message.get("channel") or message.get("source_platform") or "local_import",
                    "conversation_id": message.get("conversation_id"),
                    "draft_reply": draft_reply,
                    "related_object_type": "candidate",
                    "related_object_hint": candidate_fields["name"],
                },
            },
            "draft_reply": draft_reply,
            "next_steps": ["HR 审核回复", "编辑后发送"],
        },
    ]

    return {
        "agent_name": "recruiting_hr_agent",
        "prompt": {"key": "recruiting.hr.v1", "version": "v0.9-alpha"},
        "analysis": {
            "recruiting_intent": recruiting_intent,
            "candidate": candidate_fields,
            "confidence": route.get("confidence", 0.72),
        },
        "actions": actions,
    }


def _message_text(message: Mapping[str, Any]) -> str:
    return str(message.get("text") or message.get("content") or message.get("message_text") or "").strip()


def _candidate_fields(text: str, message: Mapping[str, Any], recruiting_intent: str) -> dict[str, Any]:
    role = _extract_role(text)
    name = _extract_name(text) or message.get("sender_name") or "未知候选人"
    score = _match_score(text, recruiting_intent)
    return {
        "name": str(name)[:200],
        "role": role,
        "stage": "onboarding" if recruiting_intent == "onboarding" else "screening",
        "match_score": score,
        "summary": text[:800] or "候选人信息待补充",
        "interview_questions": _interview_questions(role, text),
        "onboarding_checklist": _onboarding_checklist(role),
        "source_message_id": message.get("id") or message.get("message_id"),
    }


def _extract_role(text: str) -> str:
    role_keywords = ["产品经理", "后端工程师", "前端工程师", "运营", "销售", "客服", "HR", "设计师"]
    for keyword in role_keywords:
        if keyword.lower() in text.lower():
            return keyword
    match = re.search(r"(应聘|岗位|JD)[:： ]?([\u4e00-\u9fa5A-Za-z0-9 ]{2,24})", text)
    return match.group(2).strip() if match else "待确认岗位"


def _extract_name(text: str) -> str | None:
    match = re.search(r"(候选人|我叫|姓名)[:： ]?([\u4e00-\u9fa5A-Za-z]{2,12})", text)
    return match.group(2) if match else None


def _match_score(text: str, recruiting_intent: str) -> int:
    score = 45
    rules = [
        (["简历", "经历", "项目", "经验"], 15),
        (["3年", "5年", "多年", "负责过"], 15),
        (["面试", "约面", "沟通"], 10),
        (["入职", "offer", "材料"], 20),
        (["不合适", "拒绝", "暂不"], -20),
    ]
    lowered = text.lower()
    for keywords, delta in rules:
        if any(keyword.lower() in lowered for keyword in keywords):
            score += delta
    if recruiting_intent == "onboarding":
        score += 10
    return max(0, min(100, score))


def _interview_questions(role: str, text: str) -> list[dict[str, str]]:
    return [
        {
            "category": "岗位能力",
            "question": f"请介绍一个最能体现你胜任{role}的项目，你负责的边界和最终结果是什么？",
            "purpose": "验证岗位核心能力和真实贡献",
            "signal": "能说清目标、动作、结果和复盘",
        },
        {
            "category": "简历亮点",
            "question": f"简历里最接近{role}要求的一段经历是什么？当时最大的难点在哪里？",
            "purpose": "追问简历亮点是否可复用到当前岗位",
            "signal": "能把经验迁移到新岗位场景",
        },
        {
            "category": "风险点",
            "question": "如果入职后发现资源、节奏或协作方式和预期不一致，你会怎么处理？",
            "purpose": "验证稳定性、沟通方式和预期管理",
            "signal": "能主动沟通并给出建设性处理方式",
        },
        {
            "category": "动机匹配",
            "question": "你希望下一份工作优先解决什么问题？为什么现在考虑这个机会？",
            "purpose": "确认求职动机和岗位吸引点",
            "signal": "动机与团队阶段、岗位职责一致",
        },
    ]


def _onboarding_checklist(role: str) -> list[dict[str, str]]:
    return [
        {"title": "确认入职日期和直属负责人", "owner": "HR", "phase": "offer", "status": "todo", "completed": False},
        {"title": "收集身份证、银行卡、合同信息", "owner": "HR", "phase": "onboarding", "status": "todo", "completed": False},
        {"title": f"准备{role}岗位资料和系统权限", "owner": "部门负责人", "phase": "onboarding", "status": "todo", "completed": False},
        {"title": "安排入职首日介绍和试用期目标沟通", "owner": "直属负责人", "phase": "hired", "status": "todo", "completed": False},
    ]


def _task_title(intent: str, candidate_fields: Mapping[str, Any]) -> str:
    if intent == "onboarding":
        return f"准备入职 Checklist：{candidate_fields['name']}"
    if intent == "interview_schedule":
        return f"安排面试：{candidate_fields['name']}"
    return f"筛选候选人：{candidate_fields['name']}"


def _draft_reply(intent: str, fields: Mapping[str, Any]) -> str:
    if intent == "onboarding":
        return f"您好，已收到入职相关信息。我们会先确认{fields['role']}岗位入职清单，人工核对后同步下一步材料和时间安排。"
    if intent == "interview_schedule":
        return f"您好，已收到面试沟通需求。我们会先核对{fields['role']}岗位安排，确认后同步可选时间。"
    return f"您好，已收到候选人信息。我们会先结合{fields['role']}岗位要求做初步匹配，并由 HR 确认后回复下一步安排。"
