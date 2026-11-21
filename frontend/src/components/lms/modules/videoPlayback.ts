// LESSON_VIDEOS V4: pure rules of the hosted lesson video player (`LessonVideo.tsx`); checked by videoPlayback.check.ts.

export const VIDEO_RATES = [0.75, 1, 1.25, 1.5, 2] as const;
/** The share of the duration that counts as watched (the view fact). */
export const WATCHED_RATIO = 0.9;
/** Refresh the signed address this long before it expires. */
export const REFRESH_BEFORE_MS = 60_000;
/** Never schedule a refresh sooner than this (a clock far off must not cause a request loop). */
export const MIN_REFRESH_MS = 5_000;

/** A backend address (absolute, `/api/v1/…` or relative to the API base) as an absolute URL. */
export function resolveApiUrl(url: string, origin: string, apiBase: string): string {
  const base = new URL(apiBase.replace(/\/?$/, "/"), origin);
  return new URL(url, base).toString();
}

/** Milliseconds until the address should be refreshed; null when `expires_at` is unreadable. */
export function refreshDelay(expiresAt: string, now: number): number | null {
  const at = Date.parse(expiresAt);
  if (!Number.isFinite(at)) return null;
  return Math.max(MIN_REFRESH_MS, at - REFRESH_BEFORE_MS - now);
}

/** Whether the address is expired or about to (within `REFRESH_BEFORE_MS`). */
export function isStale(expiresAt: string, now: number): boolean {
  const at = Date.parse(expiresAt);
  return Number.isFinite(at) && now >= at - REFRESH_BEFORE_MS;
}

/** A remembered position worth restoring: past the first 5 s and not within the last 5 s. */
export function restorablePosition(saved: number | null, duration: number): number | null {
  if (saved === null || !Number.isFinite(saved) || saved < 5) return null;
  if (Number.isFinite(duration) && duration > 0 && saved > duration - 5) return null;
  return saved;
}

/** The position to remember: null (forget) near the end, so the next visit starts from the beginning. */
export function positionToSave(time: number, duration: number): number | null {
  if (!Number.isFinite(time) || time <= 0) return null;
  if (duration > 0 && time > duration - 5) return null;
  return Math.floor(time);
}

/** Whether playback has reached the watched share of the duration. */
export function reachedWatched(time: number, duration: number): boolean {
  return duration > 0 && Number.isFinite(time) && time >= duration * WATCHED_RATIO;
}

/** The rate a stored value stands for, when it is one of the menu's. */
export function storedRate(value: number | null): number | null {
  return value !== null && (VIDEO_RATES as readonly number[]).includes(value) ? value : null;
}
