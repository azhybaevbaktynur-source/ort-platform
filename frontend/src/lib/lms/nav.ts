/**
 * Phase 8c S1 (PHASE_8C_DESIGN §2.2, §2.3, §5.3): the course sidebar links and the `from` rule.
 *
 * Dependency-free on purpose (checked by `nav.check.ts` with a standalone `tsc`): structural types only, no imports.
 *
 * - `courseNavItems(course, role, pathname, t)`: the links of the course sidebar for one role, with the active link
 *   for `pathname` (`/<lang>/courses/<id>/...`). Students (and org admins, read-only observers) see Announcements and
 *   Files only when the course has published content of that kind (`features`); staff always see them, marked
 *   `hiddenFromStudents` when the flag is false. The server stays authoritative for every list (a hidden link hides
 *   nothing the server would return).
 *   FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-1): staff get five sections (Content, Students, Grades, Analytics, Settings)
 *   then a "More" group (Announcements, Files, Practice, Question banks). Assignments is a tab of Content (its URL
 *   stays `/assignments`), so Content is active on it and on `/assessments/**`, `/attempts/**`. Students and observers
 *   keep their items and order.
 * - `safeFrom(param, fallback)`: a `?from=` value usable as a same-site link (same rule as the player's `?return=`,
 *   P8B-10): `/<lang>/...` with the fallback's language, no scheme, no `//`, no backslash, no control characters;
 *   anything else gives `fallback`.
 */

// `observer`: not the parent role, see `guardian`.
export type CourseNavRole = "teacher" | "assistant" | "student" | "observer";
export type CourseNavKey =
  | "course" | "announcements" | "assignments" | "grades" | "people" | "bank" | "settings" | "files"
  | "practice" | "progress" | "saved" | "analytics";

export interface CourseNavCourse {
  id: string;
  home_kind?: string | null;
  home_page_id?: string | null;
  features?: { modules: boolean; files: boolean; announcements: boolean; practice?: boolean } | null;
  my_enrollment: { role: string; read_only?: boolean };
}

export interface CourseNavItem {
  key: CourseNavKey;
  href: string;
  label: string;
  active: boolean;
  /** Staff only: the link is hidden from students (no published content of that kind yet). */
  hiddenFromStudents: boolean;
  /** FB8-5 S1: staff sidebar section ("more" = the labelled "More" group); students and observers have none. */
  group?: "main" | "more";
}

type T = (key: string, vars?: Record<string, string | number>) => string;

/** The sidebar role of the viewer: org admins (no enrollment, `read_only`) are read-only observers. */
export function courseNavRole(course: CourseNavCourse): CourseNavRole {
  if (course.my_enrollment.read_only) return "observer";
  const r = course.my_enrollment.role;
  return r === "teacher" || r === "assistant" ? r : "student";
}

