// Phase 10 S4 (PHASE_10_DESIGN 4): my progress, mistakes notebook and goal.
import { lmsFetch } from "./client";
import type { ReviewItemOut } from "./attemptTypes";
import type { LocalizedText } from "./types";

export interface TrendPoint { attempt_id: string; at: string | null; title: LocalizedText | null; percent: number; practice: boolean }
export interface SectionStat { section: string; correct: number; total: number; accuracy: number }
export interface TopicStat { topic: string; section: string | null; correct: number; total: number; accuracy: number }
export interface ProgressOut {
  goal_percent: number | null;
  current_percent: number | null;
  attempts_total: number;
  assessments_done: number;
  open_mistakes: number;
  trend: TrendPoint[];
  by_section: SectionStat[];
  by_topic: TopicStat[];
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

export const getProgress = (courseId: string, opts: { signal?: AbortSignal } = {}) =>
  lmsFetch<ProgressOut>(`${base(courseId)}/progress`, { signal: opts.signal });
export const listMistakes = (courseId: string, status: MistakeStatus, cursor?: string | null, signal?: AbortSignal) =>
  lmsFetch<MistakePage>(`${base(courseId)}/mistakes`, { params: { status, cursor, limit: 25 }, signal });
export const putGoal = (courseId: string, percent: number) =>
  lmsFetch<{ goal_percent: number }>(`${base(courseId)}/goal`, { method: "PUT", body: { percent } });
export const deleteGoal = (courseId: string) => lmsFetch<void>(`${base(courseId)}/goal`, { method: "DELETE" });
