/**
 * Phase 7a S5: one view model for a student's assignment card (list, course home): window state, the next action
 * and which card gets the page's one primary button. Pure (no React).
 */
import type { AssignmentStudentOut } from "../../../lib/lms/assignmentTypes";

export type StudentAction = "continue" | "start" | "hand_in" | "open" | "none";

export interface StudentAssignmentView {
  opensLater: boolean;
  windowClosed: boolean;
  /** quiz with no attempts left */
  noAttemptsLeft: boolean;
  action: StudentAction;
  /** due date or, without one, the end of the window */
  deadline: string | null;
}

const ts = (v: string | null | undefined) => {
  if (!v) return null;
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(v) ? v : `${v}Z`;
  const n = Date.parse(s);
  return Number.isFinite(n) ? n : null;
};

export function studentAssignmentView(a: AssignmentStudentOut, now: number = Date.now(), readOnly = false): StudentAssignmentView {
  const from = ts(a.available_from);
  const until = ts(a.available_until);
  const opensLater = from !== null && from > now;
  const windowClosed = until !== null && until <= now;
  const open = !opensLater && !windowClosed;
  const status = a.status ?? "not_started";
  const noAttemptsLeft = a.kind === "quiz" && a.attempts_left === 0 && status !== "in_progress";
  let action: StudentAction = "open";
  if (readOnly) action = "open";
  else if (a.kind === "quiz") {
    if (status === "in_progress") action = "continue";
    else if (open && !noAttemptsLeft && status !== "excused") action = "start";
  } else if (a.kind === "text" || a.kind === "file") {
    if (open && (status === "not_started" || status === "missing")) action = "hand_in";
  }
  return { opensLater, windowClosed, noAttemptsLeft, action, deadline: a.due_at ?? a.available_until ?? null };
}

/** Effective due date first (no date last), then the course order, then id. */
export function sortForStudent(rows: AssignmentStudentOut[]): AssignmentStudentOut[] {
  return [...rows].sort((x, y) => {
    const a = ts(x.due_at) ?? Number.POSITIVE_INFINITY;
    const b = ts(y.due_at) ?? Number.POSITIVE_INFINITY;
    if (a !== b) return a - b;
    const p = (x.position ?? 0) - (y.position ?? 0);
    return p !== 0 ? p : x.id.localeCompare(y.id);
  });
}

/** The one card with the primary button: a running quiz, else the first startable / to-hand-in card in due order. */
export function primaryAssignmentId(rows: { a: AssignmentStudentOut; v: StudentAssignmentView }[]): string | null {
  const running = rows.find((r) => r.v.action === "continue");
  if (running) return running.a.id;
  const next = rows.find((r) => r.v.action === "start" || r.v.action === "hand_in");
  return next ? next.a.id : null;
}

/** Where a card leads: the quiz lobby, else the assignment page. */
export function assignmentHref(base: string, a: Pick<AssignmentStudentOut, "id" | "kind" | "assessment_id">): string {
  return a.kind === "quiz" && a.assessment_id ? `${base}/assessments/${a.assessment_id}` : `${base}/assignments/${a.id}`;
}
