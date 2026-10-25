/**
 * Phase 6b S6b: one status model for a student's assessment row (UX S1, S6). Used by the student course home
 * and the student assessment list so both say the same thing.
 */
import type { AssessmentStudentSummaryOut } from "@/lib/lms/assessmentTypes";
import type { MyGradeOut } from "@/lib/lms/gradingTypes";
import { parseApiDate } from "@/lib/format";

export type StudentAssessmentStatus = "not_started" | "in_progress" | "submitted" | "graded" | "closed";

export interface StudentAssessmentView {
  status: StudentAssessmentStatus;
  /** null = unlimited attempts */
  attemptsLeft: number | null;
  noAttemptsLeft: boolean;
  /** opens later (available_from in the future) */
  opensLater: boolean;
  /** the window is closed (available_until passed) */
  windowClosed: boolean;
  /** can start a new attempt now (as far as the list knows; the lobby stays authoritative) */
  canStart: boolean;
  /** kept attempt with a released result (link to the result page) */
  resultAttemptId: string | null;
  grade: MyGradeOut | null;
  /** due date or, without one, the end of the window */
  deadline: string | null;
}

export function studentAssessmentView(a: AssessmentStudentSummaryOut, grade: MyGradeOut | null | undefined, now: number = Date.now()): StudentAssessmentView {
  const from = parseApiDate(a.available_from);
  const until = parseApiDate(a.available_until);
  const opensLater = !!from && from.getTime() > now;
  const windowClosed = !!until && until.getTime() <= now;
  const attemptsLeft = a.allowed_attempts === -1 ? null : Math.max(0, a.allowed_attempts - a.attempts_used);
  const inProgress = !!a.in_progress_attempt_id;
  const noAttemptsLeft = attemptsLeft === 0 && !inProgress;
  const graded = grade?.state === "graded" || !!a.last_result;
  let status: StudentAssessmentStatus;
  if (inProgress) status = "in_progress";
  else if (graded) status = "graded";
  else if (a.attempts_used > 0) status = "submitted";
  else if (windowClosed) status = "closed";
  else status = "not_started";
  const g = grade ?? null;
  return {
    status,
    attemptsLeft,
    noAttemptsLeft,
    opensLater,
    windowClosed,
    canStart: !inProgress && !noAttemptsLeft && !opensLater && !windowClosed,
    resultAttemptId: g && g.state === "graded" && g.kept_attempt_id ? g.kept_attempt_id : null,
    grade: g,
    deadline: a.due_at ?? a.available_until ?? null,
  };
}

/**
 * The one row that gets the primary button: the first in-progress attempt, else the open, not yet started
 * assessment with the nearest deadline (no deadline last, then list order).
 */
export function primaryAssessmentId(rows: { a: AssessmentStudentSummaryOut; v: StudentAssessmentView }[]): string | null {
  const running = rows.find((r) => r.v.status === "in_progress");
  if (running) return running.a.id;
  const open = rows.filter((r) => r.v.status === "not_started" && r.v.canStart);
  if (open.length === 0) return null;
  const key = (r: { v: StudentAssessmentView }) => parseApiDate(r.v.deadline)?.getTime() ?? Number.POSITIVE_INFINITY;
  return open.reduce((best, r) => (key(r) < key(best) ? r : best)).a.id;
}
