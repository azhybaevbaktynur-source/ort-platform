/**
 * Client engine for the attempt player (docs/phases/PHASE_3_DESIGN.md section 6).
 *
 * Framework-free on purpose: only `import type` from other modules, all I/O (network, timers, storage,
 * wall clock) injected, so it runs under plain node for `attemptClient.check.ts`.
 *
 * - ServerClock: offset between the server clock and Date.now(), keeping the lowest-RTT sample.
 * - remainingMs(): deadline minus server time, recomputed every call (never decremented).
 * - AutosaveQueue: coalesces per position, mirrors to localStorage, batches <= 20, retries with backoff,
 *   classifies server errors (closed / invalid / auth / transient).
 */
import type { AnswerIn, AttemptSectionState, AttemptState, SaveOut } from "./attemptTypes";

// ---------- server clock ----------

export class ServerClock {
  private offsetMs = 0;
  private bestRtt = Infinity;
  private has = false;

  /** `sentMs`/`recvMs` are Date.now() before the request and after the response; `serverNowIso` is from the body. */
  sample(serverNowIso: string | undefined | null, sentMs: number, recvMs: number): void {
    if (!serverNowIso) return;
    const server = Date.parse(serverNowIso);
    if (!Number.isFinite(server)) return;
    const rtt = Math.max(0, recvMs - sentMs);
    if (this.has && rtt > this.bestRtt) return;
    this.bestRtt = rtt;
    this.offsetMs = server - (sentMs + recvMs) / 2;
    this.has = true;
  }

  /** Server "now" in epoch ms as estimated from the local clock. */
  now(localNowMs: number = Date.now()): number {
    return localNowMs + this.offsetMs;
  }

  get offset(): number {
    return this.offsetMs;
  }
}

// ---------- timing helpers ----------

export function parseIso(s: string | null | undefined): number | null {
  if (!s) return null;
  const v = Date.parse(s);
  return Number.isFinite(v) ? v : null;
}

/** The section that is open now (forward-only: the current one; free navigation: none has its own timer). */
export function currentSection(state: Pick<AttemptState, "sections" | "current_section_pos">): AttemptSectionState | undefined {
  return state.sections.find((s) => s.pos === state.current_section_pos);
}

/** Effective deadline (epoch ms) of the running timer: min(section, attempt); null = no limit. */
export function effectiveDeadlineMs(
  state: Pick<AttemptState, "sections" | "current_section_pos" | "deadline_at" | "navigation">,
): number | null {
  const att = parseIso(state.deadline_at);
  const sec = state.navigation === "section_forward_only" ? parseIso(currentSection(state)?.deadline_at) : null;
  if (att === null) return sec;
  if (sec === null) return att;
  return Math.min(att, sec);
}

/** Milliseconds left (can be negative) or null when unlimited. Pure given the clock sample. */
export function remainingMs(
  state: Pick<AttemptState, "sections" | "current_section_pos" | "deadline_at" | "navigation">,
  clock: Pick<ServerClock, "now">,
  localNowMs: number = Date.now(),
): number | null {
  const d = effectiveDeadlineMs(state);
  if (d === null) return null;
  return d - clock.now(localNowMs);
}

/** True when the attempt deadline (not the section one) has passed. */
export function attemptExpired(
  state: Pick<AttemptState, "deadline_at">,
  clock: Pick<ServerClock, "now">,
  localNowMs: number = Date.now(),
): boolean {
  const d = parseIso(state.deadline_at);
  return d !== null && d - clock.now(localNowMs) <= 0;
}

// ---------- error classification (duck-typed, no import of LmsApiError) ----------

export type FailureKind =
  | "closed" // attempt/section closed or gone: stop, reload state
  | "invalid" // entry rejected for good (422, item_not_found)
  | "too_large" // 413
  | "auth" // 401: keep queue, ask to sign in
  | "transient"; // network, 5xx, 429, anything else: retry with backoff

export interface ClassifiedFailure {
  kind: FailureKind;
  code: string;
  status: number;
  positions: number[];
  retryAfterMs: number | null;
}

