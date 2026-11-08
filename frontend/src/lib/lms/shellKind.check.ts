/**
 * Dependency-free check of the shell decision (PERFORMANCE_AUDIT §5.1, S1).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_shell --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/studentNav.ts src/lib/lms/shellKind.ts src/lib/lms/shellKind.check.ts && node /tmp/agy_shell/shellKind.check.js
 */
import { shellKindFor, urlAreaFor, type ShellArea, type ShellMe } from "./shellKind";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const student: ShellMe = { is_teacher: false, can_create_courses: false, is_platform_admin: false, has_student_enrollments: true };
const teacherOnly: ShellMe = { is_teacher: true, can_create_courses: true, is_platform_admin: false, has_student_enrollments: false };
const teacherLearning: ShellMe = { ...teacherOnly, has_student_enrollments: true };
const teacherOld: ShellMe = { is_teacher: true, can_create_courses: true, is_platform_admin: false }; // answer without the field
const admin: ShellMe = { is_teacher: false, can_create_courses: true, is_platform_admin: true, has_student_enrollments: false };
const kind = (rest: string, me: ShellMe | null, view: string | null = null, declared: ShellArea | null = null) =>
  shellKindFor({ rest, view, declared, me });

// --- student: cold (nothing cached) and warm (cached answer) ---
ok(kind("/courses", null) === "neutral", "student cold on /courses: neutral");
ok(kind("/courses", student) === "student", "student warm on /courses: student");
ok(kind("/courses/c1/tests", null) === "neutral", "student cold on a course page: neutral");
ok(kind("/courses/c1/tests", student) === "student", "student warm on a course page: student, no waiting");
ok(kind("/courses/catalog", student) === "student", "student on the catalog: student");

// --- teacher without enrollments on /courses ---
ok(kind("/courses", teacherOnly) === "app", "teacher (no enrollments) on /courses: app");
ok(kind("/courses", teacherOnly, "teaching") === "app", "teacher on ?view=teaching: app");
ok(kind("/courses", teacherOnly, "learning") === "app", "teacher without Learning on ?view=learning: app (the page opens Teaching)");
ok(urlAreaFor("/courses", "learning", teacherOnly) === "teaching", "without Learning, /courses is Teaching");

// --- teacher with enrollments ---
ok(kind("/courses", teacherLearning) === "app", "teacher (learns too) on /courses: app (Teaching opens first)");
ok(kind("/courses", teacherLearning, "teaching") === "app", "teacher (learns too) on ?view=teaching: app");
ok(kind("/courses", teacherLearning, "learning") === "student", "teacher (learns too) on ?view=learning: student");
ok(kind("/courses", teacherOld, "learning") === "student", "an older answer without the field keeps Learning");

// --- admin ---
ok(kind("/admin", null) === "app", "admin cold on /admin: app (the URL decides)");
ok(kind("/admin", admin) === "app", "admin warm on /admin: app");
ok(kind("/admin/users", admin) === "app", "admin on /admin/users: app");
ok(kind("/org/o1", null) === "app" && kind("/grading-schemes", null) === "app", "other areas' URLs: app without an answer");
ok(kind("/courses", admin) === "app", "admin (creates, learns nowhere) on /courses: app");

// --- teacher on a course page, before and after the course's declaration ---
ok(kind("/courses/c1", teacherOnly) === "neutral", "teacher on a course page before the declaration: neutral");
ok(kind("/courses/c1/people", teacherOnly, null, "teaching") === "app", "declared teaching: app");
ok(kind("/courses/c1", teacherLearning, null, "learning") === "student", "declared learning (a course they study): student");
ok(kind("/courses/c1", null, null, "teaching") === "neutral", "declared but nothing known about the person: neutral");
ok(kind("/courses/new", teacherOnly) === "app" && kind("/courses/trash", null) === "app", "/courses/new and /courses/trash: app");
ok(kind("/courses/join", teacherOnly) === "student", "/courses/join is not a course page: no waiting");

// --- player route ---
ok(kind("/courses/c1/attempts/a1", null) === "player", "player route, cold: player");
ok(kind("/courses/c1/attempts/a1", teacherOnly, null, "teaching") === "player", "player route, staff: player");
ok(kind("/courses/c1/attempts/a1/result", student) === "student", "result page is not the player");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
