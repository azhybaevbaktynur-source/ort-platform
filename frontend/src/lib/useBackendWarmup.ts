"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "@/lib/apiBase";

/**
 * Sends a cheap request as soon as an auth page opens, so a sleeping backend (Render free tier)
 * and database (Neon autosuspend) start waking up while the user is still typing.
 * Goes to the backend origin directly (API_BASE_URL; CSP connect-src allows it), not through the Vercel rewrite,
 * which was 3-9x slower (PERFORMANCE_AUDIT.md 10.2 item 5). Unset NEXT_PUBLIC_API_URL (local dev): "/api/v1" as before.
 */
export function useBackendWarmup() {
  useEffect(() => {
    fetch(`${API_BASE_URL}/auth/ping`, { cache: "no-store" }).catch(() => {});
  }, []);
}

/** True once `busy` has lasted longer than `afterMs` (used to explain a slow first login). */
export function useSlowHint(busy: boolean, afterMs = 4000): boolean {
  const [slow, setSlow] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (busy) {
      timer.current = setTimeout(() => setSlow(true), afterMs);
    } else {
      setSlow(false);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [busy, afterMs]);
  return slow;
}
