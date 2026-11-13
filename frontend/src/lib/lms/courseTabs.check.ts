/**
 * Dependency-free check of the course-space tabs (STUDENT_IA_DESIGN §3.2, §3.5).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_tabs --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/courseTabs.ts src/lib/lms/courseTabs.check.ts && node /tmp/agy_tabs/courseTabs.check.js
 */
import { courseTabs, shownTabs, tabOfPath, type CourseTabKey, type CourseTabsCourse } from "./courseTabs";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const t = (k: string) => k;
const base = "/ru/courses/c1";
const NONE = { modules: false, files: false, announcements: false, practice: false, tests: false, hand_ins: false };
const course = (f: Partial<typeof NONE> | null): CourseTabsCourse => ({ id: "c1", features: f === null ? null : { ...NONE, ...f } });
const keys = (c: CourseTabsCourse, opts = {}) => courseTabs(c, base, t, opts).tabs.map((x) => x.key).join(",");

// every route of app/[lang]/courses/[courseId]/** a student reaches -> the parent tab
const ROUTES: [string, CourseTabKey][] = [
  ["", "overview"], ["/lessons", "lessons"], ["/modules", "lessons"], ["/modules/m1/items/i1", "lessons"],
  ["/pages/p1", "lessons"], ["/tests", "tests"], ["/assessments/a1", "tests"], ["/attempts/t1", "tests"],
  ["/attempts/t1/result", "tests"], ["/assignments", "tests"], ["/assignments/a1", "tests"], ["/practice", "tests"],
  ["/analytics", "analytics"], ["/progress", "analytics"], ["/grades", "analytics"], ["/saved", "saved"],
  ["/announcements", "overview"], ["/files", "overview"], ["/people", "overview"],
];
for (const [suffix, key] of ROUTES) {
  ok(tabOfPath(base + suffix, base) === key, `${suffix || "/"} -> ${key}`);
  const all = courseTabs(course({ modules: true, tests: true, practice: true }), base + suffix, t);
  ok(all.tabs.filter((x) => x.active).map((x) => x.key).join(",") === key, `${suffix || "/"}: one active tab ${key}`);
  ok(all.variant === (suffix === "" ? "full" : "compact"), `${suffix || "/"}: ${suffix === "" ? "full" : "compact"} header`);
}
ok(tabOfPath("/ru/courses/c2/tests", base) === null, "another course: no tab");
ok(tabOfPath("/ru/courses/c10", base) === null, "a longer id is not this course");

// visibility (design §3.2 examples)
ok(keys(course({})) === "overview", "nothing published: Обзор only");
ok(keys(course({ tests: true })) === "overview,tests,analytics,saved", "only tests: Обзор · Тесты · Аналитика · Повторение");
ok(keys(course({ modules: true })) === "overview,lessons", "only lessons: Обзор · Уроки");
ok(keys(course({ modules: true, tests: true })) === "overview,lessons,tests,analytics,saved", "both: all five");
ok(keys(course({ hand_ins: true })) === "overview,tests,analytics", "only hand-ins: Задания · Аналитика, no Повторение");
ok(keys(course({ practice: true })) === "overview,tests", "only practice: Тесты (its #practice section)");
ok(keys(course({}), { lessonCourses: true }) === "overview,lessons", "exam with lesson courses: Уроки");
ok(keys(course({}), { lessonCourses: false }) === "overview", "exam without lesson courses: no Уроки");
ok(keys(course(null)) === "overview,lessons,tests,analytics,saved", "older backend: every tab");
ok(shownTabs(course({ announcements: true, files: true })).lessons === false, "announcements and files are no tabs");

// label rule (D4)
const label = (f: Partial<typeof NONE>) => courseTabs(course(f), base, t).tabs.find((x) => x.key === "tests")?.label;
ok(label({ tests: true }) === "course.tabs.tests", "quizzes only: Тесты");
ok(label({ tests: true, hand_ins: true }) === "course.tabs.assignments", "a hand-in: Задания");
ok(label({ hand_ins: true }) === "course.tabs.assignments", "hand-ins only: Задания");

// hrefs keep the language
const ky = courseTabs(course({ modules: true, tests: true }), "/ky/courses/c1/saved", t);
ok(ky.tabs.map((x) => x.href).join(" ") === "/ky/courses/c1 /ky/courses/c1/lessons /ky/courses/c1/tests /ky/courses/c1/analytics /ky/courses/c1/saved", "hrefs in the page's language");

// hidden tab opened by URL
const hid = (f: Partial<typeof NONE> | null, suffix: string, opts = {}) => courseTabs(course(f), base + suffix, t, opts).hidden;
ok(hid({}, "/tests") === "tests", "no tests: /tests is hidden");
ok(hid({}, "/analytics") === "analytics", "no tests: /analytics is hidden");
ok(hid({}, "/saved") === "saved", "no tests: /saved is hidden");
ok(hid({}, "/lessons") === "lessons", "no lessons: /lessons is hidden");
ok(hid({}, "/lessons", { lessonCourses: null }) === null, "exam course, lesson courses not known yet: wait");
ok(hid({}, "/lessons", { lessonCourses: true }) === null, "exam course with lesson courses: /lessons shown");
ok(hid({ tests: true }, "/tests") === null, "tests: /tests shown");
ok(hid({}, "/assessments/a1") === null, "object pages are never refused here (the server answers)");
ok(hid({}, "") === null, "Обзор is never hidden");
ok(hid(null, "/saved") === null, "older backend: nothing hidden");
ok(hid({ hand_ins: true }, "/saved") === "saved", "hand-ins only: /saved hidden");

if (failed) {
  console.error(`${failed} check(s) failed`);
  process.exit(1);
}
console.log("all course tab checks passed");
