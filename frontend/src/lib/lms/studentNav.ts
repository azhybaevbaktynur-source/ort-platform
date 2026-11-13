/**
 * Step 3a S3 (docs/phases/STUDENT_IA_DESIGN.md §2.1, §2.5): the links of the student frame. The global frame is about
 * the person, a course space about one course (S2), so no global link carries a course id. S7 (v3, V1, V7, V8): Главная
 * `/home` and Каталог `/courses/catalog` (no «Мои курсы» page any more), then the «Мои курсы» rows (recent first, 6 +
 * «Все курсы (N)» → `/home#courses`; no course: no rows, the shell hides the group). Dependency-free (structural types;
 * `lastPlace.ts` is dependency-free too), checked by `studentNav.check.ts`.
 */
import { courseRowHref, recentFirst, type LastPlace } from "./lastPlace";

export type StudentNavKey = "home" | "catalog";

export interface StudentNavLink {
  key: StudentNavKey;
  href: string;
  active: boolean;
}

/** Path segments under /courses that are not a course id. */
const NOT_COURSE = new Set(["catalog", "join", "new", "trash", "become-teacher", "choose"]);

/** The course id of a path (`/courses/<id>/...`), or null. */
export function courseIdOfPath(rest: string): string | null {
  const m = /^\/courses\/([^/?#]+)/.exec(rest);
  return m && !NOT_COURSE.has(m[1]) ? m[1] : null;
}

function under(rest: string, prefix: string): boolean {
  return rest === prefix || rest.startsWith(`${prefix}/`);
}

/** The two global links in sidebar order; `catalog` is null for the test student (Student view). */
export function studentNavLinks({ lang, rest, testStudent = false }: {
  lang: string;
  /** Path without the language prefix (`/courses/abc/tests`). */
  rest: string;
  testStudent?: boolean;
}): { home: StudentNavLink; catalog: StudentNavLink | null } {
  const base = `/${lang}`;
  return {
    home: { key: "home", href: `${base}/home`, active: rest === "/home" },
    catalog: testStudent ? null : { key: "catalog", href: `${base}/courses/catalog`, active: under(rest, "/courses/catalog") },
  };
}

/** Rows of the «Мои курсы» list; with more courses the last row is «Все курсы (N)». */
export const COURSE_ROWS_MAX = 6;

export interface CourseRowInput {
  id: string;
  progress?: { done: number; total: number } | null;
}

export interface CourseRow<T extends CourseRowInput = CourseRowInput> {
  course: T;
  href: string;
  /** the course being viewed (inside its space) */
  active: boolean;
  /** the ring: something to finish; null: nothing on the right */
  progress: { done: number; total: number } | null;
}

export interface CourseRows<T extends CourseRowInput = CourseRowInput> {
  rows: CourseRow<T>[];
  /** «Все курсы (N)» → `/home#courses` (the hub's «Мои курсы» section) when there are more courses than rows */
  all: { href: string; count: number } | null;
}

/**
 * The student's courses as sidebar rows (§2.1, §2.5): the recent ids first, then the home's order (newest enrolment
 * first); a row opens the course's last tab when the last place names it, else Обзор; the viewed course's row is
 * active. No course, or `loaded` false: no rows (the shell hides the group; v3 V8, no «Выбрать курсы» row).
 */
export function courseRows<T extends CourseRowInput>({ lang, rest, courses, recent, place, loaded }: {
  lang: string;
  rest: string;
  courses: T[];
  recent: string[];
  place: LastPlace | null;
  loaded: boolean;
}): CourseRows<T> {
  const viewed = courseIdOfPath(rest);
  if (!loaded || courses.length === 0) return { rows: [], all: null };
  const ordered = recentFirst(courses, recent);
  // the viewed course stays visible even when it is not among the first rows
  let shown = ordered.slice(0, COURSE_ROWS_MAX);
  const viewedRow = viewed ? ordered.find((c) => c.id === viewed) : undefined;
  if (viewedRow && !shown.includes(viewedRow)) shown = [...shown.slice(0, COURSE_ROWS_MAX - 1), viewedRow];
  const rows = shown.map((c) => ({
    course: c,
    href: courseRowHref(lang, c.id, place),
    active: c.id === viewed,
    progress: c.progress && c.progress.total > 0 ? c.progress : null,
  }));
  const all = courses.length > COURSE_ROWS_MAX ? { href: `/${lang}/home#courses`, count: courses.length } : null;
  return { rows, all };
}
