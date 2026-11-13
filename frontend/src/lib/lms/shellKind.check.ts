/**
 * Dependency-free check of the shell decision (PERFORMANCE_AUDIT §5.1, S1).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_shell --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/studentNav.ts src/lib/lms/shellKind.ts src/lib/lms/shellKind.check.ts && node /tmp/agy_shell/shellKind.check.js
 */
import { activeAreaFor, hidesLearning, learnsHere, shellKindFor, urlAreaFor, type ShellArea, type ShellMe } from "./shellKind";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const student: ShellMe = { is_teacher: false, can_create_courses: false, is_platform_admin: false, has_student_enrollments: true };
const teacherOnly: ShellMe = { is_teacher: true, can_create_courses: true, is_platform_admin: false, has_student_enrollments: false };
const teacherLearning: ShellMe = { ...teacherOnly, has_student_enrollments: true };
const teacherOld: ShellMe = { is_teacher: true, can_create_courses: true, is_platform_admin: false }; // answer without the field
const admin: ShellMe = { is_teacher: false, can_create_courses: true, is_platform_admin: true, has_student_enrollments: false };
const adminOnly: ShellMe = { is_teacher: false, can_create_courses: false, is_platform_admin: true }; // creates and teaches nothing
const kind = (rest: string, me: ShellMe | null, declared: ShellArea | null = null) =>
  shellKindFor({ rest, declared, me });

// --- student: cold (nothing cached) and warm (cached answer) ---
ok(kind("/courses", null) === "neutral", "student cold on /courses: neutral");
ok(kind("/courses", student) === "student", "student warm on /courses: student");
ok(kind("/courses/c1/tests", null) === "neutral", "student cold on a course page: neutral");
ok(kind("/courses/c1/tests", student) === "student", "student warm on a course page: student, no waiting");
ok(kind("/courses/catalog", student) === "student", "student on the catalog: student");

// --- teacher without enrollments on /courses ---
ok(kind("/courses", teacherOnly) === "app", "teacher (no enrollments) on /courses: app");
ok(urlAreaFor("/courses", teacherOnly) === "teaching", "without Learning, /courses is Teaching");

// --- teacher with student enrollments (owner decision 2026-11-12, fix round 1e: ignored, no Learning) ---
ok(kind("/courses", teacherLearning) === "app", "teacher (with enrollments) on /courses: app");
ok(urlAreaFor("/courses", teacherLearning) === "teaching", "teacher (with enrollments): /courses is Teaching");
ok(kind("/courses", teacherOld) === "app", "an older answer without the field: no Learning either");
ok(hidesLearning(teacherLearning) && hidesLearning(admin) && !hidesLearning(student) && !hidesLearning(null),
  "hidesLearning: everyone who teaches, nobody else");

// --- admin ---
ok(kind("/admin", null) === "app", "admin cold on /admin: app (the URL decides)");
ok(kind("/admin", admin) === "app", "admin warm on /admin: app");
ok(kind("/admin/users", admin) === "app", "admin on /admin/users: app");
ok(kind("/org/o1", null) === "app" && kind("/grading-schemes", null) === "app", "other areas' URLs: app without an answer");
ok(kind("/courses", admin) === "app", "admin (creates, learns nowhere) on /courses: app");

// --- teacher on a course page (fix round 1b: the person decides, no waiting for the course's declaration) ---
ok(kind("/courses/c1", teacherOnly) === "app", "teacher on a course page before the declaration: app at once");
ok(kind("/courses/c1/people", teacherOnly, "teaching") === "app", "declared teaching: app");
ok(kind("/courses/c1", teacherLearning, "learning") === "app", "a course a teacher once joined as a student: app, never the student frame");
ok(activeAreaFor("/courses/c1", "learning", teacherLearning) === "teaching", "...and the header shows Teaching, not Learning");
ok(activeAreaFor("/courses/c1", "teaching", teacherOnly) === "teaching", "a course they teach: Teaching");
ok(activeAreaFor("/courses/c1", "learning", student) === "learning", "a student's course: Learning");
ok(kind("/courses/c1", null, "teaching") === "neutral", "declared but nothing known about the person: neutral");
ok(kind("/courses/c1", student, "learning") === "student", "a student's course page: student");
ok(kind("/courses/new", teacherOnly) === "app" && kind("/courses/trash", null) === "app", "/courses/new and /courses/trash: app");
ok(kind("/courses/join", teacherOnly) === "app" && kind("/courses/join", student) === "student", "/courses/join: the person decides");

// --- fix round 1b: URLs no staff area claims (Pro, Privacy, the catalog, invitations, anything new) ---
// step 3a S3: /home (the hub) and /courses/choose (S7: a redirect to the catalog) are Learning for learners, the home
// area otherwise
for (const rest of ["/home", "/courses/choose", "/pro", "/privacy", "/courses/catalog", "/courses/catalog/c1", "/courses/catalog/c1/apply", "/courses/join", "/invitations", "/courses/become-teacher", "/something-new"]) {
  ok(kind(rest, student) === "student", `student on ${rest}: student`);
  ok(kind(rest, teacherOnly) === "app" && urlAreaFor(rest, teacherOnly) === "teaching", `teacher on ${rest}: app, Teaching`);
  ok(kind(rest, teacherLearning) === "app" && urlAreaFor(rest, teacherLearning) === "teaching", `teacher with an old enrolment on ${rest}: app, Teaching`);
  ok(kind(rest, admin) === "app" && urlAreaFor(rest, admin) === "teaching", `admin who creates courses on ${rest}: app, Teaching`);
  ok(kind(rest, adminOnly) === "app" && urlAreaFor(rest, adminOnly) === "platform", `admin who teaches nothing on ${rest}: app, Platform`);
  ok(kind(rest, null) === "neutral", `nobody known yet on ${rest}: neutral`);
}
ok(learnsHere(student) && !learnsHere(teacherOnly) && !learnsHere(teacherLearning) && !learnsHere(admin) && !learnsHere(adminOnly),
  "learnsHere: only people who teach nothing (Pro in the account menu)");
ok(urlAreaFor("/admin", adminOnly) === "platform" && urlAreaFor("/org/o1", teacherOnly) === "organization",
  "claimed URLs keep their area");

// --- player route ---
ok(kind("/courses/c1/attempts/a1", null) === "player", "player route, cold: player");
ok(kind("/courses/c1/attempts/a1", teacherOnly, "teaching") === "player", "player route, staff: player");
// step 3a S3: /courses is the person's home area (coursesDefault is gone): a platform admin who teaches nothing: Platform
ok(urlAreaFor("/courses", adminOnly) === "platform" && urlAreaFor("/courses", admin) === "teaching" && urlAreaFor("/courses", student) === "learning",
  "/courses: Learning for learners, the home area for everyone else");
ok(kind("/home", student) === "student" && kind("/home", teacherOnly) === "app", "/home: the student frame for learners, never for teachers");
ok(kind("/courses/c1/attempts/a1/result", student) === "student", "result page is not the player");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
