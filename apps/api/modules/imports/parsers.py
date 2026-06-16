from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from apps.api.schemas import ImportRecord


def parse_csv_records(content: bytes) -> list[ImportRecord]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    records: list[ImportRecord] = []
    for row in reader:
        records.append(record_from_mapping(row, default_channel="local_csv"))
    return records


def record_from_mapping(row: dict[str, Any], default_channel: str = "local") -> ImportRecord:
    raw_timestamp = first_present(row, "timestamp", "time", "created_at", "received_at")
    timestamp = parse_timestamp(raw_timestamp)
    text = first_present(row, "text", "message", "content", "body") or ""
    sender_name = first_present(row, "sender_name", "sender", "user", "from") or "未知用户"
    conversation_id = first_present(row, "conversation_id", "chat_id", "room_id", "group_id") or "demo-conversation"

    return ImportRecord(
        text=str(text),
        sender_name=str(sender_name),
        sender_external_id=nullable_str(first_present(row, "sender_external_id", "sender_id", "user_id")),
        timestamp=timestamp,
        conversation_id=str(conversation_id),
        conversation_name=str(first_present(row, "conversation_name", "chat_name", "room_name", "group_name") or conversation_id),
        conversation_type=str(first_present(row, "conversation_type", "chat_type") or "group"),
        channel=str(first_present(row, "channel", "platform") or default_channel),
        message_type=str(first_present(row, "message_type", "type") or "text"),
        external_message_id=nullable_str(first_present(row, "external_message_id", "message_id", "msg_id")),
        raw_payload={key: value for key, value in row.items()},
    )


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def nullable_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None
