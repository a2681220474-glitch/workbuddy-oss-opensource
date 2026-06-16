"""Rule-first Agent Router for WorkBuddy OSS Phase 0."""

from __future__ import annotations

import re
from typing import Any, Mapping

from ...shared.llm import LLMProvider, LLMRequest, get_llm_provider
from ...shared.prompts import get_prompt


SUPPORT_RULES: dict[str, dict[str, Any]] = {
    "refund_request": {
        "keywords": ["退款", "退货", "不要了", "取消订单", "refund", "return"],
        "priority": "urgent",
        "risk_level": "critical",
    },
    "complaint": {
        "keywords": ["投诉", "太差", "没人管", "骗人", "生气", "complaint"],
        "priority": "urgent",
        "risk_level": "critical",
    },
    "bug_report": {
        "keywords": ["报错", "打不开", "失败", "异常", "崩溃", "卡死", "bug", "error", "failed"],
        "priority": "high",
        "risk_level": "high",
    },
    "account_issue": {
        "keywords": ["登录不了", "登不上", "账号", "账户", "权限", "密码", "login", "account"],
        "priority": "high",
        "risk_level": "high",
    },
    "billing_issue": {
        "keywords": ["发票", "扣费", "续费", "账单", "付款失败", "invoice", "billing"],
        "priority": "high",
        "risk_level": "high",
    },
    "how_to_question": {
        "keywords": ["怎么用", "如何", "在哪里", "怎么设置", "教程", "how to"],
        "priority": "normal",
        "risk_level": "medium",
    },
    "feature_request": {
        "keywords": ["能不能加", "希望支持", "建议", "需求", "feature", "support"],
        "priority": "normal",
        "risk_level": "medium",
    },
}

SALES_RULES: dict[str, dict[str, Any]] = {
    "price_inquiry": {
        "keywords": ["多少钱", "价格", "报价", "收费", "费用", "套餐", "price", "pricing", "quote"],
        "stage": "qualified",
        "risk_level": "medium",
    },
    "demo_request": {
        "keywords": ["演示", "demo", "约个会", "介绍一下", "看一下系统"],
        "stage": "qualified",
        "risk_level": "medium",
    },
    "trial_request": {
        "keywords": ["试用", "体验", "账号试一下", "trial", "pilot"],
        "stage": "qualified",
        "risk_level": "medium",
    },
    "proposal_request": {
        "keywords": ["方案", "资料", "案例", "proposal", "deck", "case study"],
        "stage": "proposal",
        "risk_level": "medium",
    },
    "purchase_intent": {
        "keywords": ["采购", "购买", "合同", "下单", "预算", "buy", "contract"],
        "stage": "negotiation",
        "risk_level": "high",
    },
}

COMMUNITY_RULES: dict[str, dict[str, Any]] = {
    "high_intent_user": {
        "keywords": ["想买", "怎么买", "课程", "优惠名额", "报名", "购买", "下单", "价格", "优惠", "名额"],
        "risk_level": "medium",
    },
    "unanswered_question": {
        "keywords": ["有人吗", "没人回", "还没回复", "等一下", "怎么没有人", "请问"],
        "risk_level": "medium",
    },
    "complaint_or_risk": {
        "keywords": ["投诉", "退款", "骗人", "太差", "不满意", "没人管"],
        "risk_level": "high",
    },
    "activity_feedback": {
        "keywords": ["活动", "课程", "直播", "体验课", "训练营", "反馈"],
        "risk_level": "low",
    },
    "community_question": {
        "keywords": ["群里", "社群", "请问", "怎么", "能不能", "可以吗"],
        "risk_level": "low",
    },
}

COMMUNITY_CONTEXT_KEYWORDS = ["社群", "群里", "群内", "直播", "体验课", "训练营", "活动", "课程"]

RECRUITING_RULES: dict[str, dict[str, Any]] = {
    "resume_screening": {
        "keywords": ["简历", "候选人", "应聘", "求职", "工作经历", "项目经历"],
        "risk_level": "medium",
    },
    "interview_schedule": {
        "keywords": ["面试", "约面", "面谈", "候选时间", "HR沟通", "hr沟通"],
        "risk_level": "medium",
    },
    "onboarding": {
        "keywords": ["入职", "offer", "材料", "合同", "工位", "权限", "试用期"],
        "risk_level": "high",
    },
}

SYSTEM_COMMANDS = {"/help", "/report", "/pause", "/bind", "/settings"}


