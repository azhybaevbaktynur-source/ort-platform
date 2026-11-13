/**
 * Dependency-free check of the student frame's links (step 3a S3, STUDENT_IA_DESIGN §2.1, §2.5; S7 v3 V1, V7, V8): the
 * two global links (no course id in either) and the «Мои курсы» rows.
 * Run: cd frontend && npx tsc --outDir /tmp/agy_snav --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/lastPlace.ts src/lib/lms/studentNav.ts src/lib/lms/studentNav.check.ts && node /tmp/agy_snav/studentNav.check.js
 */
import { COURSE_ROWS_MAX, courseIdOfPath, courseRows, studentNavLinks } from "./studentNav";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

// --- the global links ---
const nav = (rest: string, testStudent = false) => studentNavLinks({ lang: "ru", rest, testStudent });
ok(nav("/home").home.active && nav("/home").home.href === "/ru/home", "Главная is /home, active there");
ok(!("courses" in nav("/home")), "no «Мои курсы» link (v3 V1: the hub shows the courses)");
ok(nav("/courses/catalog/c1").catalog?.active === true && nav("/courses/catalog").catalog?.href === "/ru/courses/catalog", "Каталог active on a landing");
ok(!nav("/courses/c1/tests").catalog?.active && !nav("/courses/c1/tests").home.active, "inside a course: no global link is current");
ok(nav("/home", true).catalog === null, "the test student has no Каталог");
for (const l of [nav("/courses/c1").home, nav("/courses/c1").catalog!]) {
  ok(!/\/courses\/c1/.test(l.href), `no course id in the global ${l.key} link`);
}

ok(courseIdOfPath("/courses/catalog/lc1") === null, "catalog landing is not a course path");
ok(courseIdOfPath("/courses/choose") === null, "the choose step is not a course path");
ok(courseIdOfPath("/courses/c1/tests") === "c1", "a course tab names its course");

// --- the «Мои курсы» rows ---
const mk = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `c${i}`, progress: i === 0 ? { done: 2, total: 5 } : i === 1 ? { done: 0, total: 0 } : null }));
const rows = (rest: string, n: number, recent: string[] = [], extra: Partial<Parameters<typeof courseRows>[0]> = {}) =>
  courseRows({ lang: "ru", rest, courses: mk(n), recent, place: null, loaded: true, ...extra });

const one = rows("/courses/c0/tests", 1);
ok(one.rows.length === 1 && one.all === null, "one course: one row");
ok(one.rows[0].active && one.rows[0].href === "/ru/courses/c0", "the viewed course's row is current; no place: Обзор");
ok(one.rows[0].progress?.done === 2, "a row with something to finish has the ring");
ok(rows("/home", 2).rows[1].progress === null, "nothing to finish: no ring");

const eight = rows("/home", 8, ["c5", "c7"]);
ok(eight.rows.length === COURSE_ROWS_MAX, `capped at ${COURSE_ROWS_MAX} rows`);
ok(eight.rows[0].course.id === "c5" && eight.rows[1].course.id === "c7" && eight.rows[2].course.id === "c0", "recent first, then the home's order");
ok(eight.all?.count === 8 && eight.all.href === "/ru/home#courses", "«Все курсы (8)» → /home#courses (v3 V7)");
ok(rows("/home", COURSE_ROWS_MAX).all === null, `exactly ${COURSE_ROWS_MAX}: no «Все курсы»`);
const deep = rows("/courses/c7/saved", 8);
ok(deep.rows.some((r) => r.course.id === "c7" && r.active) && deep.rows.length === COURSE_ROWS_MAX, "the viewed course is shown even past the cap");

const placed = rows("/home", 3, ["c2"], { place: { courseId: "c2", path: "/ru/courses/c2/analytics", kind: "analytics", at: 1 } });
ok(placed.rows[0].href === "/ru/courses/c2/analytics" && placed.rows[1].href === "/ru/courses/c0", "the last place's course opens its last tab");

const zero = rows("/home", 0);
ok(zero.rows.length === 0 && zero.all === null && !("choose" in zero), "no courses: no rows, no «Выбрать курсы» (v3 V8: the group is hidden)");
ok(rows("/home", 3, [], { loaded: false }).rows.length === 0, "not loaded: nothing yet");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
