/**
 * Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.1, §3.2, §3.5): the tabs of one course space for its students
 * (Student view included): Обзор · Уроки · Тесты (or Задания) · Аналитика · Сохранённые.
 *
 * Dependency-free on purpose (checked by `courseTabs.check.ts` with a standalone `tsc`): structural types only.
 *
 * - A tab is shown only when the server says the course has published content for it (`CourseOut.features`, server
 *   EXISTS over published, live content); Обзор always. No client-side visibility decision: an older backend without
 *   flags shows every tab and hides nothing (the server stays authoritative for every list).
 * - `active`: the tab of `pathname` (`/<lang>/courses/<id>/...`); object pages make their parent tab active (lessons
 *   and pages → Уроки, lobby / result / assignment → Тесты, announcements / files → Обзор).
 * - `hidden`: the tab of a tab URL whose tab is not shown (the layout draws `AreaUnavailable` in the frame instead).
 * - `variant`: the full header on Обзор, the compact header everywhere else.
 * - The Тесты tab is labelled Задания when the course has a hand-in assignment (D4, glossary UX_GUIDELINES §5).
 */

export type CourseTabKey = "overview" | "lessons" | "tests" | "analytics" | "saved";

export interface CourseTabsCourse {
  id: string;
  features?: {
    modules: boolean; files: boolean; announcements: boolean; practice?: boolean; tests?: boolean; hand_ins?: boolean;
  } | null;
}

export interface CourseTabsOptions {
  /** Exam courses: lesson courses attached to the exam exist (true / false), or not known yet (null). */
  lessonCourses?: boolean | null;
}

export interface CourseTab {
  key: CourseTabKey;
  href: string;
  label: string;
  active: boolean;
}

export interface CourseTabsResult {
  tabs: CourseTab[];
  active: CourseTabKey | null;
  /** The tab whose own URL is open while the tab is not shown. */
  hidden: CourseTabKey | null;
  variant: "full" | "compact";
}

type T = (key: string, vars?: Record<string, string | number>) => string;

const LANG_RE = /^\/(en|ky|ru)(?=\/|$)/;

function under(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** The parent tab of a course path (null: a path outside this course). */
export function tabOfPath(pathname: string, base: string): CourseTabKey | null {
  if (!under(pathname, base)) return null;
  if (pathname === base) return "overview";
  if (under(pathname, `${base}/lessons`) || under(pathname, `${base}/modules`) || under(pathname, `${base}/pages`)) return "lessons";
  if (under(pathname, `${base}/tests`) || under(pathname, `${base}/assessments`) || under(pathname, `${base}/attempts`)
    || under(pathname, `${base}/assignments`) || under(pathname, `${base}/practice`)) return "tests";
  if (under(pathname, `${base}/analytics`) || under(pathname, `${base}/progress`) || under(pathname, `${base}/grades`)) return "analytics";
  if (under(pathname, `${base}/saved`)) return "saved";
  // announcements, files, people and anything else of the course: Обзор
  return "overview";
}

/** The URL of each tab (relative to the course base). */
const TAB_PATH: Record<CourseTabKey, string> = {
  overview: "", lessons: "/lessons", tests: "/tests", analytics: "/analytics", saved: "/saved",
};

/** Which tabs the course shows (Обзор always). */
export function shownTabs(course: CourseTabsCourse, opts: CourseTabsOptions = {}): Record<CourseTabKey, boolean> {
  const f = course.features;
  if (!f) return { overview: true, lessons: true, tests: true, analytics: true, saved: true }; // older backend
  const tests = !!f.tests;
  const handIns = !!f.hand_ins;
  return {
    overview: true,
    lessons: !!f.modules || opts.lessonCourses === true,
    // practice sets live in the Тесты tab (#practice, D6), so a course with only practice still reaches them
    tests: tests || handIns || !!f.practice,
    analytics: tests || handIns,
    saved: tests,
  };
}

export function courseTabs(course: CourseTabsCourse, pathname: string, t: T, opts: CourseTabsOptions = {}): CourseTabsResult {
  const lang = (pathname.match(LANG_RE) || [])[1] || "ru";
  const base = `/${lang}/courses/${course.id}`;
  const shown = shownTabs(course, opts);
  const active = tabOfPath(pathname, base);
  const testsLabel = course.features?.hand_ins ? t("course.tabs.assignments") : t("course.tabs.tests");
  const label: Record<CourseTabKey, string> = {
    overview: t("course.tabs.overview"),
    lessons: t("course.tabs.lessons"),
    tests: testsLabel,
    analytics: t("course.tabs.analytics"),
    saved: t("course.tabs.saved"),
  };
  const order: CourseTabKey[] = ["overview", "lessons", "tests", "analytics", "saved"];
  const tabs = order.filter((k) => shown[k]).map((k) => ({ key: k, href: base + TAB_PATH[k], label: label[k], active: active === k }));
  // only a tab's own URL is refused (object pages keep their own server answers); Уроки of an exam course waits
  // while its lesson courses are not known yet
  let hidden: CourseTabKey | null = null;
  const own = (k: CourseTabKey) => TAB_PATH[k] !== "" && pathname === base + TAB_PATH[k];
  for (const k of order) {
    if (!shown[k] && own(k)) {
      if (k === "lessons" && opts.lessonCourses === null && !course.features?.modules) break;
      hidden = k;
      break;
    }
  }
  return { tabs, active, hidden, variant: pathname === base ? "full" : "compact" };
}
