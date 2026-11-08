"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

/*
 * PERFORMANCE_AUDIT §5.2 (slice S2): a small stale-while-revalidate cache, no library. A fresh answer is returned at
 * once; a stale one is returned at once and asked again in the background; two callers of the same key share one
 * request. Kept per token (memory, and this tab's sessionStorage for `storage: "session"`), like `useLmsMe`'s cache:
 * another token sees nothing of it; a 401 or sign-out (`clearAll`) clears everything. It only saves requests: every
 * request is still authorised by the server. Never for attempts, grades or content (they must stay exact).
 *
 * Dependency-free apart from React (checked by `swr.check.ts` in node); the environment can be replaced for that.
 */

export interface SwrOptions {
  /** Milliseconds an answer counts as fresh (default 30 s). */
  ttl?: number;
  /** "session" also keeps the answer in this tab's sessionStorage (survives a reload); default "memory". */
  storage?: "session" | "memory";
}

export interface SwrEntry<T = unknown> {
  value: T;
  at: number;
  ttl: number;
  session: boolean;
}

export interface SwrEnv {
  now: () => number;
  /** The end of the token in use (whose answers these are); "" without one. */
  token: () => string;
  storage: () => Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
}

const SESSION_KEY = "ort_swr_v1";
const DEFAULT_TTL = 30_000;

// The same rule as `useLmsMe` / `api.getAuthHeader`: Student view's token wins over the signed-in one.
function defaultToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const sv = window.sessionStorage.getItem("studentView");
    const svToken = sv ? (JSON.parse(sv) as { token?: string }).token : undefined;
    return (svToken ?? window.localStorage.getItem("ort_token") ?? "").slice(-16);
  } catch {
    return "";
  }
}

let env: SwrEnv = {
  now: () => Date.now(),
  token: defaultToken,
  storage: () => (typeof window === "undefined" ? null : window.sessionStorage),
};

interface Store {
  token: string;
  entries: Record<string, SwrEntry>;
}

let store: Store | null = null;
const inflight = new Map<string, Promise<unknown>>();
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

function current(): Store {
  const token = env.token();
  if (store?.token === token) return store;
  inflight.clear(); // answers asked under another token never land in this one
  let entries: Record<string, SwrEntry> = {};
  try {
    const raw = env.storage()?.getItem(SESSION_KEY);
    const saved = raw ? (JSON.parse(raw) as Partial<Store>) : null;
    if (token && saved?.token === token && saved.entries) entries = saved.entries;
  } catch { /* storage blocked or a bad value: start empty */ }
  store = { token, entries };
  return store;
}

function persist(s: Store) {
  const kept: Record<string, SwrEntry> = {};
  for (const [k, e] of Object.entries(s.entries)) if (e.session) kept[k] = e;
  try {
    const st = env.storage();
    if (!st) return;
    if (s.token && Object.keys(kept).length) st.setItem(SESSION_KEY, JSON.stringify({ token: s.token, entries: kept }));
    else st.removeItem(SESSION_KEY);
  } catch { /* the cache is optional */ }
}

function isStale(e: SwrEntry): boolean {
  return env.now() - e.at > e.ttl;
}

/** The stored entry of `key` (fresh or stale), or null. Stable until the entry changes (a `useSyncExternalStore` snapshot). */
export function peek<T>(key: string): SwrEntry<T> | null {
  return (current().entries[key] as SwrEntry<T> | undefined) ?? null;
}

/** Stores `value` under `key` (an answer obtained another way, e.g. from a mutation). */
export function put<T>(key: string, value: T, opts: SwrOptions = {}): void {
  const s = current();
  s.entries = { ...s.entries, [key]: { value, at: env.now(), ttl: opts.ttl ?? DEFAULT_TTL, session: opts.storage === "session" } };
  persist(s);
  notify();
}

function load<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions): Promise<T> {
  const running = inflight.get(key);
  if (running) return running as Promise<T>;
  const token = current().token;
  const p: Promise<T> = fetcher().then(
    (value) => {
      // dropped by `invalidate` / `clearAll` or a token change meanwhile: the caller gets it, the cache does not
      if (inflight.get(key) === p && current().token === token) {
        inflight.delete(key);
        put(key, value, opts);
      }
      return value;
    },
    (err: unknown) => {
      if (inflight.get(key) === p) inflight.delete(key);
      if ((err as { status?: number } | null)?.status === 401) clearAll();
      throw err;
    },
  );
  inflight.set(key, p);
  return p;
}

