"""Prompt registry for rule-first Agent Runtime metadata."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    version: str
    description: str
    template: str

    def render(self, **variables: Any) -> str:
        allowed = {field_name for _, field_name, _, _ in Formatter().parse(self.template) if field_name}
        safe_variables = {key: variables.get(key, "") for key in allowed}
        return self.template.format(**safe_variables)

    def metadata(self) -> dict[str, str]:
        return {
            "key": self.key,
            "version": self.version,
            "description": self.description,
        }


PROMPTS: dict[str, PromptTemplate] = {
    "router.intent.v1": PromptTemplate(
        key="router.intent.v1",
        version="2026-05-20.phase0",
        description="Classify normalized IM messages into WorkBuddy business intents.",
        template=(
            "You are WorkBuddy OSS, an enterprise IM message analyst.\n"
            "Message: {message_text}\n"
            "Sender: {sender_name}\n"
            "Conversation context: {conversation_context}\n"
            "Return JSON with intent, confidence, risk_level, requires_approval, entities, reason."
        ),
    ),
    "support.ticket.v1": PromptTemplate(
        key="support.ticket.v1",
        version="2026-05-20.phase0",
        description="Extract a support ticket and cautious external reply draft.",
        template=(
            "You are a support ticket analyst.\n"
            "Customer message: {message_text}\n"
            "History: {conversation_history}\n"
            "Return JSON for ticket category, priority, missing_info, suggested_reply."
        ),
    ),
    "sales.lead.v1": PromptTemplate(
        key="sales.lead.v1",
        version="2026-05-20.phase0",
        description="Extract a sales lead, score, next action, and external reply draft.",
        template=(
            "You are a sales operations analyst.\n"
            "Conversation: {conversation_text}\n"
            "Return JSON for customer, company, interest, pain_points, budget, score, next_action."
        ),
    ),
}


def get_prompt(key: str) -> PromptTemplate:
    try:
        return PROMPTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt key: {key}") from exc


def render_prompt(key: str, **variables: Any) -> str:
    return get_prompt(key).render(**variables)
