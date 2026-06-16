"""Sales lead scenario agent for Phase 0."""

from __future__ import annotations

import re
from typing import Any, Mapping

from ....shared.prompts import get_prompt


def build_sales_actions(message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    text = _message_text(message)
    entities = dict(route.get("entities") or {})
    sales_intent = str(entities.get("sales_intent") or "sales_consulting")
    lead_fields = _extract_lead_fields(text, message, entities, sales_intent)
    draft_reply = _draft_reply(sales_intent, lead_fields)
    prompt = get_prompt("sales.lead.v1")

    actions = [
        {
            "action_type": "create_lead",
            "priority": _priority_for_score(lead_fields["score"]),
            "requires_approval": False,
            "reason": f"Sales route detected {sales_intent}; create a structured lead.",
            "business_object": {"type": "lead", "fields": lead_fields},
            "draft_reply": draft_reply,
            "next_steps": [
                "创建销售线索",
                "记录客户痛点和预算",
                "将外部回复草稿送入审批队列",
            ],
        },
        {
            "action_type": "create_followup_task",
            "priority": _priority_for_score(lead_fields["score"]),
            "requires_approval": False,
            "reason": "Sales leads need an explicit next follow-up task.",
            "business_object": {
                "type": "task",
                "fields": {
                    "title": lead_fields["suggested_next_action"],
                    "status": "todo",
                    "related_object_type": "lead",
                    "due_hint": lead_fields.get("next_followup_time"),
                    "source_message_id": message.get("id") or message.get("message_id"),
                },
            },
            "next_steps": ["提醒销售跟进", "补充公司规模和预算", "推进到下一销售阶段"],
        },
        {
            "action_type": "send_draft_to_approval",
            "priority": _priority_for_score(lead_fields["score"]),
            "requires_approval": True,
            "reason": "External sales reply may imply pricing or commitment and must be approved.",
            "business_object": {
                "type": "approval",
                "fields": {
                    "approval_type": "external_reply",
                    "channel": message.get("channel") or message.get("source_platform") or "local_import",
                    "conversation_id": message.get("conversation_id"),
                    "draft_reply": draft_reply,
                    "related_object_type": "lead",
                    "related_object_hint": lead_fields.get("customer_name") or lead_fields.get("company"),
                },
            },
            "draft_reply": draft_reply,
            "next_steps": ["人工审核回复", "确认报价或承诺", "记录审批结果"],
        },
    ]

    return {
        "agent_name": "sales_lead_agent",
        "prompt": prompt.metadata(),
        "analysis": {
            "sales_intent": sales_intent,
            "confidence": route.get("confidence", 0.75),
            **lead_fields,
        },
        "actions": actions,
    }


def _message_text(message: Mapping[str, Any]) -> str:
    return str(message.get("text") or message.get("content") or message.get("message_text") or "").strip()


def _extract_lead_fields(
    text: str,
    message: Mapping[str, Any],
    entities: Mapping[str, Any],
    sales_intent: str,
) -> dict[str, Any]:
    score, scoring_reasons = _score(text, entities, sales_intent)
    company = _extract_company(text)
    customer_name = entities.get("customer_name") or message.get("sender_name") or _extract_customer(text)
    interest = entities.get("product") or _extract_interest(text) or "待确认产品/方案"
    pain_points = _extract_pain_points(text)
    budget = entities.get("budget") or _extract_budget(text)
    next_followup_time = _extract_followup_time(text)
    stage = entities.get("suggested_stage") or ("qualified" if score >= 50 else "potential")

    return {
        "source_message_id": message.get("id") or message.get("message_id"),
        "customer_name": customer_name,
        "company": company,
        "interest": interest,
        "pain_points": pain_points,
        "budget": budget,
        "stage": stage,
        "score": score,
        "score_reasons": scoring_reasons,
        "urgency_level": "high" if score >= 70 else "medium" if score >= 40 else "low",
        "decision_role": "decision_maker" if customer_name and str(customer_name).endswith("总") else "unknown",
        "objections": _extract_objections(text),
        "next_followup_time": next_followup_time,
        "suggested_next_action": _next_action(sales_intent, interest, budget),
        "source_excerpt": text[:500],
    }


def _score(text: str, entities: Mapping[str, Any], sales_intent: str) -> tuple[int, list[str]]:
    score = 10
    reasons = ["基础销售咨询 +10"]
    lowered = text.lower()
    scoring_rules = [
        (["采购", "购买", "下单", "buy"], 40, "明确购买意向"),
        (["演示", "demo"], 30, "要求演示"),
        (["试用", "体验", "trial"], 30, "要求试用"),
        (["多少钱", "价格", "报价", "收费", "price", "quote"], 20, "询问价格"),
        (["方案", "资料", "案例", "proposal", "case"], 15, "索要资料/案例"),
        (["预算"], 20, "提到预算"),
        (["下周", "明天", "今天", "月底", "周三", "下午"], 20, "提到时间点"),
        (["竞品", "对比"], -5, "提到竞品"),
        (["太贵", "暂时不用", "没预算"], -10, "存在异议"),
    ]
    for keywords, delta, reason in scoring_rules:
        if any(keyword.lower() in lowered for keyword in keywords):
            score += delta
            reasons.append(f"{reason} {delta:+d}")
    if entities.get("customer_name"):
        score += 10
        reasons.append("识别到客户称呼 +10")
    if entities.get("budget"):
        score += 20
        reasons.append("识别到预算 +20")
    if sales_intent == "purchase_intent":
        score += 10
        reasons.append("采购/合同意向 +10")
    return max(0, min(100, score)), reasons


def _extract_budget(text: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+)?\s*(?:万|元|块|k|K|w|W|rmb|RMB))", text)
    return match.group(1) if match else None


