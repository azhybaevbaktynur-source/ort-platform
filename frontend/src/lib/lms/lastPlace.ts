/**
 * Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §2.5, decision N2): the student's last place inside a course and the
 * recent courses, stored on the device per user (no server field):
 *
 * - `ort_last_place:{userId}` = `{courseId, path, kind, at}`, written on every student navigation inside a course
 *   (tabs and object pages). The player and the result page write the **lobby** path: an attempt is resumed through
 *   the server's `in_progress`, never through a stored attempt URL.
 * - `ort_recent_courses:{userId}` = up to 10 course ids, most recent first, updated by the same write.
 *
 * The per-user key keeps a teacher's Student view session (another user id on the same device) separate. Every
 * storage access is wrapped in try/catch (private mode, blocked storage: nothing is remembered, nothing breaks).
 * S2 writes only; the readers (sidebar order, «Продолжить», the hub's continue card) come with S3.
 *
 * Dependency-free on purpose (checked by `lastPlace.check.ts` with a standalone `tsc`).
 */

export type PlaceKind = "overview" | "lessons" | "tests" | "analytics" | "saved" | "lesson" | "lobby" | "assignment";

export interface LastPlace {
  courseId: string;
  /** the page path with its language (`/ru/courses/c1/tests`), never a query or an attempt URL */
  path: string;
  kind: PlaceKind;
  /** epoch milliseconds */
  at: number;
}

/** The subset of `Storage` used here (a fake in the check). */
export interface PlaceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const RECENT_MAX = 10;
export const lastPlaceKey = (userId: string) => `ort_last_place:${userId}`;
export const recentCoursesKey = (userId: string) => `ort_recent_courses:${userId}`;

const ID = "[^/?#]+";
const LANG = "(en|ky|ru)";
const NOT_COURSE = new Set(["catalog", "join", "new", "trash", "become-teacher", "choose"]);

/**
 * The place a course page stands for, or null (pages that are not remembered: the player, the result, staff-only and
 * unknown pages). The player and the result are remembered as their lobby by `lobbyPlace`.
 */
export function placeOfPath(pathname: string): Omit<LastPlace, "at"> | null {
  const path = pathname.split(/[?#]/, 1)[0];
  const m = new RegExp(`^/${LANG}/courses/(${ID})(/.*)?$`).exec(path);
  if (!m || NOT_COURSE.has(m[2])) return null;
  const courseId = m[2];
  const rest = m[3] ?? "";
  const tab: Record<string, PlaceKind> = {
    "": "overview", "/lessons": "lessons", "/tests": "tests", "/analytics": "analytics", "/saved": "saved",
  };
  if (rest in tab) return { courseId, path, kind: tab[rest] };
  if (new RegExp(`^/modules/${ID}/items/${ID}$`).test(rest) || new RegExp(`^/pages/${ID}$`).test(rest)) {
    return { courseId, path, kind: "lesson" };
  }
  if (new RegExp(`^/assessments/${ID}$`).test(rest)) return { courseId, path, kind: "lobby" };
  if (new RegExp(`^/assignments/${ID}$`).test(rest)) return { courseId, path, kind: "assignment" };
  return null;
}

/** The lobby place of an attempt (player, result and review write it). */
export function lobbyPlace(lang: string, courseId: string, assessmentId: string): Omit<LastPlace, "at"> {
  return { courseId, path: `/${lang}/courses/${courseId}/assessments/${assessmentId}`, kind: "lobby" };
}

function parsePlace(raw: string | null): LastPlace | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<LastPlace> | null;
    if (!v || typeof v.courseId !== "string" || typeof v.path !== "string" || typeof v.kind !== "string" || typeof v.at !== "number") return null;
    return { courseId: v.courseId, path: v.path, kind: v.kind as PlaceKind, at: v.at };
  } catch {
    return null;
  }
}

export function readLastPlace(storage: PlaceStorage | null | undefined, userId: string): LastPlace | null {
  if (!storage || !userId) return null;
  try {
    return parsePlace(storage.getItem(lastPlaceKey(userId)));
  } catch {
    return null;
  }
}

export function readRecentCourses(storage: PlaceStorage | null | undefined, userId: string): string[] {
  if (!storage || !userId) return [];
  try {
    const v = JSON.parse(storage.getItem(recentCoursesKey(userId)) || "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

/** Remember `place` for `userId` (and its course first in the recent list). Never throws. */
export function writePlace(storage: PlaceStorage | null | undefined, userId: string, place: Omit<LastPlace, "at"> | null,
  now: number = Date.now()): void {
  if (!storage || !userId || !place) return;
  try {
    const value: LastPlace = { courseId: place.courseId, path: place.path, kind: place.kind, at: now };
    storage.setItem(lastPlaceKey(userId), JSON.stringify(value));
    const recent = [place.courseId, ...readRecentCourses(storage, userId).filter((id) => id !== place.courseId)].slice(0, RECENT_MAX);
    storage.setItem(recentCoursesKey(userId), JSON.stringify(recent));
  } catch {
    // storage full or blocked: nothing is remembered
  }
}

/** `localStorage`, or null where it cannot be reached. */
export function deviceStorage(): PlaceStorage | null {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : null;
  } catch {
    return null;
  }
}
