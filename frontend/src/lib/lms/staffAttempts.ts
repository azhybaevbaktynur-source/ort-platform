/** Staff attempt API (docs/phases/PHASE_3_DESIGN.md section 5, staff table). snake_case as on the wire. */
import { lmsFetch } from "./client";
import type { Lang, PageOut } from "./types";
import type { AttemptResultOut, AttemptStatus, ReviewItemOut, SubmitReason } from "./attemptTypes";

const e = encodeURIComponent;

export interface AttemptStaffSummaryOut {
  id: string;
  user_id: string;
  student_name: string | null;
  attempt_no: number | null;
  status: AttemptStatus;
  language: Lang;
  started_at: string;
  submitted_at: string | null;
  submit_reason: SubmitReason | null;
  raw_score: number | string | null;
  points_possible: number | string | null;
  pending_review: number;
  is_preview: boolean;
}

/** One reviewed item for staff: the student review item plus scoring fields. */
export interface StaffReviewItem extends ReviewItemOut {
  auto_score?: number | string | null;
  manual_score?: number | string | null;
  graded_by_id?: string | null;
  graded_by_name?: string | null;
  graded_at?: string | null;
}

export interface AttemptStaffOut extends AttemptStaffSummaryOut {
  assessment_id?: string;
  result?: AttemptResultOut | null;
  items: StaffReviewItem[];
}

export interface ScoreIn {
  points: number;
  feedback?: string | null;
}

export type StaffAttemptFilter = { status?: AttemptStatus | ""; preview?: boolean; cursor?: string | null; limit?: number };

export const listStaffAttempts = (courseId: string, assessmentId: string, f: StaffAttemptFilter = {}) =>
  lmsFetch<PageOut<AttemptStaffSummaryOut>>(`/courses/${e(courseId)}/assessments/${e(assessmentId)}/attempts`, {
    params: { status: f.status || undefined, preview: f.preview ? true : false, cursor: f.cursor, limit: f.limit },
  });
export const getStaffAttempt = (courseId: string, attemptId: string) =>
  lmsFetch<AttemptStaffOut>(`/courses/${e(courseId)}/attempts/${e(attemptId)}`);
export const scoreAttemptItem = (courseId: string, attemptId: string, position: number, body: ScoreIn) =>
  lmsFetch<AttemptStaffOut>(`/courses/${e(courseId)}/attempts/${e(attemptId)}/items/${position}/score`, { method: "PUT", body });
/** Phase 4 (P4-20): void a graded or needs-review attempt; the kept result is recomputed server-side. Reason <= 500. */
export const voidAttempt = (courseId: string, attemptId: string, reason: string) =>
  lmsFetch<AttemptStaffOut>(`/courses/${e(courseId)}/attempts/${e(attemptId)}/void`, { method: "POST", body: { reason } });
