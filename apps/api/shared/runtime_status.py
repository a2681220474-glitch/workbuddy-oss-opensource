from __future__ import annotations

import socket
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from apps.api.core.config import Settings, get_settings
from apps.api.db.session import engine
from apps.api.modules.background.status import read_runtime_jobs_status
from apps.api.modules.channels.stream_status import read_feishu_stream_status
from apps.api.shared.structured_logging import recent_log_status


def runtime_stack_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    database = database_runtime_status(active_settings)
    backup = backup_runtime_status(active_settings, database)
    redis = redis_runtime_status(active_settings)
    runtime_jobs_worker = read_runtime_jobs_status()
    background_jobs = background_job_status(active_settings, redis, runtime_jobs_worker)
    logs = recent_log_status()
    feishu_worker = read_feishu_stream_status()
    blocking_failures = [database]
    if background_jobs["enabled"]:
        blocking_failures.append(background_jobs)
    healthy = all(component.get("connected", component.get("ready", False)) for component in blocking_failures)
    return {
        "status": "ok" if healthy else "degraded",
        "timezone": "Asia/Shanghai",
        "database": database,
        "backup": backup,
        "redis": redis,
        "background_jobs": background_jobs,
        "logs": logs,
        "channels": {
            "real_im_adapters_enabled": active_settings.enable_real_im_adapters,
            "external_send_enabled": active_settings.enable_external_send,
            "feishu_worker": {
                "running": bool(feishu_worker.get("running")),
                "health_level": feishu_worker.get("health_level"),
                "health_message": feishu_worker.get("health_message"),
            },
        },
        "deployment": {
            "mode": deployment_mode(active_settings),
            "compose_services": ["api", "web", "feishu-worker", "runtime-jobs", "postgres", "redis"],
            "compose_up_command": "docker compose up --build",
            "compose_api_command": "docker compose up api web feishu-worker runtime-jobs postgres redis",
            "local_api_command": "uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000",
            "local_web_command": "npm --prefix apps/web run dev -- --host 0.0.0.0 --port 5173",
            "local_feishu_worker_command": "npm run services:start -- feishu-worker",
            "local_runtime_jobs_command": "npm run services:start -- workers",
            "backup_create_command": "npm run backup:create",
            "backup_verify_command": "npm run backup:verify -- <backup-path>",
            "backup_restore_plan_command": "npm run backup:restore-plan -- <backup-path>",
            "logs_tail_command": "npm run logs:tail",
            "logs_check_command": "npm run check:logs",
        },
    }


def database_runtime_status(settings: Settings) -> dict[str, Any]:
    backend = database_backend(settings.database_url)
    masked_url = mask_connection_url(settings.database_url)
    status: dict[str, Any] = {
        "backend": backend,
        "label": database_label(backend),
        "configured": bool(settings.database_url),
        "url_masked": masked_url,
        "persistence": database_persistence(settings.database_url),
        "connected": False,
        "status": "failed",
        "advice": None,
    }
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        status["connected"] = True
        status["status"] = "ok"
        status["advice"] = "数据库连接正常。"
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        status["error"] = str(exc)
        status["advice"] = database_failure_advice(backend)
    return status


def redis_runtime_status(settings: Settings) -> dict[str, Any]:
    url = settings.redis_url.strip()
    if not url:
        return {
            "configured": False,
            "connected": False,
            "status": "not_configured",
            "url_masked": "",
            "advice": (
                "当前使用 database_polling，Redis 不是本地后台任务的必需依赖。"
                if settings.background_queue_driver == "database_polling"
                else "尚未配置 REDIS_URL；当前队列驱动需要 Redis。"
            ),
        }
    parsed = urlparse(url)
    status: dict[str, Any] = {
        "configured": True,
        "connected": False,
        "status": "failed",
        "url_masked": mask_connection_url(url),
        "scheme": parsed.scheme or "redis",
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 6379,
        "db": parsed.path.lstrip("/") or "0",
        "advice": None,
    }
    try:
        response = redis_ping(parsed)
        status["connected"] = response == "PONG"
        status["status"] = "ok" if status["connected"] else "failed"
        status["advice"] = "Redis 连接正常。" if status["connected"] else "Redis 没有返回 PONG。"
        status["response"] = response
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        status["error"] = str(exc)
        status["advice"] = "请启动 Redis，或在 docker compose 环境下确认 redis service 已健康。"
    return status


def background_job_status(settings: Settings, redis_status: dict[str, Any], worker_status: dict[str, Any]) -> dict[str, Any]:
    enabled = settings.enable_background_jobs
    driver = settings.background_queue_driver
    dependency_ready = (
        True
        if driver == "database_polling"
        else bool(redis_status.get("connected"))
    )
    worker_ready = bool(worker_status.get("running")) and worker_status.get("health_level") == "ok"
    ready = (not enabled) or (dependency_ready and worker_ready)
    return {
        "enabled": enabled,
        "queue_driver": driver,
        "ready": ready,
        "status": "ok" if ready else "failed",
        "dependency_ready": dependency_ready,
        "worker": worker_status,
        "scheduled_jobs": [
            "approval_delivery_retry_scan",
            "sla_overdue_scan",
            "daily_report_generation",
        ],
        "advice": (
            "后台任务已启用且 worker 在线。"
            if ready and enabled
            else "后台任务当前关闭，仍依赖人工触发和前台操作。"
            if not enabled
            else "后台任务已启用，但依赖或 worker 尚未就绪，当前不能稳定执行重试和定时扫描。"
        ),
    }


