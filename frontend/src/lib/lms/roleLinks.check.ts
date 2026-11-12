/**
 * Fix round 2026-11-12 1b: the per-role link table, checked without a browser (like `shellKind.check.ts`).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_links --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/shellKind.ts src/lib/lms/roleLinks.ts src/lib/lms/roleLinks.check.ts && node /tmp/agy_links/roleLinks.check.js
 */
import { expectedArea, expectedFrame, expectsLearning, expectsPro, ROLES, splitPath, type Role } from "./roleLinks";
import type { ShellArea, ShellKind } from "./shellKind";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

type Row = [href: string, frame: ShellKind, area: ShellArea];
const STAFF: Role[] = ["teacher", "teacher_enrolled", "org_admin", "platform_admin"];

// --- the student: every personal URL in the student frame, the Learning area ---
const studentRows: Row[] = [
  ["/ru/courses", "student", "learning"],
  ["/ru/courses?view=learning", "student", "learning"], // step 3a S3: the page sends a learner on to /home
  // step 3a S3 (STUDENT_IA_DESIGN §2.1): the hub and the choose step
  ["/ru/home", "student", "learning"],
  ["/ru/courses/choose", "student", "learning"],
  ["/ru/courses/c1", "student", "learning"],
  ["/ru/courses/c1/tests", "student", "learning"],
  // step 3a S2: the course tabs (STUDENT_IA_DESIGN §3.2) and the lobby
  ["/ru/courses/c1/lessons", "student", "learning"],
  ["/ru/courses/c1/analytics", "student", "learning"],
  ["/ru/courses/c1/saved", "student", "learning"],
  ["/ru/courses/c1/assessments/x1", "student", "learning"],
  ["/ru/courses/c1/attempts/a1/result", "student", "learning"],
  ["/ru/courses/catalog", "student", "learning"],
  ["/ru/courses/catalog/c1", "student", "learning"],
  ["/ru/courses/join", "student", "learning"],
  ["/ru/pro", "student", "learning"],
  ["/ru/privacy", "student", "learning"],
  ["/ru/invitations", "student", "learning"],
  ["/ky/pro", "student", "learning"],
  ["/ru/courses/c1/attempts/a1", "player", "learning"],
];
for (const [href, frame, area] of studentRows) {
  ok(expectedFrame("student", href) === frame, `student ${href}: frame ${frame}`);
  ok(expectedArea("student", href) === area, `student ${href}: area ${area}`);
}

// --- everyone who teaches or administers: the app frame everywhere, never Learning ---
const staffRows: Row[] = [
  ["/ru/courses", "app", "teaching"],
  ["/ru/courses?view=teaching", "app", "teaching"],
  // step 3a S3: the hub and the choose step are never a student frame for people who teach (their home area)
  ["/ru/home", "app", "teaching"],
  ["/ru/courses/choose", "app", "teaching"],
  ["/ru/courses?view=learning", "app", "teaching"],
  ["/ru/courses/c1", "app", "teaching"],
  ["/ru/courses/c1/people", "app", "teaching"],
  ["/ru/courses/c1/lessons", "app", "teaching"],
  ["/ru/courses/c1/analytics", "app", "teaching"],
  ["/ru/courses/c1/saved", "app", "teaching"],
  ["/ru/courses/new", "app", "teaching"],
  ["/ru/grading-schemes", "app", "teaching"],
  ["/ru/exam-templates", "app", "teaching"],
  ["/ru/courses/catalog", "app", "teaching"],
  ["/ru/courses/catalog/c1", "app", "teaching"],
  ["/ru/courses/join", "app", "teaching"],
  ["/ru/pro", "app", "teaching"],
  ["/ru/privacy", "app", "teaching"],
  ["/ru/invitations", "app", "teaching"],
  ["/ru/org/o1", "app", "organization"],
  ["/ru/org/o1/teachers", "app", "organization"],
  ["/ru/admin", "app", "platform"],
  ["/ru/admin/users", "app", "platform"],
  ["/ru/admin/catalog", "app", "platform"], // step 3b S2: Admin → Каталог (the page refuses anyone but the platform admin)
  ["/ru/admin/catalog?state=blocked", "app", "platform"],
  // step 3b S3: Admin → Преподаватели (platform admin only); the old requests address redirects into its second tab
  ["/ru/admin/teachers", "app", "platform"],
  ["/ru/admin/teachers?tab=requests", "app", "platform"],
  ["/ru/admin/teacher-requests", "app", "platform"],
  ["http://127.0.0.1:3780/ru/pro#x", "app", "teaching"],
];
for (const role of STAFF) {
  for (const [href, frame, area] of staffRows) {
    ok(expectedFrame(role, href) === frame, `${role} ${href}: frame ${frame}`);
    ok(expectedArea(role, href) === area, `${role} ${href}: area ${area}`);
  }
}

// --- menu contents ---
ok(expectsPro("student") && STAFF.every((r) => !expectsPro(r)), "Pro only for the student");
ok(expectsLearning("student") && STAFF.every((r) => !expectsLearning(r)), "Learning only for the student");
ok(ROLES.length === 5, "five roles, no teacher+student role (owner decision 2026-11-12)");

// --- path parsing ---
ok(splitPath("/ru").rest === "/" && splitPath("/ru/courses/").rest === "/courses", "language prefix and trailing slash");
ok(splitPath("/ru/courses?view=teaching&x=1").view === "teaching", "?view= is read");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
