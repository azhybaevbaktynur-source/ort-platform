"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe } from "./courses";
import { readCachedMe as readCache, writeCachedMe as writeCache } from "./meCache";
import { LMS_ME_STALE_EVENT } from "./meStale";
import type { LmsApiError } from "./client";
import type { MeOut } from "./types";

interface LmsMeState {
  me: MeOut | null;
  loading: boolean;
  error: LmsApiError | null;
  reload: () => Promise<void>;
}

const LmsMeContext = createContext<LmsMeState | null>(null);

// The per-token cache of the answer lives in ./meCache (PERFORMANCE_AUDIT S1: the shell reads it at render time).

export function useLmsMeLoader(enabled: boolean): LmsMeState {
  const [fresh, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LmsApiError | null>(null);
  // `enabled` is false on the server and the first client render, so this cannot cause a hydration mismatch
  const me = fresh ?? (enabled ? readCache() : null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getMe();
      writeCache(next);
      setMe(next);
      setError(null);
    } catch (e) {
      if ((e as LmsApiError).status === 401) writeCache(null);
      setError(e as LmsApiError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) void reload();
  }, [enabled, reload]);

  // Owner feedback 2026-11-08 (item 2): a join or leave changes the areas, so the answer is asked again
  useEffect(() => {
    if (!enabled) return;
    const stale = () => { void reload(); };
    window.addEventListener(LMS_ME_STALE_EVENT, stale);
    return () => window.removeEventListener(LMS_ME_STALE_EVENT, stale);
  }, [enabled, reload]);

  return { me, loading, error, reload };
}

export const LmsMeProvider = LmsMeContext.Provider;

/** Current user's LMS profile (MeOut). Requires LmsShell (or another LmsMeProvider) above. */
export function useLmsMe(): LmsMeState {
  const ctx = useContext(LmsMeContext);
  if (!ctx) throw new Error("useLmsMe must be used within LmsShell");
  return ctx;
}
