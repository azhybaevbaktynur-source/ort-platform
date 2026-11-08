"use client";

import { useSyncExternalStore } from "react";
import { getStudentView } from "@/lib/api";
import type { MeOut } from "./types";

/*
 * UX rework 2: every area has its own layout, so moving between areas mounts a new shell. The last `/me/lms` answer is
 * kept per token (memory + this tab's sessionStorage) and shown at once while a fresh one loads, so the header never
 * loses an area on the way. It only draws the menu: every permission is decided by the server on each request.
 *
 * PERFORMANCE_AUDIT §5.1 (S1): moved out of `useLmsMe.tsx` so the shell can read it synchronously at render time
 * (`useCachedMe`, hydration-safe) and decide its frame once, before anything is drawn.
 */
const CACHE_KEY = "ort_lms_me";
let memory: { token: string; me: MeOut } | null = null;
const listeners = new Set<() => void>();

/** The end of the token in use: tells whose answer is cached, and is useless as a credential. */
function activeToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return (getStudentView()?.token ?? window.localStorage.getItem("ort_token") ?? "").slice(-16);
  } catch {
    return "";
  }
}

/** The cached `/me/lms` answer of the signed-in user (this tab), or null. Safe to call on the server (null). */
export function readCachedMe(): MeOut | null {
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

/** Stores (or, with null, forgets) the answer for the token in use. */
export function writeCachedMe(me: MeOut | null): void {
  const token = activeToken();
  memory = me && token ? { token, me } : null;
  try {
    if (memory) window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(memory));
    else window.sessionStorage.removeItem(CACHE_KEY);
  } catch { /* the cache is optional */ }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/**
 * The cached answer at render time: null on the server and during hydration (no mismatch), the cached value from
 * the render right after hydration on.
 */
export function useCachedMe(): MeOut | null {
  return useSyncExternalStore(subscribe, readCachedMe, () => null);
}
