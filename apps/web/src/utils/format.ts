import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import type { EntityId } from "../types";

dayjs.extend(utc);
dayjs.extend(timezone);

export function formatTime(value?: string) {
  if (!value) return "-";
  const trimmed = String(value).trim();
  const hasExplicitZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
  const parsed = hasExplicitZone ? dayjs(trimmed) : dayjs.tz(trimmed, "Asia/Shanghai");
  return parsed.isValid() ? parsed.tz("Asia/Shanghai").format("YYYY-MM-DD HH:mm") : value;
}

export function entityKey(value?: EntityId, fallback?: string | number) {
  return String(value ?? fallback ?? crypto.randomUUID());
}

export function shortText(value?: string, max = 72) {
  if (!value) return "-";
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

export function statusColor(status?: string) {
  const normalized = status?.toLowerCase();
  if (!normalized) return "default";
  if (["approved", "sent", "closed", "qualified", "done", "success", "accepted", "published", "hired", "healthy"].includes(normalized)) return "green";
  if (["pending", "pending_review", "open", "new", "needs_review"].includes(normalized)) return "blue";
  if (["edited", "in_progress", "waiting_customer", "contacted", "screening", "interview", "offer", "onboarding", "draft", "archive_suggested"].includes(normalized)) return "gold";
  if (["rejected", "failed", "high", "critical", "urgent", "expired", "needs_optimization"].includes(normalized)) return "red";
  return "default";
}