def database_backend(database_url: str) -> str:
    prefix = database_url.split(":", 1)[0].lower()
    if prefix.startswith("postgresql"):
        return "postgresql"
    if prefix.startswith("sqlite"):
        return "sqlite"
    return prefix or "unknown"


def database_label(backend: str) -> str:
    if backend == "postgresql":
        return "PostgreSQL"
    if backend == "sqlite":
        return "SQLite"
    return backend


def database_persistence(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        normalized = database_url.replace("sqlite:///", "", 1)
        if normalized in {":memory:", ""}:
            return "in_memory"
        if Path(normalized).name.endswith(".db"):
            return "local_file"
        return "sqlite_path"
    if database_url.startswith("postgresql"):
        return "service"
    return "external"


def database_failure_advice(backend: str) -> str:
    if backend == "postgresql":
        return "请确认 PostgreSQL 已启动、DATABASE_URL 可达、账号密码正确。"
    if backend == "sqlite":
        return "请确认 SQLite 文件路径可写，且当前进程有访问权限。"
    return "请确认数据库连接串格式正确，且目标数据库可访问。"


def backup_runtime_status(settings: Settings, database: dict[str, Any]) -> dict[str, Any]:
    backup_dir = Path("apps/api/data/backups")
    latest = latest_backup_file(backup_dir)
    backend = database.get("backend") or database_backend(settings.database_url)
    return {
        "backend": backend,
        "backup_dir": str(backup_dir),
        "ready": bool(database.get("connected")),
        "status": "ok" if database.get("connected") else "blocked",
        "latest_backup": str(latest) if latest else None,
        "latest_backup_size_bytes": latest.stat().st_size if latest and latest.exists() else None,
        "create_command": "npm run backup:create",
        "verify_command": "npm run backup:verify -- <backup-path>",
        "restore_plan_command": "npm run backup:restore-plan -- <backup-path>",
        "restore_sqlite_command": "npm run backup:restore:sqlite -- <backup-path> --confirm",
        "advice": (
            "数据库已连接，可以创建和校验备份。"
            if database.get("connected")
            else "数据库未连接，暂时不能创建可靠备份。"
        ),
    }


def latest_backup_file(backup_dir: Path) -> Path | None:
    if not backup_dir.exists():
        return None
    candidates = [
        item
        for item in backup_dir.iterdir()
        if item.is_file() and item.suffix in {".db", ".dump", ".sql"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def deployment_mode(settings: Settings) -> str:
    if settings.database_url.startswith("postgresql") and settings.redis_url:
        return "docker_or_service"
    if settings.database_url.startswith("sqlite"):
        return "local_single_process"
    return "custom"


def mask_connection_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    if parsed.password is None and parsed.username is None:
        return value
    auth = parsed.username or ""
    if parsed.password is not None:
        auth = f"{auth}:***"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if auth:
        netloc = f"{auth}@{host}"
    else:
        netloc = host
    path = parsed.path or ""
    return parsed._replace(netloc=netloc, params="", query="", fragment="").geturl().replace("///", f"//{netloc}/", 1) if parsed.scheme == "sqlite" else parsed._replace(netloc=netloc).geturl()


def redis_ping(parsed) -> str:
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    timeout = 2.0
    with socket.create_connection((host, port), timeout=timeout) as raw_socket:
        connection: socket.socket
        if parsed.scheme == "rediss":
            context = ssl.create_default_context()
            connection = context.wrap_socket(raw_socket, server_hostname=host)
        else:
            connection = raw_socket
        auth_payload = redis_auth_payload(parsed)
        if auth_payload:
            connection.sendall(auth_payload)
            auth_response = read_redis_line(connection)
            if not auth_response.startswith("+OK"):
                raise ConnectionError(f"Redis AUTH failed: {auth_response}")
        connection.sendall(redis_command("PING"))
        response = read_redis_line(connection)
        if not response.startswith("+"):
            raise ConnectionError(f"Unexpected Redis response: {response}")
        return response[1:]


def redis_auth_payload(parsed) -> bytes | None:
    password = parsed.password
    username = parsed.username
    if password is None:
        return None
    if username:
        return redis_command("AUTH", username, password)
    return redis_command("AUTH", password)


def redis_command(*parts: str) -> bytes:
    encoded = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        item = part.encode("utf-8")
        encoded.append(f"${len(item)}\r\n".encode("utf-8"))
        encoded.append(item + b"\r\n")
    return b"".join(encoded)


def read_redis_line(connection: socket.socket) -> str:
    buffer = bytearray()
    while not buffer.endswith(b"\r\n"):
        chunk = connection.recv(1024)
        if not chunk:
            break
        buffer.extend(chunk)
    return buffer.decode("utf-8", errors="replace").strip()
