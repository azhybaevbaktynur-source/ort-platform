/**
 * Step 3a S3 (docs/phases/STUDENT_IA_DESIGN.md §2.1, §2.5): the links of the student frame. The global frame is about
 * the person, a course space about one course (S2), so no global link carries a course id: Главная `/home`, Мои курсы
 * `/courses`, Каталог `/courses/catalog`, then the «Мои курсы» rows (recent first, 6 + «Все курсы (N)»; none: «Выбрать
 * курсы»). Dependency-free (structural types; `lastPlace.ts` is dependency-free too), checked by `studentNav.check.ts`.
 */
import { chooseCoursesHref } from "./chooseCourses";
import { courseRowHref, recentFirst, type LastPlace } from "./lastPlace";

export type StudentNavKey = "home" | "courses" | "catalog";

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

/** The three global links in sidebar order; `catalog` is null for the test student (Student view). */
export function studentNavLinks({ lang, rest, testStudent = false }: {
  lang: string;
  /** Path without the language prefix (`/courses/abc/tests`). */
  rest: string;
  testStudent?: boolean;
}): { home: StudentNavLink; courses: StudentNavLink; catalog: StudentNavLink | null } {
  const base = `/${lang}`;
  return {
    home: { key: "home", href: `${base}/home`, active: rest === "/home" },
    courses: { key: "courses", href: `${base}/courses`, active: rest === "/courses" },
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
  /** «Все курсы (N)» → `/courses` when there are more rows than shown */
  all: { href: string; count: number; active: boolean } | null;
  /** no course yet: «Выбрать курсы» → `chooseCoursesHref` (the catalog until S4; never for the test student) */
  choose: { href: string; active: boolean } | null;
}

/**
 * The student's courses as sidebar rows (§2.1, §2.5): the recent ids first, then the home's order (newest enrolment
 * first); a row opens the course's last tab when the last place names it, else Обзор; the viewed course's row is
 * active. `loaded` false: nothing yet (no «Выбрать курсы» flash).
 */
export function courseRows<T extends CourseRowInput>({ lang, rest, courses, recent, place, loaded, testStudent = false }: {
  lang: string;
  rest: string;
  courses: T[];
  recent: string[];
  place: LastPlace | null;
  loaded: boolean;
  testStudent?: boolean;
}): CourseRows<T> {
  const viewed = courseIdOfPath(rest);
  if (!loaded) return { rows: [], all: null, choose: null };
  if (courses.length === 0) {
    const href = chooseCoursesHref(lang);
    return { rows: [], all: null, choose: testStudent ? null : { href, active: href === `/${lang}${rest}` } };
  }
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
  const all = courses.length > COURSE_ROWS_MAX ? { href: `/${lang}/courses`, count: courses.length, active: rest === "/courses" } : null;
  return { rows, all, choose: null };
}