function under(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

const LANG_RE = /^\/(en|ky|ru)(?=\/|$)/;

/**
 * `staffShape`: the server answered with the staff serializer (`isStaffCourse`): org admins reading a course of their
 * organization (Phase 9 UX). Fix round 1b: it no longer adds Question banks (see the observer list below). Settings
 * stay for course teachers only (A13).
 */
export function courseNavItems(course: CourseNavCourse, role: CourseNavRole, pathname: string, t: T,
  _opts: { staffShape?: boolean } = {}): CourseNavItem[] {
  const lang = (pathname.match(LANG_RE) || [])[1] || "ru";
  const base = `/${lang}/courses/${course.id}`;
  const staff = role === "teacher" || role === "assistant";
  const f = course.features ?? { modules: false, files: false, announcements: false, practice: false };
  const item = (key: CourseNavKey, href: string, label: string, active: boolean, shown: boolean, flag = true) =>
    shown ? [{ key, href, label, active, hiddenFromStudents: staff && !flag }] : [];
  // Course: the course page; modules and pages are reached from it (staff /modules redirects here; students keep it)
  const courseActive = pathname === base || under(pathname, `${base}/modules`) || under(pathname, `${base}/pages`);
  // quiz builder, lobby and attempt lists live under /assessments; staff attempt details under /attempts
  const assignmentsActive = under(pathname, `${base}/assignments`) || under(pathname, `${base}/assessments`)
    || under(pathname, `${base}/attempts`);
  if (staff) {
    // FB8-5 S1 (D-FB8-5-1): Content (Structure + Assignments tabs), Students, Grades, Analytics, Settings; then More
    const main = (key: CourseNavKey, href: string, label: string, active: boolean, shown = true): CourseNavItem[] =>
      item(key, href, label, active, shown).map((i) => ({ ...i, group: "main" as const }));
    const more = (key: CourseNavKey, href: string, label: string, flag = true): CourseNavItem[] =>
      item(key, href, label, under(pathname, href), true, flag).map((i) => ({ ...i, group: "more" as const }));
    return [
      ...main("course", base, t("courseNav.content"), courseActive || assignmentsActive),
      ...main("people", `${base}/people`, t("courseNav.students"), under(pathname, `${base}/people`)),
      ...main("grades", `${base}/grades`, t("gradebook.tab"), under(pathname, `${base}/grades`)),
      ...main("analytics", `${base}/analytics`, t("analytics.nav"), under(pathname, `${base}/analytics`)),
      ...main("settings", `${base}/settings`, t("courses.settings.tab"), under(pathname, `${base}/settings`), role === "teacher"),
      ...more("announcements", `${base}/announcements`, t("announcements.title"), f.announcements),
      ...more("files", `${base}/files`, t("courseFiles.title"), f.files),
      ...more("practice", `${base}/practice`, t("practice.nav"), !!f.practice),
      ...more("bank", `${base}/bank`, t("bank.tab")),
    ];
  }
  return [
    ...item("course", base, t("courses.home.tab"), courseActive, true),
    ...item("announcements", `${base}/announcements`, t("announcements.title"), under(pathname, `${base}/announcements`),
      f.announcements, f.announcements),
    ...item("assignments", `${base}/assignments`, t("assignments.tab"), assignmentsActive, true),
    // fix round 1b (per-role link check): observers (org admins reading the course) have no grades (A13): no link
    ...item("grades", `${base}/grades`, t("gradebook.tab"), under(pathname, `${base}/grades`), role !== "observer"),
    ...item("people", `${base}/people`, t(role === "student" ? "courses.people.tabStudent" : "courses.people.tab"),
      under(pathname, `${base}/people`), true),
    // fix round 1b (per-role link check): no Question banks link for observers either. It opened "only teachers and
    // assistants" (and a refused request) wherever the course has no organization-shared bank; org admins reach the
    // shared banks from Organization → Shared banks → Open (`BankGate` still lets them in there); `staffShape` is kept
    // for callers but no longer adds a link
    ...item("files", `${base}/files`, t("courseFiles.title"), under(pathname, `${base}/files`), f.files, f.files),
    // Phase 10: practice (students once a practice quiz is published), progress (students), analytics (observers)
    ...item("practice", `${base}/practice`, t("practice.nav"), under(pathname, `${base}/practice`), role === "student" && !!f.practice, !!f.practice),
    ...item("progress", `${base}/progress`, t("progress.nav"), under(pathname, `${base}/progress`), role === "student"),
    // Student UI U8: flagged questions and the mistakes notebook (moved off the progress page)
    ...item("saved", `${base}/saved`, t("student.nav.saved"), under(pathname, `${base}/saved`), role === "student"),
    ...item("analytics", `${base}/analytics`, t("analytics.nav"), under(pathname, `${base}/analytics`), role === "observer"),
  ];
}

/** Areas a student (or observer) may not open while their link is hidden (`AreaUnavailable` instead of the page). */
export function hiddenAreaFor(course: CourseNavCourse, role: CourseNavRole, pathname: string): "announcements" | "files" | null {
  if (role === "teacher" || role === "assistant") return null;
  const lang = (pathname.match(LANG_RE) || [])[1] || "ru";
  const base = `/${lang}/courses/${course.id}`;
  const f = course.features;
  if (!f) return null; // older backend: no flags, nothing hidden
  if (!f.announcements && under(pathname, `${base}/announcements`)) return "announcements";
  if (!f.files && under(pathname, `${base}/files`)) return "files";
  return null;
}

/** Same rule as the player's `?return=` (P8B-10), with the language of `fallback`. */
export function safeFrom(param: string | null | undefined, fallback: string): string {
  const lang = (fallback.match(LANG_RE) || [])[1];
  if (!param || !lang || param.length > 500) return fallback;
  if (!param.startsWith(`/${lang}/`)) return fallback;
  if (param.includes("//") || param.includes("\\")) return fallback;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(param)) return fallback;
  return param;
}

/** `href` with `from=<path>` added to its query. */
export function withFrom(href: string, from: string): string {
  const [path, hash] = href.split("#", 2);
  return `${path}${path.includes("?") ? "&" : "?"}from=${encodeURIComponent(from)}${hash !== undefined ? `#${hash}` : ""}`;
}