export function classifyFailure(err: unknown): ClassifiedFailure {
  const e = (err ?? {}) as { status?: number; code?: string; details?: Record<string, unknown> };
  const status = typeof e.status === "number" ? e.status : 0;
  const code = typeof e.code === "string" ? e.code : "unknown";
  const raw = e.details?.positions ?? e.details?.invalid_positions;
  const positions = Array.isArray(raw) ? raw.filter((x): x is number => typeof x === "number") : [];
  const ra = e.details?.retry_after_seconds;
  const retryAfterMs = typeof ra === "number" ? ra * 1000 : null;
  const base = { code, status, positions, retryAfterMs };
  // too_many_answers (422): the batch was larger than the server cap; the queue halves it and retries (never dropped)
  if (code === "too_many_answers") return { kind: "too_large", ...base };
  if (code === "attempt_closed" || code === "section_closed" || code === "attempt_not_found") return { kind: "closed", ...base };
  if (status === 410) return { kind: "closed", ...base };
  if (status === 409 && code !== "rate_limited") return { kind: "closed", ...base };
  if (status === 401) return { kind: "auth", ...base };
  if (status === 413 || code === "payload_too_large") return { kind: "too_large", ...base };
  if (code === "invalid_response" || code === "item_not_found" || status === 422) return { kind: "invalid", ...base };
  return { kind: "transient", ...base };
}

/**
 * Failures of the section-close call. `use_submit` (last section) and `section_not_current` (409) are expected
 * outcomes of that call, not "attempt closed": handle them explicitly, never through `classifyFailure`'s closed path.
 */
export type CloseFailure = "use_submit" | "not_current" | "closed" | "other";

export function classifyCloseFailure(err: unknown): CloseFailure {
  const code = (err as { code?: string } | null | undefined)?.code;
  if (code === "use_submit") return "use_submit";
  if (code === "section_not_current") return "not_current";
  return classifyFailure(err).kind === "closed" ? "closed" : "other";
}

// ---------- backoff ----------

export const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000, 16000, 30000];

/** Backoff for the n-th consecutive failure (0-based) with +-20 % jitter; `rand` in [0,1). */
export function backoffMs(failures: number, rand: () => number = Math.random): number {
  const base = BACKOFF_STEPS_MS[Math.min(Math.max(failures, 0), BACKOFF_STEPS_MS.length - 1)];
  return Math.round(base * (0.8 + 0.4 * rand()));
}

// ---------- autosave queue ----------

export type SaveStatus = "idle" | "saving" | "saved" | "offline" | "error" | "auth" | "closed";

export interface QueueSnapshot {
  status: SaveStatus;
  pending: number;
  lastError: string | null;
}

export interface QueueEnv {
  save: (answers: AnswerIn[]) => Promise<SaveOut>;
  /** Called with every batch on `visibilitychange: hidden`; must never throw. */
  saveKeepalive?: (answers: AnswerIn[]) => void;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (h: unknown) => void;
  now: () => number;
  rand?: () => number;
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
}

export interface QueueHandlers {
  /** Server said the attempt or section is closed (or unreachable for good). Queue is cleared. */
  onClosed?: (info: ClassifiedFailure) => void;
  /** Entries dropped for good; show which questions failed. */
  onRejected?: (positions: number[], info: ClassifiedFailure) => void;
  /** Server reported a different section/status in a successful SaveOut (e.g. lazily advanced). */
  onServerState?: (out: SaveOut) => void;
  onChange?: (snap: QueueSnapshot) => void;
}

export const MAX_BATCH = 20;
export const IDLE_FLUSH_MS = 1500;
export const MAX_DIRTY_MS = 5000;
export const CONTINUOUS_FLUSH_MS = 1000;
export const storageKey = (attemptId: string) => `lms_attempt_q_${attemptId}`;

export class AutosaveQueue {
  private entries = new Map<number, AnswerIn>();
  private lastTs = 0;
  private idleTimer: unknown = null;
  private maxTimer: unknown = null;
  private retryTimer: unknown = null;
  private inflight: Promise<void> | null = null;
  private failures = 0;
  private batchLimit = MAX_BATCH;
  private stopped: ClassifiedFailure | null = null;
  private authBlocked = false;
  private continuous = false;
  private status: SaveStatus = "idle";
  private lastError: string | null = null;

  constructor(
    private readonly attemptId: string,
    private readonly env: QueueEnv,
    private readonly handlers: QueueHandlers = {},
  ) {
    this.restore();
  }

  // ----- public -----

  get pending(): number {
    return this.entries.size;
  }

  snapshot(): QueueSnapshot {
    return { status: this.status, pending: this.entries.size, lastError: this.lastError };
  }

