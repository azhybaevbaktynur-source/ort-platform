/**
 * Dependency-free check of the course sidebar links and `safeFrom` (PHASE_8C_DESIGN §2.2, §5.3, §14).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_nav --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/nav.ts src/lib/lms/nav.check.ts && node /tmp/agy_nav/nav.check.js
 */
import { courseNavItems, courseNavRole, hiddenAreaFor, safeFrom, withFrom, type CourseNavCourse, type CourseNavRole } from "./nav";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const t = (k: string) => k;
const cid = "c1";
const base = `/en/courses/${cid}`;
const course = (role: string, features = { modules: true, files: false, announcements: false }, extra = {}): CourseNavCourse =>
  ({ id: cid, features, my_enrollment: { role }, ...extra });

// every route of app/[lang]/courses/[courseId]/** -> the active link
const ROUTES: [string, string][] = [
  ["", "course"], ["/modules", "course"], ["/pages", "course"], ["/pages/p1", "course"], ["/pages/p1/edit", "course"],
  ["/pages/new", "course"], ["/announcements", "announcements"], ["/assignments", "assignments"],
  ["/assignments/a1", "assignments"], ["/assignments/a1/edit", "assignments"], ["/assignments/a1/grade", "assignments"],
  ["/assessments", "assignments"], ["/assessments/x1", "assignments"], ["/assessments/x1/edit", "assignments"],
  ["/assessments/x1/attempts", "assignments"], ["/assessments/x1/attempts/t1", "assignments"],
  ["/attempts/t1", "assignments"], ["/grades", "grades"], ["/people", "people"], ["/bank", "bank"],
  ["/bank/questions/q1", "bank"], ["/bank/passages/p1", "bank"], ["/bank/import", "bank"], ["/settings", "settings"],
  ["/files", "files"],
];

const ROLES: CourseNavRole[] = ["teacher", "assistant", "student", "observer"];
for (const role of ROLES) {
  const all = { modules: true, files: true, announcements: true };
  for (const [suffix, key] of ROUTES) {
    const items = courseNavItems(course(role, all), role, base + suffix, t);
    const active = items.filter((i) => i.active).map((i) => i.key);
    const visible = items.some((i) => i.key === key);
    ok(visible ? active.length === 1 && active[0] === key : active.length === 0,
      `${role} ${suffix || "/"} -> ${visible ? key : "(no link)"}`);
  }
}

const keys = (role: CourseNavRole, f = { modules: true, files: false, announcements: false }) =>
  courseNavItems(course(role, f), role, base, t).map((i) => i.key).join(",");
ok(keys("teacher") === "course,announcements,assignments,grades,people,bank,settings,files", "teacher: all eight links");
ok(keys("assistant") === "course,announcements,assignments,grades,people,bank,files", "assistant: no settings");
ok(keys("student") === "course,assignments,grades,people", "student: announcements and files auto-hidden");
ok(keys("student", { modules: true, files: true, announcements: true }) === "course,announcements,assignments,grades,people,files",
  "student: shown with published content");
ok(keys("observer") === "course,assignments,grades,people", "observer without the staff shape: no banks, no settings");
ok(courseNavItems(course("observer"), "observer", base, t, { staffShape: true }).map((i) => i.key).join(",")
  === "course,assignments,grades,people,bank", "org admin (staff shape): question banks, no settings");
const marks = courseNavItems(course("teacher"), "teacher", base, t).filter((i) => i.hiddenFromStudents).map((i) => i.key);
ok(marks.join(",") === "announcements,files", "staff: hidden-from-students marks");
ok(courseNavItems(course("student"), "student", base, t).every((i) => !i.hiddenFromStudents), "students: no marks");
ok(courseNavItems(course("student"), "student", base, t).find((i) => i.key === "people")?.label === "courses.people.tabStudent",
  "students: people link is 'Teachers'");
ok(courseNavItems(course("teacher"), "teacher", `/ky/courses/${cid}/grades`, t)[0].href === `/ky/courses/${cid}`, "language from the path");
ok(courseNavRole(course("student", undefined, { my_enrollment: { role: "student", read_only: true } })) === "observer", "read_only -> observer");
ok(courseNavRole(course("assistant")) === "assistant" && courseNavRole(course("teacher")) === "teacher", "staff roles");

// auto-hide: the "not available" page for students only
ok(hiddenAreaFor(course("student"), "student", `${base}/announcements`) === "announcements", "student: hidden announcements");
ok(hiddenAreaFor(course("student"), "student", `${base}/files`) === "files", "student: hidden files");
ok(hiddenAreaFor(course("teacher"), "teacher", `${base}/files`) === null, "staff: never hidden");
ok(hiddenAreaFor(course("student", { modules: true, files: true, announcements: true }), "student", `${base}/files`) === null, "published: open");
ok(hiddenAreaFor({ id: cid, my_enrollment: { role: "student" } }, "student", `${base}/files`) === null, "no flags: open");

// safeFrom
const fb = "/en/courses/c1/assignments";
ok(safeFrom("/en/courses/c1#m-1", fb) === "/en/courses/c1#m-1", "same-language path accepted");
ok(safeFrom(null, fb) === fb && safeFrom("", fb) === fb, "missing -> fallback");
ok(safeFrom("//evil.example/x", fb) === fb, "protocol-relative rejected");
ok(safeFrom("https://evil.example/en/x", fb) === fb, "scheme rejected");
ok(safeFrom("javascript:alert(1)", fb) === fb, "javascript: rejected");
ok(safeFrom("/ru/courses/c1", fb) === fb, "other language rejected");
ok(safeFrom("/en/courses//c1", fb) === fb, "inner // rejected");
ok(safeFrom("/en/courses\\c1", fb) === fb, "backslash rejected");
ok(safeFrom("/en/courses/c1\n", fb) === fb, "control character rejected");
ok(safeFrom("/en/" + "x".repeat(600), fb) === fb, "too long rejected");
ok(withFrom("/en/courses/c1/assignments/a1?tab=settings", "/en/courses/c1#m-2")
  === "/en/courses/c1/assignments/a1?tab=settings&from=%2Fen%2Fcourses%2Fc1%23m-2", "withFrom appends");

if (failed) { console.error(`${failed} failed`); process.exit(1); }
console.log("all passed");
