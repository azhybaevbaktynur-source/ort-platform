/**
 * Student UI U2 (docs/phases/STUDENT_UI_DESIGN.md §2.2, §2.3): the links of the student shell for the current exam
 * course, with the active one for the current path. Dependency-free (structural types only).
 *
 * Pages that do not exist yet point to existing routes (TODO):
 * - Тесты: the course page for now (TODO U4: `/courses/{c}/tests`);
 * - Сохранённые: the mistakes tab of progress for now (TODO U8: `/courses/{c}/saved`);
 * - Видеоуроки: the syllabus `/courses/{c}/modules` (U7; its module sub-links come from `modules/lessonNav.ts`).
 */

export type StudentNavKey = "home" | "analytics" | "saved" | "lessons" | "tests" | "practice" | "mistakes" | "catalog";

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
export function studentNavLinks({ lang, rest, tab, courseId, features }: StudentNavInput): Record<StudentNavKey, StudentNavLink | null> {
  const base = `/${lang}`;
  const home: StudentNavLink = { key: "home", href: `${base}/courses`, active: rest === "/courses" };
  const catalog: StudentNavLink = { key: "catalog", href: `${base}/courses/catalog`, active: under(rest, "/courses/catalog") };
  if (!courseId) {
    return { home, catalog, analytics: null, saved: null, lessons: null, tests: null, practice: null, mistakes: null };
  }
  const c = `/courses/${courseId}`;
  const progress = under(rest, `${c}/progress`);
  const mistakesTab = progress && tab === "mistakes";
  return {
    home,
    catalog,
    analytics: { key: "analytics", href: `${base}${c}/progress`, active: progress && !mistakesTab },
    // TODO U8: `/courses/{c}/saved` (flagged questions); never active until it has its own page
    saved: { key: "saved", href: `${base}${c}/progress?tab=mistakes`, active: false },
    lessons: features?.modules
      ? { key: "lessons", href: `${base}${c}/modules`, active: under(rest, `${c}/modules`) || under(rest, `${c}/pages`) }
      : null,
    // TODO U4: `/courses/{c}/tests`
    tests: { key: "tests", href: `${base}${c}`, active: rest === c },
    practice: { key: "practice", href: `${base}${c}/practice`, active: under(rest, `${c}/practice`) },
    mistakes: { key: "mistakes", href: `${base}${c}/progress?tab=mistakes`, active: mistakesTab },
  };
}
