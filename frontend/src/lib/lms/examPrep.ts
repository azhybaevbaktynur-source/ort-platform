// Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): the exam-prep page of a student, the test library and the target score.
import { lmsFetch } from "./client";
import type { LocalizedText, PageOut } from "./types";

/** Decimals come as strings from the server. */
export type Num = string | number;

export interface ExamGoalOut { target_score: number | null; scale_min: Num | null; scale_max: Num | null }
export interface ScorePoint { attempt_id: string; assessment_id: string; title: LocalizedText; at: string | null; value: Num | null }
export interface SectionBar { key: string; raw: Num; possible: Num; correct: number }
export type NextKind = "resume" | "start" | "practice" | "retake";
export interface ExamNextOut {
  kind: NextKind;
  assessment_id: string | null;
  attempt_id: string | null;
  title: LocalizedText | null;
  section: string | null;
  last_at: string | null;
}
export interface ExamSourceOut { module_id: string | null; title: LocalizedText | null; count: number }
export interface ExamPrepOut {
  exam_date: string | null;
  goal: ExamGoalOut;
  latest: ScorePoint | null;
  history: ScorePoint[];
  sections: SectionBar[];
  next: ExamNextOut | null;
  sources: ExamSourceOut[];
  library_total: number;
}
export type LibraryStatus = "not_started" | "in_progress" | "done";
export interface LibraryCardOut {
  id: string;
  title: LocalizedText;
  item_count: number;
  time_limit_s: number | null;
  status: LibraryStatus;
  attempt_id: string | null;
  attempts_used: number;
  best_value: Num | null;
  best_percent: number | null;
  scale_max: Num | null;
  /** Reserved for paid tests (S3); always false now. */
  locked: boolean;
}

/** Library filter: all tests, one module's, or those in no module. */
export const SOURCE_OTHER = "other";

const base = (courseId: string) => `/courses/${encodeURIComponent(courseId)}/exam-prep`;

export const getExamPrep = (courseId: string, signal?: AbortSignal) => lmsFetch<ExamPrepOut>(base(courseId), { signal });
export const listExamLibrary = (courseId: string, opts: { source?: string | null; cursor?: string | null; limit?: number; signal?: AbortSignal } = {}) =>
  lmsFetch<PageOut<LibraryCardOut>>(`${base(courseId)}/library`, {
    params: { source: opts.source || undefined, cursor: opts.cursor || undefined, limit: opts.limit ?? 12 }, signal: opts.signal,
  });
export const putExamGoal = (courseId: string, targetScore: number) =>
  lmsFetch<ExamGoalOut>(`${base(courseId)}/goal`, { method: "PUT", body: { target_score: targetScore } });
export const deleteExamGoal = (courseId: string) => lmsFetch<void>(`${base(courseId)}/goal`, { method: "DELETE" });

/** A decimal from the server as a whole number for display ("172"), or null. */
export function wholeNumber(v: Num | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : null;
}

/** Whole days from today (the viewer's calendar) to an ISO date; negative once it has passed. */
export function daysUntil(isoDate: string, today: Date = new Date()): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const target = Date.UTC(y, (m || 1) - 1, d || 1);
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - now) / 86_400_000);
}
