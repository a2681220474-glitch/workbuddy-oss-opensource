from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.api.models import BEIJING_TZ


DEFAULT_LOG_DIR = Path("apps/api/data/logs")


def configure_service_logging(service: str, log_dir: str | Path | None = None) -> Path:
    target_dir = Path(log_dir or os.getenv("WORKBUDDY_LOG_DIR") or DEFAULT_LOG_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / f"{service}.jsonl"
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(isinstance(handler, JsonLineFileHandler) and handler.log_path == log_path for handler in logger.handlers):
        logger.addHandler(JsonLineFileHandler(log_path, service))
    if not any(getattr(handler, "_workbuddy_console", False) for handler in logger.handlers):
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        console._workbuddy_console = True  # type: ignore[attr-defined]
        logger.addHandler(console)
    return log_path


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"workbuddy_event": event, "workbuddy_fields": sanitize(fields)})


class JsonLineFileHandler(logging.Handler):
    def __init__(self, log_path: Path, service: str) -> None:
        super().__init__(level=logging.INFO)
        self.log_path = log_path
        self.service = service
        self.max_bytes = max(1, int(os.getenv("WORKBUDDY_STRUCTURED_LOG_MAX_BYTES", str(5 * 1024 * 1024))))
        self.backup_count = max(1, int(os.getenv("WORKBUDDY_STRUCTURED_LOG_BACKUPS", "3")))

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "ts": datetime.now(BEIJING_TZ).isoformat(),
            "service": self.service,
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "workbuddy_event", record.getMessage()),
            "message": record.getMessage(),
            "fields": sanitize(getattr(record, "workbuddy_fields", {})),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        if self.log_path.exists() and self.log_path.stat().st_size + len(encoded) > self.max_bytes:
            self.rotate()
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(encoded.decode("utf-8"))

    def rotate(self) -> None:
        oldest = self.log_path.with_name(f"{self.log_path.name}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.log_path.with_name(f"{self.log_path.name}.{index}")
            if source.exists():
                source.replace(self.log_path.with_name(f"{self.log_path.name}.{index + 1}"))
        if self.log_path.exists():
            self.log_path.replace(self.log_path.with_name(f"{self.log_path.name}.1"))


def recent_log_status(log_dir: str | Path | None = None) -> dict[str, Any]:
    target_dir = Path(log_dir or os.getenv("WORKBUDDY_LOG_DIR") or DEFAULT_LOG_DIR)
    files: list[dict[str, Any]] = []
    if target_dir.exists():
        for item in sorted(target_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True):
            stat = item.stat()
            files.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "size_bytes": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime, BEIJING_TZ).isoformat(),
                }
            )
    return {
        "log_dir": str(target_dir),
        "ready": target_dir.exists(),
        "files": files[:12],
        "tail_command": "npm run logs:tail",
        "check_command": "npm run check:logs",
        "advice": "日志目录已就绪，可查看 API、worker 和后台任务结构化日志。" if target_dir.exists() else "日志目录尚未创建，启动 API 或 worker 后会自动创建。",
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in ("secret", "token", "key", "password", "authorization")):
                sanitized[str(key)] = "***"
            else:
                sanitized[str(key)] = sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value[:50]]
    return value
