from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.api.core.config import get_settings
from apps.api.models import BEIJING_TZ


def read_feishu_stream_status() -> dict[str, Any]:
    path = status_path()
    if not path.exists():
        return enrich_stream_status({
            "status": "not_started",
            "running": False,
            "status_path": str(path),
            "message": "Feishu stream worker has not written a status file yet.",
        })

    try:
        data = read_status_payload(path)
    except (OSError, json.JSONDecodeError) as exc:
        return enrich_stream_status({
            "status": "unknown",
            "running": False,
            "status_path": str(path),
            "message": f"Failed to read Feishu stream status: {exc}",
        })

    pid = data.get("pid")
    running = is_process_running(pid)
    data["running"] = running
    data["status_path"] = str(path)
    if data.get("status") in {"starting", "running"} and not running:
        data["status"] = "stopped"
    return enrich_stream_status(data)


def write_feishu_stream_status(status: str, **extra: Any) -> None:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = read_status_payload(path) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    append_event = extra.pop("append_event", None)
    append_error = extra.pop("append_error", None)
    heartbeat = bool(extra.pop("heartbeat", False))
    now = datetime.now(BEIJING_TZ).isoformat()
    payload = {
        **previous,
        "status": status,
        "pid": os.getpid(),
        "updated_at": now,
        **extra,
    }
    if status == "starting":
        payload["started_at"] = now
        payload["heartbeat_count"] = 0
        payload["recent_events"] = []
        payload["recent_errors"] = []
    if heartbeat:
        payload["heartbeat_count"] = int(payload.get("heartbeat_count") or 0) + 1
        payload["last_heartbeat_at"] = now
    if append_event:
        payload["recent_events"] = append_recent(previous.get("recent_events"), append_event)
        payload["last_success_at"] = append_event.get("occurred_at") if append_event.get("status") == "success" else payload.get("last_success_at")
    if append_error:
        payload["recent_errors"] = append_recent(previous.get("recent_errors"), append_error)
        payload["last_failure_at"] = append_error.get("occurred_at") or now
        payload["last_error"] = append_error.get("error")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def status_path() -> Path:
    return Path(get_settings().feishu_stream_status_path)


def read_status_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_recent(current: Any, item: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    items = current if isinstance(current, list) else []
    return [item, *items][:limit]


def is_process_running(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def enrich_stream_status(data: dict[str, Any]) -> dict[str, Any]:
    running = bool(data.get("running"))
    status = str(data.get("status") or "unknown")
    updated_at = parse_datetime(data.get("last_heartbeat_at") or data.get("updated_at"))
    seconds_since_heartbeat = None
    if updated_at is not None:
        seconds_since_heartbeat = int((datetime.now(BEIJING_TZ) - updated_at).total_seconds())
    stale = seconds_since_heartbeat is not None and seconds_since_heartbeat > 120
    if running and not stale and status == "running":
        health_level = "ok"
        health_message = "飞书长连接正在运行，可以接收真实消息。"
    elif status == "failed":
        health_level = "error"
        health_message = "飞书 worker 启动或运行失败，请查看错误并重新启动。"
    elif not running:
        health_level = "offline"
        health_message = "飞书 worker 当前不在线，真实消息不会实时进入系统。"
    elif stale:
        health_level = "warning"
        health_message = "飞书 worker 心跳较旧，建议确认进程是否仍在接收事件。"
    else:
        health_level = "offline"
        health_message = "飞书 worker 当前不在线，真实消息不会实时进入系统。"
    data.update({
        "health_level": health_level,
        "health_message": health_message,
        "receiving_real_messages": running and status == "running" and not stale,
        "seconds_since_heartbeat": seconds_since_heartbeat,
        "last_heartbeat_at": data.get("last_heartbeat_at") or data.get("updated_at"),
        "last_error": data.get("error") or data.get("last_error"),
        "last_failure_at": data.get("last_failure_at"),
        "last_success_at": data.get("last_success_at"),
        "recent_events": data.get("recent_events") if isinstance(data.get("recent_events"), list) else [],
        "recent_errors": data.get("recent_errors") if isinstance(data.get("recent_errors"), list) else [],
        "run_command": "npm run services:start -- feishu-worker",
        "compose_command": "docker compose up feishu-worker",
        "check_command": "npm run check:feishu-stream",
        "recovery_steps": [
            "在项目根目录确认配置中心的飞书 App ID / Secret 已保存。",
            "运行 npm run check:feishu-stream 做配置检查。",
            "本地运行 npm run services:start -- feishu-worker，由服务管理器负责自动重启；Docker 方式运行 docker compose up feishu-worker。",
            "回到配置中心确认 Worker 在线，并发送一条飞书测试消息验证最近消息时间。",
        ],
    })
    return data


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(BEIJING_TZ)
