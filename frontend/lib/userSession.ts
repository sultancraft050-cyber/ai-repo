"use client";

import type { SavedBuild, SaudiBuildOption, UserAccount } from "@/types/builder";

const GUEST_ID_KEY = "pc_builder_guest_id";
const USER_KEY = "pc_builder_user";
const RECENT_BUILDS_KEY = "pc_builder_recent_builds";

export type UserIdentity = {
  user_id?: string | null;
  guest_id: string;
  user?: UserAccount | null;
};

export function getGuestId(): string {
  if (typeof window === "undefined") return "guest-server";
  const existing = window.localStorage.getItem(GUEST_ID_KEY);
  if (existing) return existing;
  const next = `guest-${crypto.randomUUID()}`;
  window.localStorage.setItem(GUEST_ID_KEY, next);
  return next;
}

export function getStoredUser(): UserAccount | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserAccount;
  } catch {
    return null;
  }
}

export function setStoredUser(user: UserAccount | null): void {
  if (typeof window === "undefined") return;
  if (!user) {
    window.localStorage.removeItem(USER_KEY);
    return;
  }
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getIdentity(): UserIdentity {
  const user = getStoredUser();
  return {
    user_id: user?.user_id ?? null,
    guest_id: getGuestId(),
    user
  };
}

export function rememberRecentBuild(build: SaudiBuildOption): void {
  if (typeof window === "undefined") return;
  const existing = getRecentBuilds();
  const next = [
    {
      build_id: `local-${Date.now()}`,
      title: build.title,
      region: "SA",
      build_mode: build.label,
      total_price_sar: build.summary.total_recommended_price_sar,
      confidence_level: build.summary.confidence_level,
      warning_summary: build.summary.warning_summary,
      component_ids: build.components.map((component) => component.product_id),
      price_snapshot_ids: [],
      build_summary: build.summary as unknown as Record<string, unknown>,
      build_payload: build as unknown as Record<string, unknown>,
      share_slug: "",
      public_visibility: false,
      favorite: false
    } as SavedBuild,
    ...existing
  ].slice(0, 8);
  window.localStorage.setItem(RECENT_BUILDS_KEY, JSON.stringify(next));
}

export function getRecentBuilds(): SavedBuild[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(RECENT_BUILDS_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as SavedBuild[];
  } catch {
    return [];
  }
}