  /** Record a change. `response` undefined = leave the stored answer alone; null = clear it. */
  set(position: number, patch: { response?: Record<string, unknown> | null; flagged?: boolean }): void {
    if (this.stopped) return;
    const prev = this.entries.get(position);
    const ts = Math.max(this.env.now(), this.lastTs + 1);
    this.lastTs = ts;
    const next: AnswerIn = { position, client_ts: ts };
    const response = patch.response !== undefined ? patch.response : prev?.response;
    const flagged = patch.flagged !== undefined ? patch.flagged : prev?.flagged;
    if (response !== undefined) next.response = response;
    if (flagged !== undefined) next.flagged = flagged;
    this.entries.set(position, next);
    this.persist();
    this.schedule();
    this.emit(this.inflight ? "saving" : "idle");
  }

  /** Last-minute mode: flush shortly after every change. */
  setContinuous(on: boolean): void {
    if (this.continuous === on) return;
    this.continuous = on;
    if (on && this.entries.size) this.schedule();
  }

  /** Entries to ride along with a submit request (oldest first, <= 20). */
  peek(max: number = MAX_BATCH): AnswerIn[] {
    return this.sorted().slice(0, max);
  }

  /** After a successful submit/close the queue is moot. */
  clear(): void {
    this.entries.clear();
    this.clearTimers();
    this.persist();
    this.emit("idle");
  }

  /**
   * Flush until the queue is empty or a pass fails. Resolves true when empty. Used before section close and
   * submit; callers fall back to sending `peek()` with the submit request when this returns false.
   */
  async flushNow(): Promise<boolean> {
    this.clearTimers();
    for (let guard = 0; guard < 200; guard++) {
      if (this.stopped) return false;
      if (this.inflight) {
        await this.inflight;
        if (this.failures > 0 || this.stopped) return this.entries.size === 0;
        continue;
      }
      if (this.entries.size === 0) return true;
      const ok = await this.runOnce();
      if (!ok) return false;
    }
    return this.entries.size === 0;
  }

  /** `online` event / user pressed "retry" / returned from sign-in. */
  retryNow(): void {
    this.authBlocked = false;
    this.failures = 0;
    if (this.retryTimer) this.env.clearTimer(this.retryTimer);
    this.retryTimer = null;
    void this.flushNow();
  }

  /** `visibilitychange: hidden`. */
  onHidden(): void {
    if (!this.entries.size || this.stopped) return;
    const batch = this.sorted().slice(0, MAX_BATCH);
    try {
      this.env.saveKeepalive?.(batch);
    } catch { /* ignore */ }
  }

  dispose(): void {
    this.clearTimers();
    if (this.retryTimer) this.env.clearTimer(this.retryTimer);
    this.retryTimer = null;
  }

  // ----- internals -----

  private sorted(): AnswerIn[] {
    return Array.from(this.entries.values()).sort((a, b) => a.client_ts - b.client_ts);
  }

  private schedule(): void {
    if (this.stopped || this.authBlocked || this.retryTimer) return;
    if (this.idleTimer) this.env.clearTimer(this.idleTimer);
    const idle = this.continuous ? CONTINUOUS_FLUSH_MS : IDLE_FLUSH_MS;
    this.idleTimer = this.env.setTimer(() => {
      this.idleTimer = null;
      void this.flushNow();
    }, idle);
    if (!this.maxTimer) {
      this.maxTimer = this.env.setTimer(() => {
        this.maxTimer = null;
        void this.flushNow();
      }, MAX_DIRTY_MS);
    }
  }

  private clearTimers(): void {
    if (this.idleTimer) this.env.clearTimer(this.idleTimer);
    if (this.maxTimer) this.env.clearTimer(this.maxTimer);
    this.idleTimer = null;
    this.maxTimer = null;
  }

  /** One request. Returns true when the batch was accepted by the server. */
  private runOnce(): Promise<boolean> {
    const batch = this.sorted().slice(0, this.batchLimit);
    this.emit("saving");
    const p = (async (): Promise<boolean> => {
      try {
        const out = await this.env.save(batch);
        this.failures = 0;
        this.lastError = null;
        // Drop only entries not changed since the request was built (same client_ts).
        const sent = new Map(batch.map((b) => [b.position, b.client_ts]));
        for (const [pos, ts] of sent) {
          if (this.entries.get(pos)?.client_ts === ts) this.entries.delete(pos);
        }
        this.persist();
        this.handlers.onServerState?.(out);
        if (this.entries.size) this.schedule();
        this.emit(this.entries.size ? "saving" : "saved");
        return true;
      } catch (err) {
        return this.onFailure(err, batch);
      }
    })();
    this.inflight = p.then(() => undefined, () => undefined).finally(() => {
      this.inflight = null;
    });
    return p;
  }

