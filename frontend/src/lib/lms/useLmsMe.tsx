"use client";

import { createContext, useCallback, useContext, useEffect } from "react";
import { BOOTSTRAP_KEY, BOOTSTRAP_OPTIONS, fetchBootstrap, reloadBootstrap, type BootstrapOut } from "./bootstrap";
import { readCachedMe as readCache, writeCachedMe as writeCache } from "./meCache";
import { LMS_ME_STALE_EVENT } from "./meStale";
import { useCached } from "./swr";
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
  // PERFORMANCE_AUDIT S2 (§5.2): MeOut is the `me` of `GET /me/bootstrap`, read through the SWR cache (one request for
  // the whole shell, shared with the student shell's data and the banners; fresh for a minute, then refreshed in the
  // background while the cached answer stays on screen)
  const boot = useCached<BootstrapOut>(enabled ? BOOTSTRAP_KEY : null, fetchBootstrap, BOOTSTRAP_OPTIONS);
  const error = (boot.error as LmsApiError | null) ?? null;
  // `enabled` is false on the server and the first client render, so this cannot cause a hydration mismatch
  const me = boot.data?.me ?? (enabled ? readCache() : null);
  const loading = enabled && !boot.data && !error;

  // S1's render-time cache (`meCache`) follows every answer; a 401 forgets it
  const fresh = boot.data?.me ?? null;
  useEffect(() => {
    if (fresh) writeCache(fresh);
  }, [fresh]);
  const status = error?.status;
  useEffect(() => {
    if (status === 401) writeCache(null);
  }, [status]);

  const reload = useCallback(async () => {
    try { await reloadBootstrap(); } catch { /* the error is the cache's, shown by the shell */ }
  }, []);

  // Owner feedback 2026-11-08 (item 2): a join or leave changes the areas (and the student's courses), so the answer
  // is asked again
  useEffect(() => {
    if (!enabled) return;
    const stale = () => { void reload(); };
    window.addEventListener(LMS_ME_STALE_EVENT, stale);
    return () => window.removeEventListener(LMS_ME_STALE_EVENT, stale);
  }, [enabled, reload]);

  return { me, loading, error, reload };
}

export const LmsMeProvider = LmsMeContext.Provider;

/** True inside LmsShell (or another LmsMeProvider): the shell's bootstrap is there to read. */
export function useInLmsShell(): boolean {
  return useContext(LmsMeContext) !== null;
}

/** Current user's LMS profile (MeOut). Requires LmsShell (or another LmsMeProvider) above. */
export function useLmsMe(): LmsMeState {
  const ctx = useContext(LmsMeContext);
  if (!ctx) throw new Error("useLmsMe must be used within LmsShell");
  return ctx;
}
