from __future__ import annotations

from typing import Any

from apps.api.modules.adapters.base import AdapterCapabilities, AdapterResult, NotImplementedChannelAdapter


class DingTalkAdapter(NotImplementedChannelAdapter):
    channel = "dingtalk"
    label = "钉钉"
    capabilities = AdapterCapabilities(receive_event=True, normalize_message=True)

    def receive_event(self, payload: dict[str, Any]) -> AdapterResult:
        return AdapterResult(kind="message", reason="钉钉 payload 可进入本地标准化与 Agent 流水线，平台验签/解密待真实账号联调。", raw=payload)
