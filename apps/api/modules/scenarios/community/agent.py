"""Private community operations scenario agent for v0.8 Alpha."""

from __future__ import annotations

from typing import Any, Mapping


def build_community_actions(message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    text = _message_text(message)
    entities = dict(route.get("entities") or {})
    community_intent = str(entities.get("community_intent") or "community_question")
    priority = _priority_for(community_intent)
    summary = text[:500] or "社群消息需要运营跟进"
    draft_reply = _draft_reply(community_intent)

    task_title = _task_title(community_intent, text)
    actions: list[dict[str, Any]] = [
        {
            "action_type": "create_community_task",
            "priority": priority,
            "requires_approval": False,
            "reason": f"Community route detected {community_intent}; create an operations follow-up task.",
            "business_object": {
                "type": "task",
                "fields": {
                    "title": task_title,
                    "status": "todo",
                    "task_type": "community_followup",
                    "related_object_type": "community",
                    "source_message_id": message.get("id") or message.get("message_id"),
                    "summary": summary,
                    "due_hint": "今天" if priority == "high" else "本周",
                },
            },
            "next_steps": ["运营确认是否需要回复", "标记高意向或风险", "纳入群日报"],
        },
        {
            "action_type": "include_in_daily_report",
            "priority": "low",
            "requires_approval": False,
            "reason": "Important community messages should be summarized in the group daily report.",
            "business_object": {
                "type": "report_signal",
                "fields": {
                    "report_type": "community_daily",
                    "intent": community_intent,
                    "source_message_id": message.get("id") or message.get("message_id"),
                    "summary": summary,
                },
            },
            "next_steps": ["生成群日报时引用此消息"],
        },
    ]

    if community_intent in {"high_intent_user", "activity_feedback"}:
        actions.append(
            {
                "action_type": "create_lead",
                "priority": priority,
                "requires_approval": False,
                "reason": "Community message shows possible sales or conversion intent.",
                "business_object": {
                    "type": "lead",
                    "fields": {
                        "customer_name": message.get("sender_name") or "社群用户",
                        "interest": "社群高意向用户",
                        "stage": "potential",
                        "score": 55 if community_intent == "high_intent_user" else 40,
                        "source_excerpt": summary,
                        "suggested_next_action": "运营或销售跟进社群高意向用户",
                    },
                },
                "next_steps": ["确认用户需求", "分配运营或销售跟进"],
            }
        )

    if community_intent in {"community_question", "unanswered_question"}:
        actions.append(
            {
                "action_type": "add_to_knowledge_base",
                "priority": "normal",
                "requires_approval": False,
                "reason": "Potential repeated community question; capture as a knowledge gap candidate.",
                "business_object": {
                    "type": "knowledge_gap",
                    "fields": {
                        "question": summary,
                        "category": "community",
                        "suggested_answer": draft_reply,
                        "source_message_id": message.get("id") or message.get("message_id"),
                    },
                },
                "next_steps": ["人工确认标准答案", "采纳为知识条目"],
            }
        )

    if community_intent != "noise":
        actions.append(
            {
                "action_type": "send_draft_to_approval",
                "priority": priority,
                "requires_approval": True,
                "reason": "Community-facing reply should be reviewed before sending.",
                "business_object": {
                    "type": "approval",
                    "fields": {
                        "approval_type": "external_reply",
                        "channel": message.get("channel") or message.get("source_platform") or "local_import",
                        "conversation_id": message.get("conversation_id"),
                        "draft_reply": draft_reply,
                        "related_object_type": "task",
                        "related_object_hint": task_title,
                    },
                },
                "draft_reply": draft_reply,
                "next_steps": ["运营审核回复", "必要时编辑后发送"],
            }
        )

    return {
        "agent_name": "community_ops_agent",
        "prompt": {"key": "community.ops.v1", "version": "v0.8-alpha"},
        "analysis": {
            "community_intent": community_intent,
            "priority": priority,
            "summary": summary,
            "draft_reply": draft_reply,
            "confidence": route.get("confidence", 0.7),
        },
        "actions": actions,
    }


def _message_text(message: Mapping[str, Any]) -> str:
    return str(message.get("text") or message.get("content") or message.get("message_text") or "").strip()


def _priority_for(intent: str) -> str:
    if intent in {"complaint_or_risk", "unanswered_question"}:
        return "high"
    if intent in {"high_intent_user", "activity_feedback"}:
        return "normal"
    return "low"


def _task_title(intent: str, text: str) -> str:
    labels = {
        "community_question": "社群问题待回复",
        "high_intent_user": "社群高意向用户跟进",
        "complaint_or_risk": "社群风险消息处理",
        "unanswered_question": "未回复问题补跟进",
        "activity_feedback": "活动反馈整理",
        "noise": "社群消息观察",
    }
    return f"{labels.get(intent, '社群运营任务')}：{text[:24] or '待确认'}"


def _draft_reply(intent: str) -> str:
    if intent == "high_intent_user":
        return "您好，看到您对这个方向比较感兴趣。我先帮您记录需求，人工确认后给您补充更具体的方案和下一步建议。"
    if intent == "complaint_or_risk":
        return "您好，已收到您的反馈。我们会先由人工同事核实情况，并尽快给您一个明确处理结果。"
    if intent == "unanswered_question":
        return "您好，刚看到您的问题，我们先记录下来并确认准确答案，稍后给您回复。"
    if intent == "activity_feedback":
        return "感谢反馈，我们会把这条建议纳入活动复盘，并由运营同事确认后同步后续安排。"
    return "您好，问题已收到。我先帮您记录，确认后给您回复。"
