/*
 * Owner feedback 2026-11-08 (item 2): MeOut draws the header's areas, and joining or leaving a course as a student can
 * change them (Learning for people who also teach). The calls that change enrollments say so here; the loader in
 * `useLmsMe` listens and asks /me/lms again. No import of `useLmsMe` (it imports `courses`), so no cycle.
 */
export const LMS_ME_STALE_EVENT = "ort:lms-me-stale";

export function markLmsMeStale(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LMS_ME_STALE_EVENT));
}

/** Resolves like `call`, and marks MeOut stale once it succeeded. */
export async function thenMeStale<T>(call: Promise<T>): Promise<T> {
  const out = await call;
  markLmsMeStale();
  return out;
}
