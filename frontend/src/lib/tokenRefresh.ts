"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { API_BASE_URL } from "@/lib/apiBase";
import { getStudentView } from "@/lib/api";

/**
 * Rolling sessions (PHASE_11_DESIGN 5.2). Tokens live 3 days; a token older than 12 h is swapped for a new one when a page
 * opens, so an exam started after any page cannot run out of token. Checked on every navigation, not only on a full load:
 * a tab left open for days reaches the exam by client-side navigation.
 *
 * Never inside the player: an exam makes no request it does not need. Never with the tab's test student: this is the real
 * account's token, read directly from storage, so the Student view token can never land in `ort_token`. A failure changes
 * nothing: the old token stays valid until it expires, and the backend checks it on every call.
 */
const TOKEN_KEY = "ort_token";
const REFRESH_AFTER_MS = 12 * 60 * 60 * 1000;
const RETRY_AFTER_MS = 10 * 60 * 1000;
const START_DELAY_MS = 1500; // the page's own requests go first; leaving for the player within this time cancels it
const PLAYER_PATH = /\/attempts\/[^/]+\/?$/; // not `/attempts/{id}/result`, not the list of attempts

let lastTry = 0;

function claimsOf(token: string): { exp?: number; iat?: number } | null {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part));
  } catch {
    return null;
  }
}

/** A token issued before this release has no `iat`: it is old by definition, and refreshing it gives it one. */
function needsRefresh(token: string, now: number): boolean {
  const claims = claimsOf(token);
  if (!claims || typeof claims.exp !== "number" || claims.exp * 1000 <= now) return false;
  return typeof claims.iat !== "number" || now - claims.iat * 1000 >= REFRESH_AFTER_MS;
}

async function refresh(token: string): Promise<void> {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return;
    const data = (await res.json()) as { access_token?: string };
    // Only if the session is still the one we asked for: signing out or in meanwhile wins.
    if (data.access_token && localStorage.getItem(TOKEN_KEY) === token) localStorage.setItem(TOKEN_KEY, data.access_token);
  } catch {
    // no connection or no storage: try again on a later page
  }
}

export function TokenRefresh(): null {
  const pathname = usePathname();
  useEffect(() => {
    if (PLAYER_PATH.test(pathname || "") || getStudentView()) return;
    const timer = setTimeout(() => {
      const now = Date.now();
      if (now - lastTry < RETRY_AFTER_MS) return;
      let token: string | null = null;
      try {
        token = localStorage.getItem(TOKEN_KEY);
      } catch {
        return;
      }
      if (!token || !needsRefresh(token, now)) return;
      lastTry = now;
      void refresh(token);
    }, START_DELAY_MS);
    return () => clearTimeout(timer);
  }, [pathname]);
  return null;
}
