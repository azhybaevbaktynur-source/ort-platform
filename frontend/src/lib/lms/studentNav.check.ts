/**
 * Dependency-free check of the student shell's links (STUDENT_UI_DESIGN §2.2) and the УРОКИ group's lesson-course rows
 * (TEACHER_TO_STUDENT_MAP §2.4).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_snav --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/studentNav.ts src/lib/lms/studentNav.check.ts && node /tmp/agy_snav/studentNav.check.js
 */
import { LESSON_ROWS_MAX, courseIdOfPath, lessonCourseLinks, studentNavLinks } from "./studentNav";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const exam = "ex1";
const nav = (rest: string, features = { modules: true, practice: true }) =>
  studentNavLinks({ lang: "ru", rest, tab: null, courseId: exam, features });

// --- the exam's own links (unchanged) ---
ok(nav("/courses").home?.active === true, "home active on /courses");
ok(nav(`/courses/${exam}`).tests?.active === true, "tests active on the course page");
ok(nav(`/courses/${exam}/modules`).lessons?.active === true, "own Уроки active on the syllabus");
ok(nav(`/courses/${exam}/modules`, { modules: false, practice: true }).lessons === null, "own Уроки hidden without lessons");
ok(nav(`/courses/${exam}/lessons`).lessons?.active === false, "own Уроки not active on Все уроки");
ok(nav("/courses/lc1/modules").lessons?.active === false, "own Уроки not active inside a lesson course");
ok(studentNavLinks({ lang: "ru", rest: "/courses", tab: null, courseId: null, features: null }).tests === null, "no exam: no tests link");
ok(courseIdOfPath("/courses/catalog/lc1") === null, "catalog landing is not a course path");

// --- lesson-course rows ---
const row = (id: string, enrolled: boolean, progress: { done: number; total: number } | null = null) => ({ id, enrolled, progress });
const rows = [row("lc1", true, { done: 2, total: 6 }), row("lc2", false), row("lc3", true, { done: 0, total: 0 }), row("lc4", true, null)];
const r = lessonCourseLinks({ lang: "ru", rest: "/courses/lc1/modules/i1", examId: exam, rows });
ok(r.rows.length === 4 && r.all === null, "four rows, no Все уроки");
ok(r.rows[0].href === "/ru/courses/lc1/modules", "enrolled row opens the overview");
ok(r.rows[1].href === "/ru/courses/catalog/lc2", "not enrolled row opens the catalog landing");
ok(r.rows[0].active && !r.rows[1].active, "row active inside its lesson course only");
ok(r.rows[0].progress?.done === 2 && r.rows[0].progress?.total === 6, "enrolled row has the ring");
ok(r.rows[1].progress === null, "not enrolled: no ring");
ok(r.rows[2].progress === null && r.rows[3].progress === null, "nothing to finish: no ring");
ok(lessonCourseLinks({ lang: "ru", rest: "/courses/catalog/lc2", examId: exam, rows }).rows[1].active, "row active on its landing");
ok(lessonCourseLinks({ lang: "ru", rest: "/courses", examId: null, rows }).rows.length === 0, "no exam: no rows");
ok(lessonCourseLinks({ lang: "ru", rest: "/courses", examId: exam, rows: null }).rows.length === 0, "not loaded: no rows");

const many = Array.from({ length: LESSON_ROWS_MAX + 1 }, (_, i) => row(`m${i}`, false));
const m = lessonCourseLinks({ lang: "ru", rest: `/courses/${exam}/lessons`, examId: exam, rows: many });
ok(m.rows.length === LESSON_ROWS_MAX, `capped at ${LESSON_ROWS_MAX} rows`);
ok(m.all?.href === `/ru/courses/${exam}/lessons` && m.all.active, "Все уроки link, active on its page");
ok(lessonCourseLinks({ lang: "ru", rest: "/courses", examId: exam, rows: many.slice(0, LESSON_ROWS_MAX) }).all === null,
  `exactly ${LESSON_ROWS_MAX}: no Все уроки`);

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
