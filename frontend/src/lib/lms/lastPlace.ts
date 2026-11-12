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
 * S2 writes; S3 reads (sidebar order and the rows' tab, «Продолжить» in the phone bar, the hub's continue card).
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

// --- Step 3a S3 begin --- (§2.2, §2.5): the readers: «Продолжить» (hub card, phone bar slot) and the course rows' tab

/** The tab a remembered place belongs to (an object page reopens its parent tab), as a path after `/courses/{c}`. */
const TAB_OF_KIND: Record<PlaceKind, string> = {
  overview: "", lessons: "/lessons", tests: "/tests", analytics: "/analytics", saved: "/saved",
  lesson: "/lessons", lobby: "/tests", assignment: "/tests",
};

/** The place's path in the current language (the stored one carries the language it was written in). */
export function placeHref(lang: string, place: Pick<LastPlace, "path">): string {
  return place.path.replace(new RegExp(`^/${LANG}(?=/)`), `/${lang}`);
}

/** Where a course row of the sidebar opens: the course's last opened tab when the last place names it, else Обзор. */
export function courseRowHref(lang: string, courseId: string, place: LastPlace | null): string {
  const base = `/${lang}/courses/${courseId}`;
  return place && place.courseId === courseId ? `${base}${TAB_OF_KIND[place.kind] ?? ""}` : base;
}

/** The fields of `HomeNextStepOut` / `HomeModuleNextOut` that make a link (structural: no import of the API types). */
export interface StepLink {
  module_id?: string | null;
  item_id?: string | null;
  kind?: string | null;
  link?: { assignment_kind?: string | null; assignment_id?: string | null; assessment_id?: string | null; page_id?: string | null } | null;
}

/** A lesson row's link, as the home's «Продолжить урок» opened it: an assignment its own page (a quiz its lobby),
 * every other item the lesson page. Null without the ids. */
export function lessonStepHref(lang: string, courseId: string, step: StepLink): string | null {
  const base = `/${lang}/courses/${courseId}`;
  const link = step.link;
  if (step.kind === "assignment" && link) {
    if (link.assignment_kind === "quiz" && link.assessment_id) return `${base}/assessments/${link.assessment_id}`;
    if (link.assignment_id) return `${base}/assignments/${link.assignment_id}`;
  }
  return step.module_id && step.item_id ? `${base}/modules/${step.module_id}/items/${step.item_id}` : null;
}

/** A course of the student, as far as «Продолжить» needs it (`HomeCourseOut`). */
export interface ContinueCourse {
  id: string;
  student_layout?: string;
  next_step?: ({ kind: string; attempt_id?: string | null; item_kind?: string | null } & StepLink) | null;
}

/** The server parts of the fallback (`HomeOut`; absent in the phone bar, which has only the bootstrap's courses). */
export interface ContinueHome {
  in_progress: { attempt_id: string; course_id: string }[];
  modules_next?: ({ course_id: string } & StepLink)[];
}

export type ContinueKind = "place" | "resume" | "lesson" | "overview" | "choose";

export interface ContinueTarget {
  kind: ContinueKind;
  href: string;
  /** null only for `choose` (no course yet) */
  courseId: string | null;
  /** `place` only: what the remembered page is */
  placeKind?: PlaceKind;
  /** `resume` only: the attempt in progress */
  attemptId?: string;
}

/**
 * «Продолжить» (STUDENT_IA_DESIGN §2.2, §2.5): the remembered last place when its course is still one of the student's;
 * else the server fallback: the in-progress attempt, else the first next lesson, else the newest exam course's Обзор
 * (else the newest course's); with no course at all, the choose step. `courses` is in the home's order (newest
 * enrolment first). Without `home` (the phone bar) the courses' own `next_step` stands for the same two rows.
 */
export function continueTarget(lang: string, place: LastPlace | null, courses: ContinueCourse[], home: ContinueHome | null = null): ContinueTarget {
  const mine = new Set(courses.map((c) => c.id));
  const base = (id: string) => `/${lang}/courses/${id}`;
  if (place && mine.has(place.courseId)) return { kind: "place", href: placeHref(lang, place), courseId: place.courseId, placeKind: place.kind };
  const attempt = home
    ? home.in_progress.find((r) => mine.has(r.course_id))
    : courses.map((c) => (c.next_step?.kind === "resume_test" && c.next_step.attempt_id ? { attempt_id: c.next_step.attempt_id, course_id: c.id } : null))
      .find((r) => r !== null) ?? undefined;
  if (attempt) return { kind: "resume", href: `${base(attempt.course_id)}/attempts/${attempt.attempt_id}`, courseId: attempt.course_id, attemptId: attempt.attempt_id };
  const lessons: ({ course_id: string } & StepLink)[] = home
    ? (home.modules_next ?? []).filter((r) => mine.has(r.course_id))
    : courses.filter((c) => c.next_step?.kind === "continue_lesson")
      .map((c) => ({ course_id: c.id, module_id: c.next_step!.module_id, item_id: c.next_step!.item_id, kind: c.next_step!.item_kind, link: c.next_step!.link }));
  for (const r of lessons) {
    const href = lessonStepHref(lang, r.course_id, r);
    if (href) return { kind: "lesson", href, courseId: r.course_id };
  }
  const exam = courses.find((c) => c.student_layout === "exam_prep") ?? courses[0];
  if (exam) return { kind: "overview", href: base(exam.id), courseId: exam.id };
  return { kind: "choose", href: `/${lang}/courses/choose`, courseId: null };
}

/** The «Мои курсы» order (§2.5): the recent ids still in the list first, then the rest in the list's order. */
export function recentFirst<T extends { id: string }>(courses: T[], recent: string[]): T[] {
  const byId = new Map(courses.map((c) => [c.id, c]));
  const head = recent.filter((id, i) => byId.has(id) && recent.indexOf(id) === i).map((id) => byId.get(id)!);
  const seen = new Set(head.map((c) => c.id));
  return [...head, ...courses.filter((c) => !seen.has(c.id))];
}
// --- Step 3a S3 end ---

/** `localStorage`, or null where it cannot be reached. */
export function deviceStorage(): PlaceStorage | null {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : null;
  } catch {
    return null;
  }
}
