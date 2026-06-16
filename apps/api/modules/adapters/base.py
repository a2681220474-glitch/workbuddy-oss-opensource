from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from apps.api.schemas import ImportRecord


@dataclass
class AdapterCapabilities:
    receive_event: bool = False
    normalize_message: bool = False
    send_message: bool = False
    resolve_user: bool = False
    resolve_conversation: bool = False


@dataclass
class AdapterResult:
    kind: str
    record: ImportRecord | None = None
    reason: str | None = None
    raw: dict[str, Any] | None = None


class ChannelAdapter(Protocol):
    channel: str
    label: str
    capabilities: AdapterCapabilities

    def receive_event(self, payload: dict[str, Any]) -> AdapterResult:
        ...

    def normalize_message(self, payload: dict[str, Any]) -> ImportRecord:
        ...

    def send_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        ...

    def resolve_user(self, external_user_id: str) -> dict[str, Any] | None:
        ...

    def resolve_conversation(self, external_conversation_id: str) -> dict[str, Any] | None:
        ...


class NotImplementedChannelAdapter:
    channel = "unknown"
    label = "未实现渠道"
    capabilities = AdapterCapabilities()

    def receive_event(self, payload: dict[str, Any]) -> AdapterResult:
        return AdapterResult(kind="ignored", reason=f"{self.label} adapter is skeleton-only.", raw=payload)

    def normalize_message(self, payload: dict[str, Any]) -> ImportRecord:
        raise NotImplementedError(f"{self.label} normalize_message is not implemented.")

    def send_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        return {
            "sent": False,
            "mode": "mock",
            "channel": self.channel,
            "conversation_id": conversation_id,
            "text": text,
            "reason": f"{self.label} real send is not implemented in v0.4.0.",
        }

    def resolve_user(self, external_user_id: str) -> dict[str, Any] | None:
        return None

    def resolve_conversation(self, external_conversation_id: str) -> dict[str, Any] | None:
        return None