def route_message(message: Mapping[str, Any], llm_provider: LLMProvider | None = None) -> dict[str, Any]:
    """Route a normalized MessageEvent-like dictionary to a business agent."""

    text = _message_text(message)
    sender = str(message.get("sender_name") or message.get("sender") or "unknown")
    context = str(message.get("conversation_context") or message.get("conversation_title") or "")
    lowered = text.lower()

    if _is_system_command(lowered):
        command = lowered.split()[0]
        return _route(
            target_agent="system_command_agent",
            intent="system_command",
            confidence=0.98,
            risk_level="low",
            reason=f"Message starts with supported system command {command}.",
            entities={"command": command},
            requires_approval=False,
            matched_rules=[command],
        )

    forced_agent = str(message.get("conversation_bound_agent") or "")
    if forced_agent in {"support_ticket_agent", "sales_lead_agent", "community_ops_agent", "recruiting_hr_agent"}:
        return _route_for_bound_agent(forced_agent, text)

    support_match = _match_rule(text, SUPPORT_RULES)
    sales_match = _match_rule(text, SALES_RULES)
    community_match = _match_rule(text, COMMUNITY_RULES)
    recruiting_match = _match_rule(text, RECRUITING_RULES)

    if recruiting_match:
        sub_intent, rule = recruiting_match
        return _route(
            target_agent="recruiting_hr_agent",
            intent="recruiting_hr",
            confidence=_confidence_for_rule(text, rule["keywords"], base=0.76),
            risk_level=rule["risk_level"],
            reason=f"Matched recruiting rule {sub_intent}.",
            entities={
                "recruiting_intent": sub_intent,
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    if support_match and _wins_support(support_match, sales_match):
        sub_intent, rule = support_match
        return _route(
            target_agent="support_ticket_agent",
            intent="support_ticket",
            confidence=_confidence_for_rule(text, rule["keywords"], base=0.78),
            risk_level=rule["risk_level"],
            reason=f"Matched support rule {sub_intent}.",
            entities={
                "support_category": sub_intent,
                "priority": rule["priority"],
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    if community_match and (not sales_match or _has_community_context(text)):
        sub_intent, rule = community_match
        return _route(
            target_agent="community_ops_agent",
            intent="community_ops",
            confidence=_confidence_for_rule(text, rule["keywords"], base=0.72),
            risk_level=rule["risk_level"],
            reason=f"Matched community rule {sub_intent}.",
            entities={
                "community_intent": sub_intent,
                **_extract_common_entities(text),
            },
            requires_approval=sub_intent != "noise",
            matched_rules=[sub_intent],
        )

    if sales_match:
        sub_intent, rule = sales_match
        return _route(
            target_agent="sales_lead_agent",
            intent="sales_lead",
            confidence=_confidence_for_rule(text, rule["keywords"], base=0.76),
            risk_level=rule["risk_level"],
            reason=f"Matched sales rule {sub_intent}.",
            entities={
                "sales_intent": sub_intent,
                "suggested_stage": rule["stage"],
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    provider = llm_provider or get_llm_provider()
    prompt = get_prompt("router.intent.v1")
    request = LLMRequest(
        task="intent_classification",
        prompt=prompt.render(
            message_text=text,
            sender_name=sender,
            conversation_context=context,
        ),
        variables={
            "message_text": text,
            "sender_name": sender,
            "conversation_context": context,
        },
    )
    response = provider.generate(request)
    llm_route = response.content
    intent = str(llm_route.get("intent") or "chat")
    confidence = float(llm_route.get("confidence") or 0.4)
    target_agent = {
        "support_ticket": "support_ticket_agent",
        "sales_lead": "sales_lead_agent",
        "community_ops": "community_ops_agent",
        "recruiting_hr": "recruiting_hr_agent",
        "system_command": "system_command_agent",
    }.get(intent, "manual_inbox_agent")
    reason = str(llm_route.get("reason") or "LLM/mock fallback classification.")
    if confidence < 0.55 or target_agent == "manual_inbox_agent":
        target_agent = "manual_inbox_agent"
        intent = "manual_inbox"
        requires_approval = False
        reason = f"Low confidence LLM classification; send to human inbox. {reason}"
    else:
        requires_approval = bool(llm_route.get("requires_approval", True))

    return _route(
        target_agent=target_agent,
        intent=intent,
        confidence=confidence,
        risk_level=str(llm_route.get("risk_level") or "low"),
        reason=reason,
        entities=dict(llm_route.get("entities") or {}),
        requires_approval=requires_approval,
        matched_rules=[],
        classifier={
            "provider": response.provider,
            "model": response.model,
            "prompt": prompt.metadata(),
            "request": {
                "task": request.task,
                "variables": request.variables,
                "json_mode": request.json_mode,
            },
            "usage": response.usage,
            "raw": response.raw,
            "error": response.raw.get("error") if isinstance(response.raw, Mapping) else None,
        },
    )


def _route_for_bound_agent(target_agent: str, text: str) -> dict[str, Any]:
    if target_agent == "support_ticket_agent":
        support_match = _match_rule(text, SUPPORT_RULES)
        sub_intent = support_match[0] if support_match else "conversation_binding"
        rule = support_match[1] if support_match else {"priority": "normal", "risk_level": "medium", "keywords": []}
        return _route(
            target_agent="support_ticket_agent",
            intent="support_ticket",
            confidence=0.91 if support_match else 0.82,
            risk_level=str(rule["risk_level"]),
            reason="Conversation is bound to support_ticket_agent.",
            entities={
                "support_category": sub_intent,
                "priority": rule.get("priority", "normal"),
                "binding_override": True,
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    if target_agent == "community_ops_agent":
        community_match = _match_rule(text, COMMUNITY_RULES)
        sub_intent = community_match[0] if community_match else "conversation_binding"
        rule = community_match[1] if community_match else {"risk_level": "medium", "keywords": []}
        return _route(
            target_agent="community_ops_agent",
            intent="community_ops",
            confidence=0.9 if community_match else 0.8,
            risk_level=str(rule["risk_level"]),
            reason="Conversation is bound to community_ops_agent.",
            entities={
                "community_intent": sub_intent,
                "binding_override": True,
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    if target_agent == "recruiting_hr_agent":
        recruiting_match = _match_rule(text, RECRUITING_RULES)
        sub_intent = recruiting_match[0] if recruiting_match else "conversation_binding"
        rule = recruiting_match[1] if recruiting_match else {"risk_level": "medium", "keywords": []}
        return _route(
            target_agent="recruiting_hr_agent",
            intent="recruiting_hr",
            confidence=0.9 if recruiting_match else 0.8,
            risk_level=str(rule["risk_level"]),
            reason="Conversation is bound to recruiting_hr_agent.",
            entities={
                "recruiting_intent": sub_intent,
                "binding_override": True,
                **_extract_common_entities(text),
            },
            requires_approval=True,
            matched_rules=[sub_intent],
        )

    sales_match = _match_rule(text, SALES_RULES)
    sub_intent = sales_match[0] if sales_match else "conversation_binding"
    rule = sales_match[1] if sales_match else {"stage": "new", "risk_level": "medium", "keywords": []}
    return _route(
        target_agent="sales_lead_agent",
        intent="sales_lead",
        confidence=0.91 if sales_match else 0.82,
        risk_level=str(rule["risk_level"]),
        reason="Conversation is bound to sales_lead_agent.",
        entities={
            "sales_intent": sub_intent,
            "suggested_stage": rule.get("stage", "new"),
            "binding_override": True,
            **_extract_common_entities(text),
        },
        requires_approval=True,
        matched_rules=[sub_intent],
    )


def _message_text(message: Mapping[str, Any]) -> str:
    for key in ("text", "content", "message_text", "body"):
        value = message.get(key)
        if value is not None:
            return str(value).strip()
    raw = message.get("raw_payload")
    if isinstance(raw, Mapping):
        return str(raw.get("text") or raw.get("content") or "").strip()
    return ""


def _is_system_command(lowered_text: str) -> bool:
    return any(lowered_text.startswith(command) for command in SYSTEM_COMMANDS)


def _has_community_context(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in COMMUNITY_CONTEXT_KEYWORDS)


def _match_rule(text: str, rules: Mapping[str, Mapping[str, Any]]) -> tuple[str, Mapping[str, Any]] | None:
    lowered = text.lower()
    best: tuple[str, Mapping[str, Any], int] | None = None
    for name, rule in rules.items():
        hits = sum(1 for keyword in rule["keywords"] if keyword.lower() in lowered)
        if hits and (best is None or hits > best[2]):
            best = (name, rule, hits)
    if best is None:
        return None
    return best[0], best[1]


def _wins_support(
    support_match: tuple[str, Mapping[str, Any]] | None,
    sales_match: tuple[str, Mapping[str, Any]] | None,
) -> bool:
    if support_match is None:
        return False
    if sales_match is None:
        return True
    support_intent = support_match[0]
    return support_intent in {"refund_request", "complaint", "bug_report", "account_issue"}


def _confidence_for_rule(text: str, keywords: list[str], base: float) -> float:
    lowered = text.lower()
    hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
    length_bonus = 0.04 if len(text) >= 20 else 0.0
    return min(0.96, base + hits * 0.06 + length_bonus)


def _extract_common_entities(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    money = re.search(r"(\d+(?:\.\d+)?\s*(?:万|元|块|k|K|w|W|rmb|RMB))", text)
    if money:
        entities["budget"] = money.group(1)

    products = []
    product_keywords = ["AI客服", "AI 客服", "WorkBuddy", "企微", "飞书", "钉钉", "CRM", "工单"]
    for keyword in product_keywords:
        if keyword.lower() in text.lower():
            products.append(keyword)
    if products:
        entities["product"] = products[0]
        entities["mentioned_products"] = products

    customer = re.search(r"([\u4e00-\u9fa5]{1,4}(?:总|先生|女士|老师))", text)
    if customer:
        entities["customer_name"] = customer.group(1)

    return entities


def _route(
    *,
    target_agent: str,
    intent: str,
    confidence: float,
    risk_level: str,
    reason: str,
    entities: dict[str, Any],
    requires_approval: bool,
    matched_rules: list[str],
    classifier: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "target_agent": target_agent,
        "intent": intent,
        "confidence": round(confidence, 2),
        "risk_level": risk_level,
        "reason": reason,
        "entities": entities,
        "requires_approval": requires_approval,
        "matched_rules": matched_rules,
        "classifier": classifier or {"provider": "rules", "model": "keyword_rules", "prompt": None},
    }
