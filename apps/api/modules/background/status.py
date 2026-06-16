from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.api.core.config import get_settings
from apps.api.models import BEIJING_TZ
from apps.api.modules.channels.stream_status import append_recent, is_process_running, parse_datetime


def read_runtime_jobs_status() -> dict[str, Any]:
    path = status_path()
    if not path.exists():
        return enrich_runtime_jobs_status(
            {
                "status": "not_started",
                "running": False,
                "status_path": str(path),
                "message": "Runtime jobs worker has not written a status file yet.",
            }
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return enrich_runtime_jobs_status(
            {
                "status": "unknown",
                "running": False,
                "status_path": str(path),
                "message": f"Failed to read runtime jobs status: {exc}",
            }
        )
    pid = data.get("pid")
    running = is_process_running(pid)
    data["running"] = running
    data["status_path"] = str(path)
    if data.get("status") in {"starting", "running"} and not running:
        data["status"] = "stopped"
    return enrich_runtime_jobs_status(data)


def write_runtime_jobs_status(status: str, **extra: Any) -> None:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    append_cycle = extra.pop("append_cycle", None)
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
        payload["recent_cycles"] = []
        payload["recent_errors"] = []
    if heartbeat:
        payload["heartbeat_count"] = int(payload.get("heartbeat_count") or 0) + 1
        payload["last_heartbeat_at"] = now
    if append_cycle:
        payload["recent_cycles"] = append_recent(previous.get("recent_cycles"), append_cycle)
        payload["last_success_at"] = append_cycle.get("occurred_at") or payload.get("last_success_at")
    if append_error:
        payload["recent_errors"] = append_recent(previous.get("recent_errors"), append_error)
        payload["last_failure_at"] = append_error.get("occurred_at") or now
        payload["last_error"] = append_error.get("error")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def status_path() -> Path:
    return Path(get_settings().background_jobs_status_path)


def enrich_runtime_jobs_status(data: dict[str, Any]) -> dict[str, Any]:
    running = bool(data.get("running"))
    status = str(data.get("status") or "unknown")
    updated_at = parse_datetime(data.get("last_heartbeat_at") or data.get("updated_at"))
    seconds_since_heartbeat = None
    if updated_at is not None:
        seconds_since_heartbeat = int((datetime.now(BEIJING_TZ) - updated_at).total_seconds())
    stale = seconds_since_heartbeat is not None and seconds_since_heartbeat > 120
    if running and not stale and status == "running":
        health_level = "ok"
        health_message = "后台任务 worker 正在运行，可自动扫描失败发送和逾期任务。"
    elif status == "failed":
        health_level = "error"
        health_message = "后台任务 worker 启动或运行失败，请查看错误并重启。"
    elif not running:
        health_level = "offline"
        health_message = "后台任务 worker 当前不在线，自动扫描不会执行。"
    elif stale:
        health_level = "warning"
        health_message = "后台任务 worker 心跳较旧，建议确认进程是否仍在运行。"
    else:
        health_level = "offline"
        health_message = "后台任务 worker 当前不在线，自动扫描不会执行。"
    data.update(
        {
            "health_level": health_level,
            "health_message": health_message,
            "seconds_since_heartbeat": seconds_since_heartbeat,
            "last_heartbeat_at": data.get("last_heartbeat_at") or data.get("updated_at"),
            "recent_cycles": data.get("recent_cycles") if isinstance(data.get("recent_cycles"), list) else [],
            "recent_errors": data.get("recent_errors") if isinstance(data.get("recent_errors"), list) else [],
            "run_command": "npm run services:start -- workers",
            "compose_command": "docker compose up runtime-jobs",
            "check_command": "npm run check:background-jobs",
            "recovery_steps": [
                "先确认配置中心里的后台任务开关已开启。",
                "运行 npm run check:background-jobs 检查后台任务 worker 配置。",
                "本地运行 npm run services:start -- workers，由服务管理器负责自动重启；Docker 方式运行 docker compose up runtime-jobs。",
                "回到配置中心确认后台任务 worker 在线，并检查最近扫描记录是否更新。",
            ],
        }
    )
    return data