def _extract_customer(text: str) -> str | None:
    match = re.search(r"([\u4e00-\u9fa5]{1,4}(?:总|先生|女士|老师))", text)
    return match.group(1) if match else None


def _extract_company(text: str) -> str | None:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:公司|集团|教育|科技|咨询|律所))", text)
    return match.group(1) if match else None


def _extract_interest(text: str) -> str | None:
    for keyword in ["AI客服方案", "AI 客服方案", "企微接入", "工单系统", "销售助手", "WorkBuddy"]:
        if keyword.lower() in text.lower():
            return keyword
    return None


def _extract_pain_points(text: str) -> list[str]:
    pain_points = []
    candidates = {
        "客服人手不够": ["客服人手不够", "回复不过来", "客服压力"],
        "需要接入企微": ["接企微", "企微接入", "企业微信"],
        "需要本地部署": ["私有化", "本地部署", "数据安全"],
        "销售跟进难": ["线索", "跟进", "CRM"],
    }
    lowered = text.lower()
    for label, keywords in candidates.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            pain_points.append(label)
    return pain_points


def _extract_objections(text: str) -> list[str]:
    objections = []
    if "太贵" in text or "贵" in text:
        objections.append("价格顾虑")
    if "没预算" in text:
        objections.append("预算不足")
    if "对比" in text or "竞品" in text:
        objections.append("正在比较竞品")
    return objections


def _extract_followup_time(text: str) -> str | None:
    for keyword in ["今天", "明天", "后天", "下周", "周一", "周二", "周三", "周四", "周五", "月底"]:
        if keyword in text:
            return keyword
    return None


def _next_action(sales_intent: str, interest: str, budget: str | None) -> str:
    if sales_intent == "demo_request":
        return f"预约演示并确认客户场景：{interest}"
    if sales_intent == "trial_request":
        return f"确认试用范围并准备开通说明：{interest}"
    if sales_intent == "proposal_request":
        return f"发送方案/案例资料并约下一次沟通：{interest}"
    if sales_intent == "price_inquiry":
        return f"确认团队规模后准备报价说明：{interest}"
    if budget:
        return f"围绕预算 {budget} 准备版本建议和下一步推进计划"
    return f"补充客户规模、预算和决策时间：{interest}"


def _draft_reply(sales_intent: str, lead_fields: Mapping[str, Any]) -> str:
    interest = lead_fields.get("interest") or "方案"
    if sales_intent == "price_inquiry":
        return f"您好，关于{interest}我可以先整理一版报价说明。为避免给错版本，方便补充团队规模、使用场景和预计上线时间吗？"
    if sales_intent == "demo_request":
        return f"您好，可以安排{interest}演示。方便告诉我您希望重点看哪些流程，以及本周合适的时间段吗？"
    if sales_intent == "trial_request":
        return f"您好，可以先评估试用范围。方便补充团队人数、主要使用场景和希望试用的功能吗？"
    if sales_intent == "proposal_request":
        return f"您好，我先准备{interest}相关资料和案例，人工确认后发您一版更贴近场景的说明。"
    return f"您好，已收到您对{interest}的咨询。我先记录需求，确认后给您回复下一步建议。"


def _priority_for_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "normal"
    return "low"
