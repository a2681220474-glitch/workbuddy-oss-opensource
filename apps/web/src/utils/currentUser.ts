import type { LocalUser } from "../types";

const STORAGE_KEY = "workbuddy.last_auth_user";

interface StoredUser {
  username?: string;
  display_name?: string;
  role?: string;
}

export function getStoredWorkBuddyUser(): StoredUser | undefined {
  if (typeof window === "undefined") return undefined;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return undefined;
  try {
    return JSON.parse(raw) as StoredUser;
  } catch {
    return undefined;
  }
}

export function getStoredWorkBuddyUserDisplayName() {
  const user = getStoredWorkBuddyUser();
  return user?.display_name || user?.username || "本地管理员";
}

export function getStoredWorkBuddyUsername() {
  return getStoredWorkBuddyUser()?.username || "";
}

export function getStoredWorkBuddyUserRole() {
  return getStoredWorkBuddyUser()?.role || "admin";
}

export function canOperateApprovals(role = getStoredWorkBuddyUserRole()) {
  return role === "admin" || role === "approver";
}

export function canWriteProcessingRecords(role = getStoredWorkBuddyUserRole()) {
  return role !== "readonly";
}

export function setStoredWorkBuddyUser(user?: LocalUser | StoredUser | null) {
  if (typeof window === "undefined") return;
  if (!user) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
    username: user.username,
    display_name: user.display_name,
    role: user.role
  }));
}
