// Phase 10 S5: quiz statistics API client (PHASE_10_DESIGN 5).
import { lmsFetch } from "./client";
import type { PageOut } from "./types";

export type StatsState = "fresh" | "stale" | "computing" | "empty";

export interface StatsVersion { version_id: string; version_no: number | null; attempts: number }

export interface QuizStats {
  assessment_id: string;
  version_id: string | null;
  version_no: number | null;
  versions: StatsVersion[];
  state: StatsState;
  computed_at: string | null;
  attempts_counted: number;
  mean_percent: number | null;
  median_percent: number | null;
  stddev_percent: number | null;
  min_percent: number | null;
  max_percent: number | null;
  /** Ten buckets of 10 points each; 100 % is in the last one. */
  distribution: number[];
}

export interface OptionStat { key: string; label: string; count: number; is_correct: boolean }

export interface QuizItemStat {
  id: string;
  slot: number;
  question_version_id: string;
  type: string;
  stem_excerpt: string;
  section: string | null;
  topic: string | null;
  n: number;
  points: number;
  accuracy: number;
  point_biserial: number | null;
  avg_seconds: number | null;
  correct: number;
  partial: number;
  incorrect: number;
  unanswered: number;
  options: OptionStat[] | null;
}

export type ItemSort = "hardest" | "slot";

const e = encodeURIComponent;
const base = (c: string, a: string) => `/courses/${e(c)}/assessments/${e(a)}/statistics`;

export const getQuizStats = (courseId: string, assessmentId: string, versionId?: string | null) =>
  lmsFetch<QuizStats>(base(courseId, assessmentId), { params: { version_id: versionId ?? undefined } });

export const listQuizItemStats = (
  courseId: string, assessmentId: string,
  q: { versionId?: string | null; sort?: ItemSort; cursor?: string | null; limit?: number } = {},
) =>
  lmsFetch<PageOut<QuizItemStat>>(`${base(courseId, assessmentId)}/items`, {
    params: { version_id: q.versionId ?? undefined, sort: q.sort, cursor: q.cursor, limit: q.limit },
  });
