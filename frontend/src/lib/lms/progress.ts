// Phase 10 S4 (PHASE_10_DESIGN 4): my progress, mistakes notebook and goal.
import { lmsFetch } from "./client";
import type { ReviewItemOut } from "./attemptTypes";
import type { LocalizedText } from "./types";

export interface TrendPoint { attempt_id: string; at: string | null; title: LocalizedText | null; percent: number; practice: boolean }
/*
 * STUDENT_UI_FIX_PLAN 4.2/4.3: one definition for every number. `total` = answers (answered items of submitted,
 * visible attempts; blanks never count), `graded` = answers not awaiting manual grading, `correct` = correct + 0.5 x
 * partial, `accuracy` = correct / graded. `rated` (server rule): topic from 5 graded answers, section from 10.
 */
export interface SectionStat { section: string | null; correct: number; total: number; graded: number; accuracy: number; rated: boolean }
/** `topic` null: the section's answers without a topic (kept so the sums match; not shown as a topic). */
export interface TopicStat { topic: string | null; section: string | null; correct: number; total: number; graded: number; accuracy: number; rated: boolean }
export interface ProgressOut {
  days_window: ActivityDays | null; // null: all time
  goal_percent: number | null;
  current_percent: number | null;
  attempts_total: number;
  assessments_done: number;
  open_mistakes: number;
  trend: TrendPoint[];
  by_section: SectionStat[];
  by_topic: TopicStat[];
  weak_topics_ready: boolean; // >= 3 rated topics
}
export interface MistakeOut {
  attempt_id: string;
  submitted_at: string | null;
  assessment_title: LocalizedText | null;
  topic: string | null;
  section: string | null;
  item: ReviewItemOut;
}
export interface MistakePage { items: MistakeOut[]; next_cursor: string | null }
export type MistakeStatus = "open" | "fixed";

const base = (courseId: string) => `/courses/${encodeURIComponent(courseId)}/my`;

/** `days`: the same window as `getActivity` (analytics page); absent: all time (home, goal). */
export const getProgress = (courseId: string, opts: { signal?: AbortSignal; days?: ActivityDays } = {}) =>
  lmsFetch<ProgressOut>(`${base(courseId)}/progress`, { params: { days: opts.days }, signal: opts.signal });
export const listMistakes = (courseId: string, status: MistakeStatus, cursor?: string | null, signal?: AbortSignal) =>
  lmsFetch<MistakePage>(`${base(courseId)}/mistakes`, { params: { status, cursor, limit: 25 }, signal });

// Student UI U5 (STUDENT_UI_DESIGN 4.2, 4.3): activity and saved (flagged) questions.
export type ActivityDays = 7 | 30 | 90 | 365;
export interface ActivityDay {
  date: string; // YYYY-MM-DD, Asia/Bishkek
  answered: number;
  correct: number;
  wrong: number;
  study_seconds: number;
  by_section: Record<string, number>; // section key -> seconds
}
export interface ActivitySession { started_at: string; ended_at: string; answered: number; correct: number }
export interface ActivityOut {
  days_window: ActivityDays;
  streak_current: number;
  streak_longest: number;
  totals: { answered: number; correct: number; graded: number; accuracy: number }; // same definition as SectionStat
  days: ActivityDay[];
  by_hour: number[]; // 24 answer counts by Bishkek hour
  sessions: ActivitySession[]; // last 7 days, newest first, at most 50
  heatmap: { date: string; answered: number }[]; // all time, at most 366 active days, oldest first
}
export interface SavedOut extends Omit<MistakeOut, "item"> {
  position: number;
  item: ReviewItemOut | null; // null (metadata only) when the results are not visible
  released: boolean;
}
export interface SavedPage { items: SavedOut[]; next_cursor: string | null }

export const getActivity = (courseId: string, days: ActivityDays = 30, signal?: AbortSignal) =>
  lmsFetch<ActivityOut>(`${base(courseId)}/activity`, { params: { days }, signal });
export const listSaved = (courseId: string, cursor?: string | null, signal?: AbortSignal, limit = 25) =>
  lmsFetch<SavedPage>(`${base(courseId)}/saved`, { params: { cursor, limit }, signal });
export const putGoal =(courseId: string, percent: number) =>
  lmsFetch<{ goal_percent: number }>(`${base(courseId)}/goal`, { method: "PUT", body: { percent } });
export const deleteGoal = (courseId: string) => lmsFetch<void>(`${base(courseId)}/goal`, { method: "DELETE" });
