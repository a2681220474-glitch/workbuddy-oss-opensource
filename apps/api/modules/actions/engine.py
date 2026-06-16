"""Action Engine that converts routes into structured business actions."""

from __future__ import annotations

from typing import Any, Mapping

from ..scenarios.community import build_community_actions
from ..scenarios.recruiting import build_recruiting_actions
from ..scenarios.sales import build_sales_actions
from ..scenarios.support import build_support_actions


class ActionEngine:
    """Dispatch target agents to scenario action builders."""

    def build(self, message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
        target_agent = route.get("target_agent")
        intent = route.get("intent")

        if target_agent == "support_ticket_agent" or intent == "support_ticket":
            return build_support_actions(message, route)
        if target_agent == "sales_lead_agent" or intent == "sales_lead":
            return build_sales_actions(message, route)
        if target_agent == "community_ops_agent" or intent == "community_ops":
            return build_community_actions(message, route)
        if target_agent == "recruiting_hr_agent" or intent == "recruiting_hr":
            return build_recruiting_actions(message, route)
        if target_agent == "system_command_agent":
            return self._system_command_result(message, route)
        return self._chat_result(message, route)

    def _system_command_result(
        self,
        message: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> dict[str, Any]:
        command = (route.get("entities") or {}).get("command")
        return {
            "agent_name": "system_command_agent",
            "prompt": None,
            "analysis": {"command": command, "confidence": route.get("confidence", 0.98)},
            "actions": [
                {
                    "action_type": "send_internal_report"
                    if command == "/report"
                    else "request_missing_info",
                    "priority": "low",
                    "requires_approval": False,
                    "reason": "Local system command handling for Phase 0.",
                    "business_object": {
                        "type": "internal_command",
                        "fields": {
                            "command": command,
                            "source_message_id": message.get("id") or message.get("message_id"),
                        },
                    },
                    "next_steps": ["在后台展示命令处理结果"],
                }
            ],
        }

    def _chat_result(self, message: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "agent_name": str(route.get("target_agent") or "manual_inbox_agent"),
            "prompt": None,
            "analysis": {
                "confidence": route.get("confidence", 0.4),
                "reason": route.get("reason"),
                "no_business_object_created": True,
            },
            "actions": [
                {
                    "action_type": "escalate_to_human",
                    "priority": "low",
                    "requires_approval": False,
                    "reason": "No confident Phase 0 business intent; keep message in human inbox.",
                    "business_object": {
                        "type": "human_inbox_item",
                        "fields": {
                            "source_message_id": message.get("id") or message.get("message_id"),
                            "reason": route.get("reason"),
                        },
                    },
                    "next_steps": ["人工判断是否需要创建工单或线索"],
                }
            ],
        }
