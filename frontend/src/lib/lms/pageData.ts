"use client";

import { useEffect } from "react";
import { getExamPrep, type ExamPrepOut } from "./examPrep";
import { getActivity, getProgress, type ActivityDays, type ActivityOut, type ProgressOut } from "./progress";
import { invalidate, peek, put, revalidate, useCached, type SwrOptions } from "./swr";

/*
 * PERFORMANCE_AUDIT §5.2 (slice S3): the student pages' own reads through the SWR cache (`swr.ts`), so that two
 * components asking the same answer send one request (the Тесты page and the "Начало работы" checklist both read the
 * exam-prep page), and a hover or focus on a shell link can ask a page's data before the click.
 *
 * Exam-prep (ttl 30 s, this tab's sessionStorage): shown at once from the cache, asked again whenever a page mounts
 * unless it was answered moments ago (a hover prefetch), because a finished attempt changes it.
 * Analytics (memory, 15 s): only a prefetch hand-off; the page uses an answer younger than that or asks again.
 */

export const EXAM_PREP_CACHE: SwrOptions = { ttl: 30_000, storage: "session" };
/** An answer this young is used without asking again (it was asked by a hover/focus prefetch just before the click). */
const RECENT_MS = 10_000;
const INTENT_CACHE: SwrOptions = { ttl: 15_000 };

export const examPrepKey = (courseId: string) => `exam-prep:${courseId}`;
const fetchExamPrep = (courseId: string) => () => getExamPrep(courseId);

function young(key: string, ms: number): boolean {
  const e = peek(key);
  return !!e && Date.now() - e.at <= ms;
}

/** The stored answer when younger than `ms`, else a request (shared with one already running for `key`). */
function recentOrLoad<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions, ms: number): Promise<T> {
  const e = peek<T>(key);
  if (e && Date.now() - e.at <= ms) return Promise.resolve(e.value);
  return revalidate(key, fetcher, opts);
}

/** The exam-prep page for a reader that does not draw it (the checklist): a fresh cached answer, else one request. */
export function loadExamPrep(courseId: string): Promise<ExamPrepOut> {
  return recentOrLoad(examPrepKey(courseId), fetchExamPrep(courseId), EXAM_PREP_CACHE, EXAM_PREP_CACHE.ttl!);
}

/** The exam-prep page of a page that draws it: the cached answer at once, refreshed on mount (one request at most). */
export function useExamPrep(courseId: string) {
  const key = examPrepKey(courseId);
  const state = useCached<ExamPrepOut>(key, fetchExamPrep(courseId), EXAM_PREP_CACHE);
  useEffect(() => {
    if (!young(key, RECENT_MS)) revalidate(key, fetchExamPrep(courseId), EXAM_PREP_CACHE).catch(() => { /* `useCached` reports it */ });
  }, [key, courseId]);
  return state;
}

/** A local change of the exam-prep answer (the goal was saved): every reader sees it, no request. */
export function putExamPrep(courseId: string, prep: ExamPrepOut): void {
  put(examPrepKey(courseId), prep, EXAM_PREP_CACHE);
}

const progressKey = (courseId: string, days: ActivityDays) => `analytics:progress:${courseId}:${days}`;
const activityKey = (courseId: string, days: ActivityDays) => `analytics:activity:${courseId}:${days}`;

/** Аналитика's two reads: a just-prefetched answer, else a request (shared with a prefetch still running). */
export function loadAnalytics(courseId: string, days: ActivityDays): Promise<[ProgressOut, ActivityOut]> {
  return Promise.all([
    recentOrLoad(progressKey(courseId, days), () => getProgress(courseId, { days }), INTENT_CACHE, INTENT_CACHE.ttl!),
    recentOrLoad(activityKey(courseId, days), () => getActivity(courseId, days), INTENT_CACHE, INTENT_CACHE.ttl!),
  ]);
}

/** The analytics goal changed: no prefetched answer of this course is used any more. */
export function forgetAnalytics(courseId: string): void {
  invalidate(`analytics:progress:${courseId}:`);
}

/** Hover/focus on a shell link: the target page's cheap, side-effect-free reads, asked once. */
export function prefetchExamPrep(courseId: string): void {
  loadExamPrep(courseId).catch(() => { /* the page asks again */ });
}
export function prefetchAnalytics(courseId: string, days: ActivityDays = 30): void {
  loadAnalytics(courseId, days).catch(() => { /* the page asks again */ });
}
