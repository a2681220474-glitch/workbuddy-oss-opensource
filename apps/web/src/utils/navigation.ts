import type { EntityId } from "../types";

export type NavTarget =
  | "dashboard"
  | "import"
  | "messages"
  | "objects"
  | "audit"
  | "team"
  | "approvals"
  | "tickets"
  | "community"
  | "leads"
  | "tasks"
  | "candidates"
  | "knowledge"
  | "reports"
  | "demo"
  | "config"
  | "conversations"
  | "feishu-conversations"
  | "channel-events"
  | "adapter-test"
  | "feishu"
  | "wecom"
  | "agent-runs";

const validTargets = new Set<NavTarget>([
  "dashboard",
  "import",
  "messages",
  "objects",
  "audit",
  "team",
  "approvals",
  "tickets",
  "community",
  "leads",
  "tasks",
  "candidates",
  "knowledge",
  "reports",
  "demo",
  "config",
  "conversations",
  "feishu-conversations",
  "channel-events",
  "adapter-test",
  "feishu",
  "wecom",
  "agent-runs"
]);

export function parseHashNavigation(hash = window.location.hash): { target: NavTarget; id?: string } {
  const raw = hash.replace(/^#/, "");
  if (!raw) return { target: "dashboard" };
  const [path, queryString = ""] = raw.split("?");
  const target = path === "feishu-conversations"
    ? "conversations"
    : validTargets.has(path as NavTarget) ? (path as NavTarget) : "dashboard";
  const id = new URLSearchParams(queryString).get("id") ?? undefined;
  return { target, id };
}

export function currentHashId(hash = window.location.hash) {
  return parseHashNavigation(hash).id;
}

export function hashTarget(target: NavTarget, id?: EntityId) {
  const encodedId = id === undefined || id === null ? "" : `?id=${encodeURIComponent(String(id))}`;
  return `#${target}${encodedId}`;
}

export function navigateTo(target: NavTarget, id?: EntityId) {
  window.location.hash = hashTarget(target, id);
}

export function isTargetId(rowId: EntityId | undefined, targetId?: string) {
  return targetId !== undefined && rowId !== undefined && String(rowId) === targetId;
}
