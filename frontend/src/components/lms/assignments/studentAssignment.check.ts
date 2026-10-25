/**
 * Dependency-free check of the student assignment view model.
 * Run: cd frontend && npx tsc --outDir /tmp/agy_sa --module commonjs --target es2020 --skipLibCheck \
 *   src/components/lms/assignments/studentAssignment.ts src/components/lms/assignments/studentAssignment.check.ts && \
 *   node /tmp/agy_sa/components/lms/assignments/studentAssignment.check.js
 */
import { assignmentHref, primaryAssignmentId, sortForStudent, studentAssignmentView } from "./studentAssignment";
import type { AssignmentStudentOut } from "../../../lib/lms/assignmentTypes";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const NOW = Date.parse("2026-10-26T12:00:00Z");
const a = (over: Partial<AssignmentStudentOut>): AssignmentStudentOut => ({
  id: "a", kind: "text", assessment_id: null, title: { en: "A" }, points_possible: "10", due_at: null,
  available_from: null, available_until: null, status: "not_started", ...over,
});

ok(studentAssignmentView(a({}), NOW).action === "hand_in", "open text assignment -> hand in");
ok(studentAssignmentView(a({ status: "submitted" }), NOW).action === "open", "handed in -> open");
ok(studentAssignmentView(a({ available_until: "2026-10-25T00:00:00Z" }), NOW).action === "open", "closed window -> open");
ok(studentAssignmentView(a({ available_from: "2026-10-27T00:00:00Z" }), NOW).opensLater, "opens later");
ok(studentAssignmentView(a({ available_until: "2026-10-25T00:00:00" }), NOW).windowClosed, "zone-less time is UTC");
ok(studentAssignmentView(a({ kind: "quiz", assessment_id: "q", attempts_left: 2 }), NOW).action === "start", "quiz with attempts -> start");
ok(studentAssignmentView(a({ kind: "quiz", assessment_id: "q", attempts_left: 0 }), NOW).noAttemptsLeft, "quiz without attempts");
ok(studentAssignmentView(a({ kind: "quiz", status: "in_progress" }), NOW).action === "continue", "running quiz -> continue");
ok(studentAssignmentView(a({ kind: "none" }), NOW).action === "open", "offline -> open");
ok(studentAssignmentView(a({}), NOW, true).action === "open", "read-only viewer -> open only");
ok(assignmentHref("/b", a({ kind: "quiz", assessment_id: "q" })) === "/b/assessments/q", "quiz links to the lobby");
ok(assignmentHref("/b", a({ id: "x" })) === "/b/assignments/x", "text links to the submit page");

const rows = sortForStudent([
  a({ id: "late", due_at: "2026-11-02T00:00:00Z" }),
  a({ id: "none" }),
  a({ id: "soon", due_at: "2026-10-28T00:00:00Z" }),
]);
ok(rows.map((r) => r.id).join(",") === "soon,late,none", "sorted by due date, no date last");
const views = rows.map((r) => ({ a: r, v: studentAssignmentView(r, NOW) }));
ok(primaryAssignmentId(views) === "soon", "primary = nearest due");
const withRun = [...views, { a: a({ id: "run", kind: "quiz", status: "in_progress" }), v: studentAssignmentView(a({ id: "run", kind: "quiz", status: "in_progress" }), NOW) }];
ok(primaryAssignmentId(withRun) === "run", "a running quiz wins");

if (failed) { console.error(`${failed} failed`); process.exit(1); }
console.log("all student assignment checks passed");
