/**
 * Student UI U2 (docs/phases/STUDENT_UI_DESIGN.md §2.2, §2.3): the links of the student shell for the current exam
 * course, with the active one for the current path. Dependency-free (structural types only).
 *
 * U8 (§5.1 a): the mistakes notebook lives only on Сохранённые (`/courses/{c}/saved?tab=mistakes`), so there is no
 * separate "Мои ошибки" link. Видеоуроки: the syllabus `/courses/{c}/modules` (its module sub-links come from
 * `modules/lessonNav.ts`).
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
    analytics: { key: "analytics", href: `${base}${c}/progress`, active: under(rest, `${c}/progress`) },
    // U8: flagged questions and the mistakes notebook (`?tab=mistakes`); `/progress?tab=mistakes` redirects there
    saved: { key: "saved", href: `${base}${c}/saved`, active: under(rest, `${c}/saved`) },
    lessons: features?.modules
      ? { key: "lessons", href: `${base}${c}/modules`, active: under(rest, `${c}/modules`) || under(rest, `${c}/pages`) }
      : null,
    // U4: the Тесты page (the course page redirects there for exam-prep students)
    tests: { key: "tests", href: `${base}${c}/tests`, active: rest === c || under(rest, `${c}/tests`) },
    practice: { key: "practice", href: `${base}${c}/practice`, active: under(rest, `${c}/practice`) },
  };
}