/**
 * The answer of `key`: the stored one at once when fresh; when stale, the stored one at once and a background refetch;
 * otherwise `fetcher()` (shared with any request of the same key already running).
 */
export function cached<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions = {}): Promise<T> {
  const e = peek<T>(key);
  if (e) {
    if (isStale(e)) load(key, fetcher, opts).catch(() => { /* the stale answer stays */ });
    return Promise.resolve(e.value);
  }
  return load(key, fetcher, opts);
}

/** Asks again now whatever is stored (shared with a request of the same key already running). */
export function revalidate<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions = {}): Promise<T> {
  return load(key, fetcher, opts);
}

/** Drops every entry (and running request) whose key starts with `prefix`; subscribers re-read. */
export function invalidate(prefix: string): void {
  const s = current();
  const entries = { ...s.entries };
  let changed = false;
  for (const k of Object.keys(entries)) {
    if (k.startsWith(prefix)) { delete entries[k]; changed = true; }
  }
  for (const k of Array.from(inflight.keys())) if (k.startsWith(prefix)) inflight.delete(k);
  if (!changed) return;
  s.entries = entries;
  persist(s);
  notify();
}

/**
 * Keeps the entries whose key starts with `prefix` (they are still shown) but makes them stale, so the next read asks
 * again; running requests of those keys were asked before the change and are dropped. For answers the frame draws
 * (`bootstrap`): dropping them would blank the shell for a moment.
 */
export function markStale(prefix: string): void {
  for (const k of Array.from(inflight.keys())) if (k.startsWith(prefix)) inflight.delete(k);
  const s = current();
  let changed = false;
  const entries: Record<string, SwrEntry> = {};
  for (const [k, e] of Object.entries(s.entries)) {
    if (k.startsWith(prefix) && e.at !== 0) { entries[k] = { ...e, at: 0 }; changed = true; } else entries[k] = e;
  }
  if (!changed) return;
  s.entries = entries;
  persist(s);
  notify();
}

/** Sign-out or a 401: nothing cached survives. */
export function clearAll(): void {
  inflight.clear();
  const s = current();
  s.entries = {};
  persist(s);
  notify();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Tests only: replace the clock, token or storage, and start empty. */
export function configureSwr(patch: Partial<SwrEnv>): void {
  env = { ...env, ...patch };
  store = null;
  inflight.clear();
}

export interface CachedState<T> {
  data: T | null;
  stale: boolean;
  error: unknown;
  refresh: () => Promise<void>;
}

const serverSnapshot = () => null;

/**
 * `cached()` as a hook: the stored answer on the first client render after hydration (the server and hydration render
 * see null), a request when missing or stale, a re-render when the entry changes anywhere. `key` null: nothing.
 */
export function useCached<T>(key: string | null, fetcher: () => Promise<T>, opts: SwrOptions = {}): CachedState<T> {
  const entry = useSyncExternalStore(
    subscribe,
    () => (key ? peek<T>(key) : null),
    serverSnapshot,
  );
  const [error, setError] = useState<unknown>(null);
  const { ttl, storage } = opts;
  // the fetcher is usually an inline closure over the key: the key decides, not the closure's identity
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const fetch = useCallback(fetcher, [key]);
  const missingOrStale = !entry || isStale(entry);
  useEffect(() => {
    if (!key || !missingOrStale) return;
    let alive = true;
    cached(key, fetch, { ttl, storage }).then(
      () => { if (alive) setError(null); },
      (e: unknown) => { if (alive) setError(e); },
    );
    return () => { alive = false; };
  }, [key, missingOrStale, fetch, ttl, storage]);
  const refresh = useCallback(async () => {
    if (!key) return;
    try {
      await revalidate(key, fetch, { ttl, storage });
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [key, fetch, ttl, storage]);
  return { data: entry ? entry.value : null, stale: !!entry && isStale(entry), error, refresh };
}
