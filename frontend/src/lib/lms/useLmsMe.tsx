"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getStudentView } from "@/lib/api";
import { getMe } from "./courses";
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

/*
 * UX rework 2: every area has its own layout, so moving between areas mounts a new shell. The last answer is kept per
 * token (memory + this tab's sessionStorage) and shown at once while a fresh one loads, so the header never loses an
 * area on the way. It only draws the menu: every permission is decided by the server on each request.
 */
const CACHE_KEY = "ort_lms_me";
let memory: { token: string; me: MeOut } | null = null;

/** The end of the token in use: tells whose answer is cached, and is useless as a credential. */
function activeToken(): string {
  if (typeof window === "undefined") return "";
  return (getStudentView()?.token ?? window.localStorage.getItem("ort_token") ?? "").slice(-16);
}

function readCache(): MeOut | null {
  const token = activeToken();
  if (!token) return null;
  if (memory?.token === token) return memory.me;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    const saved = raw ? (JSON.parse(raw) as { token?: string; me?: MeOut }) : null;
    if (saved?.token === token && saved.me) {
      memory = { token, me: saved.me };
      return saved.me;
    }
  } catch { /* storage blocked or a bad value: load normally */ }
  return null;
}

function writeCache(me: MeOut | null): void {
  const token = activeToken();
  memory = me && token ? { token, me } : null;
  try {
    if (memory) window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(memory));
    else window.sessionStorage.removeItem(CACHE_KEY);
  } catch { /* the cache is optional */ }
}

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
