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
 * - `safeFrom(param, fallback)`: a `?from=` value usable as a same-site link (same rule as the player's `?return=`,
 *   P8B-10): `/<lang>/...` with the fallback's language, no scheme, no `//`, no backslash, no control characters;
 *   anything else gives `fallback`.
 */

export type CourseNavRole = "teacher" | "assistant" | "student" | "observer";
export type CourseNavKey =
  | "course" | "announcements" | "assignments" | "grades" | "people" | "bank" | "settings" | "files";

export interface CourseNavCourse {
  id: string;
  home_kind?: string | null;
  home_page_id?: string | null;
  features?: { modules: boolean; files: boolean; announcements: boolean } | null;
  my_enrollment: { role: string; read_only?: boolean };
}

export interface CourseNavItem {
  key: CourseNavKey;
  href: string;
  label: string;
  active: boolean;
  /** Staff only: the link is hidden from students (no published content of that kind yet). */
  hiddenFromStudents: boolean;
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

export function courseNavItems(course: CourseNavCourse, role: CourseNavRole, pathname: string, t: T): CourseNavItem[] {
  const lang = (pathname.match(LANG_RE) || [])[1] || "ru";
  const base = `/${lang}/courses/${course.id}`;
  const staff = role === "teacher" || role === "assistant";
  const f = course.features ?? { modules: false, files: false, announcements: false };
  const item = (key: CourseNavKey, href: string, label: string, active: boolean, shown: boolean, flag = true) =>
    shown ? [{ key, href, label, active, hiddenFromStudents: staff && !flag }] : [];
  // Course: the course page; modules and pages are reached from it (staff /modules redirects here; students keep it)
  const courseActive = pathname === base || under(pathname, `${base}/modules`) || under(pathname, `${base}/pages`);
  return [
    ...item("course", base, t("courses.home.tab"), courseActive, true),
    ...item("announcements", `${base}/announcements`, t("announcements.title"), under(pathname, `${base}/announcements`),
      staff || f.announcements, f.announcements),
    // quiz builder, lobby and attempt lists live under /assessments; staff attempt details under /attempts
    ...item("assignments", `${base}/assignments`, t("assignments.tab"),
      under(pathname, `${base}/assignments`) || under(pathname, `${base}/assessments`) || under(pathname, `${base}/attempts`),
      true),
    ...item("grades", `${base}/grades`, t("gradebook.tab"), under(pathname, `${base}/grades`), true),
    ...item("people", `${base}/people`, t(role === "student" ? "courses.people.tabStudent" : "courses.people.tab"),
      under(pathname, `${base}/people`), true),
    ...item("bank", `${base}/bank`, t("bank.tab"), under(pathname, `${base}/bank`), staff),
    ...item("settings", `${base}/settings`, t("courses.settings.tab"), under(pathname, `${base}/settings`), role === "teacher"),
    ...item("files", `${base}/files`, t("courseFiles.title"), under(pathname, `${base}/files`), staff || f.files, f.files),
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
