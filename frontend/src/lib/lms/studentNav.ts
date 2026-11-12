/**
 * Student UI U2 (docs/phases/STUDENT_UI_DESIGN.md §2.2, §2.3): the links of the student shell for the current exam
 * course, with the active one for the current path. Dependency-free (structural types only).
 *
 * U8 (§5.1 a): the mistakes notebook lives only on Сохранённые (`/courses/{c}/saved?tab=mistakes`), so there is no
 * separate "Мои ошибки" link. Видеоуроки: the syllabus `/courses/{c}/modules` (U9: no module sub-links).
 */

export type StudentNavKey = "home" | "analytics" | "saved" | "lessons" | "tests" | "practice" | "catalog";

export interface StudentNavLink {
  key: StudentNavKey;
  href: string;
  active: boolean;
}

export interface StudentNavInput {
  lang: string;
  /** Path without the language prefix (`/courses/abc/progress`). */
  rest: string;
  /** `?tab=` of the current URL. */
  tab: string | null;
  /** The current exam course, null when the student has none. */
  courseId: string | null;
  /** What the course has (null: not known yet; optional items stay hidden). */
  features: { modules: boolean; practice: boolean } | null;
}

/** Path segments under /courses that are not a course id. */
const NOT_COURSE = new Set(["catalog", "join", "new", "trash", "become-teacher"]);

/** The course id of a path (`/courses/<id>/...`), or null. */
export function courseIdOfPath(rest: string): string | null {
  const m = /^\/courses\/([^/?#]+)/.exec(rest);
  return m && !NOT_COURSE.has(m[1]) ? m[1] : null;
}

function under(rest: string, prefix: string): boolean {
  return rest === prefix || rest.startsWith(`${prefix}/`);
}

/** Every link the shell may show, in sidebar order; items the course does not have are left out. */
export function studentNavLinks({ lang, rest, courseId, features }: StudentNavInput): Record<StudentNavKey, StudentNavLink | null> {
  const base = `/${lang}`;
  const home: StudentNavLink = { key: "home", href: `${base}/courses`, active: rest === "/courses" };
  const catalog: StudentNavLink = { key: "catalog", href: `${base}/courses/catalog`, active: under(rest, "/courses/catalog") };
  if (!courseId) {
    return { home, catalog, analytics: null, saved: null, lessons: null, tests: null, practice: null };
  }
  const c = `/courses/${courseId}`;
  return {
    home,
    catalog,
    // step 3a S2: the links land on the course tabs (the old URLs redirect there); S3 replaces these per-course links
    analytics: { key: "analytics", href: `${base}${c}/analytics`, active: under(rest, `${c}/analytics`) || under(rest, `${c}/progress`) },
    // U8: flagged questions and the mistakes notebook (`?tab=mistakes`); `/progress?tab=mistakes` redirects there
    saved: { key: "saved", href: `${base}${c}/saved`, active: under(rest, `${c}/saved`) },
    lessons: features?.modules
      ? { key: "lessons", href: `${base}${c}/lessons`, active: under(rest, `${c}/lessons`) || under(rest, `${c}/modules`) || under(rest, `${c}/pages`) }
      : null,
    // U4: the Тесты page (step 3a S2: the course page is Обзор, no longer Тесты)
    tests: { key: "tests", href: `${base}${c}/tests`, active: under(rest, `${c}/tests`) },
    practice: { key: "practice", href: `${base}${c}/tests#practice`, active: under(rest, `${c}/practice`) },
  };
}

// --- TEACHER_TO_STUDENT_MAP §2.4 begin --- (the УРОКИ group: one row per lesson course attached to the current exam)

/** Rows shown in the sidebar; with more, a "Все уроки" link opens `/courses/{exam}/lessons`. */
export const LESSON_ROWS_MAX = 8;

export interface LessonCourseRowInput {
  id: string;
  enrolled: boolean;
  progress: { done: number; total: number } | null;
}

export interface LessonCourseLink {
  id: string;
  href: string;
  active: boolean;
  /** the ring: enrolled with something to finish; null: nothing on the right */
  progress: { done: number; total: number } | null;
}

/**
 * Enrolled: the course overview (`/courses/{lc}/modules`); not enrolled: its catalog landing, which joins. The row is
 * active anywhere inside the lesson course and on its landing.
 */
export function lessonCourseLinks({ lang, rest, examId, rows }: {
  lang: string; rest: string; examId: string | null; rows: LessonCourseRowInput[] | null;
}): { rows: LessonCourseLink[]; all: { href: string; active: boolean } | null } {
  if (!examId || !rows || rows.length === 0) return { rows: [], all: null };
  const base = `/${lang}`;
  const pathCourse = courseIdOfPath(rest);
  const links = rows.slice(0, LESSON_ROWS_MAX).map((r) => ({
    id: r.id,
    href: r.enrolled ? `${base}/courses/${r.id}` : `${base}/courses/catalog/${r.id}`, // step 3a S2: its Обзор
    active: pathCourse === r.id || under(rest, `/courses/catalog/${r.id}`),
    progress: r.enrolled && r.progress && r.progress.total > 0 ? r.progress : null,
  }));
  const allPath = `/courses/${examId}/lessons`;
  const all = rows.length > LESSON_ROWS_MAX ? { href: `${base}${allPath}`, active: under(rest, allPath) } : null;
  return { rows: links, all };
}
// --- TEACHER_TO_STUDENT_MAP §2.4 end ---
