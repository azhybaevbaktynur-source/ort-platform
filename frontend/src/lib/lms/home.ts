// Phase 6b S6b: student home data (`GET /me/home`, PHASE_6_DESIGN 8.4). One server-limited call, no N+1.
import { reloadBootstrap } from "./bootstrap";
import { lmsFetch } from "./client";
import type { HomeCourseOut, HomeOut } from "./homeTypes";
import type { PageOut } from "./types";

export const getHome = (signal?: AbortSignal) => lmsFetch<HomeOut>("/me/home", { signal });

/** Every student course of the caller, the same cards as `HomeOut.courses` ("show all" on the dashboard). */
export const listHomeCourses = (cursor?: string | null, limit = 24) =>
  lmsFetch<PageOut<HomeCourseOut>>("/me/home/courses", { params: { cursor, limit } });

/**
 * Fix round 2026-11-12 1c: close the teacher application line for good (stored on the server; 204, idempotent), then ask
 * the shell's cached `me` (bootstrap/SWR, meCache) again so the next navigation does not bring it back.
 */
export async function dismissTeacherApplication(): Promise<void> {
  await lmsFetch<void>("/me/teacher-application/dismiss", { method: "POST" });
  try { await reloadBootstrap(); } catch { /* the cache's error, shown by the shell */ }
}
