"""Support ticket scenario agent for Phase 0."""

from __future__ import annotations

from typing import Any, Mapping

from ....shared.prompts import get_prompt


CATEGORY_LABELS = {
    "bug_report": "故障反馈",
    "complaint": "客户投诉",
    "refund_request": "退款退货",
    "how_to_question": "使用咨询",
    "feature_request": "功能建议",
    "account_issue": "账号权限",
    "billing_issue": "账单发票",
    "other": "客服问题",
}

DEFAULT_MISSING_INFO = {
    "bug_report": ["复现步骤", "报错截图", "使用环境"],
    "account_issue": ["账号手机号或邮箱", "报错截图"],
    "billing_issue": ["订单号或付款凭证", "发票抬头信息"],
    "refund_request": ["订单号", "退款原因", "购买时间"],
    "complaint": ["具体问题时间", "相关截图或记录"],
}


def build_support_actions(message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    text = _message_text(message)
    entities = dict(route.get("entities") or {})
    category = str(entities.get("support_category") or "other")
    priority = str(entities.get("priority") or _priority_for_category(category))
    summary = _summarize_problem(text, category)
    title = _title_for(category, text)
    missing_info = DEFAULT_MISSING_INFO.get(category, [])
    draft_reply = _draft_reply(category, missing_info)
    prompt = get_prompt("support.ticket.v1")

    ticket_fields = {
        "source_message_id": message.get("id") or message.get("message_id"),
        "title": title,
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"]),
        "priority": priority,
        "status": "open",
        "customer_name": entities.get("customer_name") or message.get("sender_name"),
        "customer_external_id": message.get("sender_external_id"),
        "product": entities.get("product"),
        "description": summary,
        "missing_info": missing_info,
        "source_excerpt": text[:500],
    }

    actions = [
        {
            "action_type": "create_ticket",
            "priority": priority,
            "requires_approval": False,
            "reason": f"Support route detected {category}; create an internal ticket.",
            "business_object": {"type": "ticket", "fields": ticket_fields},
            "draft_reply": draft_reply,
            "next_steps": [
                "创建客服工单",
                "补充必要信息",
                "将回复草稿送入审批队列",
            ],
        },
        {
            "action_type": "send_draft_to_approval",
            "priority": priority,
            "requires_approval": True,
            "reason": "External customer-facing support reply must be approved before sending.",
            "business_object": {
                "type": "approval",
                "fields": {
                    "approval_type": "external_reply",
                    "channel": message.get("channel") or message.get("source_platform") or "local_import",
                    "conversation_id": message.get("conversation_id"),
                    "draft_reply": draft_reply,
                    "related_object_type": "ticket",
                    "related_object_hint": title,
                },
            },
            "draft_reply": draft_reply,
            "next_steps": ["人工审核回复", "编辑后发送", "记录审批结果"],
        },
    ]

    return {
        "agent_name": "support_ticket_agent",
        "prompt": prompt.metadata(),
        "analysis": {
            "should_create_ticket": True,
            "category": category,
            "priority": priority,
            "title": title,
            "problem_summary": summary,
            "missing_info": missing_info,
            "suggested_reply": draft_reply,
            "knowledge_gap": category in {"bug_report", "feature_request", "other"},
            "confidence": route.get("confidence", 0.75),
        },
        "actions": actions,
    }


def _message_text(message: Mapping[str, Any]) -> str:
    return str(message.get("text") or message.get("content") or message.get("message_text") or "").strip()


def _priority_for_category(category: str) -> str:
    if category in {"refund_request", "complaint"}:
        return "urgent"
    if category in {"bug_report", "account_issue", "billing_issue"}:
        return "high"
    return "normal"


def _title_for(category: str, text: str) -> str:
    label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
    clean = " ".join(text.split())
    if not clean:
        return label
    return f"{label}: {clean[:24]}"


def _summarize_problem(text: str, category: str) -> str:
    if text:
        return text[:800]
    return f"Imported message routed to {CATEGORY_LABELS.get(category, CATEGORY_LABELS['other'])}."


def _draft_reply(category: str, missing_info: list[str]) -> str:
    if category == "refund_request":
        return "您好，已收到您的退款诉求。我们会先核对订单和服务记录，请您补充订单号和退款原因，人工确认后尽快给您处理方案。"
    if category == "complaint":
        return "您好，非常抱歉给您带来不好的体验。我们已记录为高优先级问题，会由人工同事核实具体情况后尽快回复您。"
    if category == "bug_report":
        return "您好，我先帮您记录这个故障问题。方便补充复现步骤、报错截图和使用环境吗？我们会尽快排查。"
    if category == "account_issue":
        return "您好，我先帮您排查账号或权限问题。方便提供账号手机号或邮箱，以及当前页面的报错截图吗？"
    if category == "billing_issue":
        return "您好，账单/发票问题已收到。方便补充订单号、付款凭证或发票抬头信息吗？我们核对后再回复您。"
    if category == "how_to_question":
        return "您好，已收到您的使用问题。我会先整理一版操作说明，人工确认无误后发给您。"
    if category == "feature_request":
        return "您好，感谢您的建议。我们会先记录为产品反馈，并由人工同事评估后同步后续进展。"
    if missing_info:
        return f"您好，问题已收到。为便于处理，麻烦补充：{', '.join(missing_info)}。"
    return "您好，消息已收到，我们会先记录并由人工同事确认后回复您。"
