// Phase 10 S3 (PHASE_10_DESIGN 3): practice sets and per-item check API.
import { lmsFetch } from "./client";
import type { PracticeFeedback } from "./attemptTypes";
import type { PageOut, LocalizedText, Lang } from "./types";

const e = encodeURIComponent;
const base = (c: string) => `/courses/${e(c)}/practice`;

export type PracticeDifficulty = "easy" | "medium" | "hard";
export interface PracticeBlock {
  bank_id: string;
  count: number;
  section?: string | null;
  topic?: string | null;
  difficulty?: PracticeDifficulty | null;
}
export interface PracticeSetOut {
  id: string;
  title: LocalizedText;
  status: string;
  languages: Lang[];
  item_count: number;
  blocks: PracticeBlock[];
  my_attempts: number | null;
  my_best_percent: number | null;
  my_last_at: string | null;
  open_attempt_id: string | null;
}
export interface PracticeCreateIn { title: LocalizedText; languages: Lang[]; blocks: PracticeBlock[] }
export interface PracticeUpdateIn { title?: LocalizedText; blocks?: PracticeBlock[] }
export interface PracticeFacets { sections: string[]; topics: string[]; difficulties: string[] }

export const listPractice = (courseId: string, q: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<PracticeSetOut>>(base(courseId), { params: { cursor: q.cursor, limit: q.limit } });
export const createPractice = (courseId: string, body: PracticeCreateIn) =>
  lmsFetch<PracticeSetOut>(base(courseId), { method: "POST", body });
/** Empty body refreshes the pool from the bank. */
export const updatePractice = (courseId: string, id: string, body: PracticeUpdateIn = {}) =>
  lmsFetch<PracticeSetOut>(`${base(courseId)}/${e(id)}`, { method: "PATCH", body });
export const deletePractice = (courseId: string, id: string) =>
  lmsFetch<void>(`${base(courseId)}/${e(id)}`, { method: "DELETE" });
export const practiceFacets = (courseId: string, bankId: string) =>
  lmsFetch<PracticeFacets>(`${base(courseId)}/facets`, { params: { bank_id: bankId } });

export const checkPracticeItem = (attemptId: string, position: number) =>
  lmsFetch<PracticeFeedback>(`/attempts/${e(attemptId)}/items/${position}/check`, { method: "POST" });
export const getPracticeFeedback = (attemptId: string) =>
  lmsFetch<{ items: PracticeFeedback[] }>(`/attempts/${e(attemptId)}/practice-feedback`);
