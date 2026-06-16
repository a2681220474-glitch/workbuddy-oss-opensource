from __future__ import annotations

from apps.api.modules.adapters.dingtalk import DingTalkAdapter
from apps.api.modules.adapters.wecom import WeComAdapter


def skeleton_adapters() -> list[object]:
    return [WeComAdapter(), DingTalkAdapter()]
