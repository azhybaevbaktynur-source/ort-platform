"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Sends a cheap request as soon as an auth page opens, so a sleeping backend (Render free tier)
 * and database (Neon autosuspend) start waking up while the user is still typing.
 */
export function useBackendWarmup() {
  useEffect(() => {
    fetch("/api/v1/auth/ping", { cache: "no-store" }).catch(() => {});
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