  private onFailure(err: unknown, batch: AnswerIn[]): boolean {
    const info = classifyFailure(err);
    this.lastError = info.code;
    if (info.kind === "closed") {
      this.stopped = info;
      this.entries.clear();
      this.persist();
      this.clearTimers();
      this.emit("closed");
      this.handlers.onClosed?.(info);
      return false;
    }
    if (info.kind === "invalid" || (info.kind === "too_large" && batch.length === 1)) {
      const bad = info.positions.length ? info.positions : batch.map((b) => b.position);
      for (const pos of bad) this.entries.delete(pos);
      this.persist();
      this.emit(this.entries.size ? "saving" : "error");
      this.handlers.onRejected?.(bad, info);
      if (this.entries.size) this.schedule();
      return false;
    }
    if (info.kind === "too_large") {
      this.batchLimit = Math.max(1, Math.floor(batch.length / 2));
      this.failures = 0;
      this.schedule();
      return false;
    }
    if (info.kind === "auth") {
      this.authBlocked = true;
      this.emit("auth");
      return false;
    }
    // transient: keep the queue, back off
    const wait = Math.max(backoffMs(this.failures, this.env.rand), info.retryAfterMs ?? 0);
    this.failures += 1;
    this.clearTimers();
    if (this.retryTimer) this.env.clearTimer(this.retryTimer);
    this.retryTimer = this.env.setTimer(() => {
      this.retryTimer = null;
      void this.flushNow();
    }, wait);
    this.emit(info.status === 0 ? "offline" : "error");
    return false;
  }

  private emit(status: SaveStatus): void {
    this.status = status;
    this.handlers.onChange?.(this.snapshot());
  }

  private persist(): void {
    const st = this.env.storage;
    if (!st) return;
    try {
      if (this.entries.size === 0) st.removeItem(storageKey(this.attemptId));
      else st.setItem(storageKey(this.attemptId), JSON.stringify(this.sorted()));
    } catch { /* private mode / quota: the in-memory queue still works */ }
  }

  private restore(): void {
    const st = this.env.storage;
    if (!st) return;
    try {
      const raw = st.getItem(storageKey(this.attemptId));
      if (!raw) return;
      const arr = JSON.parse(raw) as unknown;
      if (!Array.isArray(arr)) return;
      for (const x of arr) {
        const a = x as AnswerIn;
        if (a && typeof a.position === "number" && typeof a.client_ts === "number") {
          this.entries.set(a.position, a);
          this.lastTs = Math.max(this.lastTs, a.client_ts);
        }
      }
    } catch { /* corrupt entry: ignore */ }
  }

  /** Called by the owner after construction when restored entries should start flushing. */
  kick(): void {
    if (this.entries.size) {
      this.emit("saving");
      void this.flushNow();
    }
  }
}

/** Browser wiring helper: real timers, wall clock and localStorage (guarded). */
export function browserQueueEnv(
  save: QueueEnv["save"],
  saveKeepalive?: QueueEnv["saveKeepalive"],
): QueueEnv {
  let storage: QueueEnv["storage"] = null;
  try {
    storage = typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    storage = null;
  }
  return {
    save,
    saveKeepalive,
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    now: () => Date.now(),
    rand: Math.random,
    storage,
  };
}

/** Random delay (ms) before the time-up submit, spreading the burst inside the grace window. */
export function timeUpSubmitDelayMs(rand: () => number = Math.random, graceS = 45): number {
  return Math.round(Math.min(15, Math.max(0, graceS - 20)) * 1000 * rand());
}

/**
 * Warn when the same attempt is open in another tab. Returns a disposer. `onOther` fires when another tab
 * announces itself or answers our announcement.
 */
export function watchOtherTabs(attemptId: string, onOther: () => void): () => void {
  if (typeof BroadcastChannel === "undefined") return () => {};
  const tabId = Math.random().toString(36).slice(2);
  let ch: BroadcastChannel;
  try {
    ch = new BroadcastChannel(`lms_attempt_${attemptId}`);
  } catch {
    return () => {};
  }
  ch.onmessage = (ev: MessageEvent) => {
    const m = ev.data as { from?: string; kind?: string };
    if (!m || m.from === tabId) return;
    onOther();
    if (m.kind === "hello") ch.postMessage({ from: tabId, kind: "present" });
  };
  ch.postMessage({ from: tabId, kind: "hello" });
  return () => ch.close();
}
