"use client";

import { useEffect } from "react";
import { getExamPrep, type ExamPrepOut } from "./examPrep";
import { getActivity, getProgress, type ActivityDays, type ActivityOut, type ProgressOut } from "./progress";
import { listMyCourses } from "./courses";
import type { CourseCard, PageOut } from "./types";
import { peek, put, revalidate, useCached, type SwrOptions } from "./swr";

/*
 * PERFORMANCE_AUDIT §5.2 (slice S3): the student pages' own reads through the SWR cache (`swr.ts`), so that two
 * components asking the same answer send one request (the Тесты page and the "Начало работы" checklist both read the
 * exam-prep page), and a hover or focus on a shell link can ask a page's data before the click.
 *
 * A page that draws the answer asks it again on every mount (a finished attempt changes it), sharing a request still
 * running; the only answer it takes without asking is one a hover/focus prefetch asked for it moments ago (then the
 * prefetch is used up). Exam-prep is also kept in this tab's sessionStorage (ttl 30 s), so a repeat visit draws it at
 * once and refreshes it; analytics answers live in memory only.
 */

export const EXAM_PREP_CACHE: SwrOptions = { ttl: 30_000, storage: "session" };
const ANALYTICS_CACHE: SwrOptions = { ttl: 15_000 };
/** How long a hover/focus prefetch stands for the page it leads to (and the hover bursts it ignores meanwhile). */
const INTENT_MS = 10_000;

/** key -> when a hover/focus prefetch asked it (not yet used by its page) */
const prefetched = new Map<string, number>();

/** Hover/focus: ask `key` once per burst. */
function intentLoad<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions): void {
  const at = prefetched.get(key);
  if (at !== undefined && Date.now() - at <= INTENT_MS) return;
  prefetched.set(key, Date.now());
  revalidate(key, fetcher, opts).catch(() => { prefetched.delete(key); });
}

/** Page mount: the answer of a prefetch asked moments ago (or its running request), else a new request. */
function pageLoad<T>(key: string, fetcher: () => Promise<T>, opts: SwrOptions): Promise<T> {
  const at = prefetched.get(key);
  prefetched.delete(key);
  const e = peek<T>(key);
  if (at !== undefined && Date.now() - at <= INTENT_MS && e && e.at >= at) return Promise.resolve(e.value);
  return revalidate(key, fetcher, opts); // shared with a request of the same key still running
}

export const examPrepKey = (courseId: string) => `exam-prep:${courseId}`;
const fetchExamPrep = (courseId: string) => () => getExamPrep(courseId);

/** The exam-prep page for a reader that does not draw it (the checklist): a fresh cached answer, else one request. */
export function loadExamPrep(courseId: string): Promise<ExamPrepOut> {
  const key = examPrepKey(courseId);
  const e = peek<ExamPrepOut>(key);
  if (e && Date.now() - e.at <= EXAM_PREP_CACHE.ttl!) return Promise.resolve(e.value);
  return revalidate(key, fetchExamPrep(courseId), EXAM_PREP_CACHE);
}

/** The exam-prep page of a page that draws it: the cached answer at once, asked again on mount (one request at most). */
export function useExamPrep(courseId: string) {
  const key = examPrepKey(courseId);
  const state = useCached<ExamPrepOut>(key, fetchExamPrep(courseId), EXAM_PREP_CACHE);
  useEffect(() => {
    pageLoad(key, fetchExamPrep(courseId), EXAM_PREP_CACHE).catch(() => { /* `useCached` reports a missing answer */ });
  }, [key, courseId]);
  return state;
}

/** A local change of the exam-prep answer (the goal was saved): every reader sees it, no request. */
export function putExamPrep(courseId: string, prep: ExamPrepOut): void {
  put(examPrepKey(courseId), prep, EXAM_PREP_CACHE);
}

const progressKey = (courseId: string, days: ActivityDays) => `analytics:progress:${courseId}:${days}`;
const activityKey = (courseId: string, days: ActivityDays) => `analytics:activity:${courseId}:${days}`;

/** Аналитика's two reads (a prefetch asked moments ago stands for them). */
export function loadAnalytics(courseId: string, days: ActivityDays): Promise<[ProgressOut, ActivityOut]> {
  return Promise.all([
    pageLoad(progressKey(courseId, days), () => getProgress(courseId, { days }), ANALYTICS_CACHE),
    pageLoad(activityKey(courseId, days), () => getActivity(courseId, days), ANALYTICS_CACHE),
  ]);
}

/** Hover/focus on a shell link: the target page's cheap, side-effect-free reads, asked once. */
export function prefetchExamPrep(courseId: string): void {
  intentLoad(examPrepKey(courseId), fetchExamPrep(courseId), EXAM_PREP_CACHE);
}
export function prefetchAnalytics(courseId: string, days: ActivityDays = 30): void {
  intentLoad(progressKey(courseId, days), () => getProgress(courseId, { days }), ANALYTICS_CACHE);
  intentLoad(activityKey(courseId, days), () => getActivity(courseId, days), ANALYTICS_CACHE);
}

/* Integration fix (S3 follow-up): the header's teaching sections prefetch like the student sidebar. "Мои курсы" reads
 * the first page of `/courses?as=teaching` through here; the other sections' pages have no cached reader yet. */
const TEACHING_CACHE: SwrOptions = { ttl: 15_000 };
const TEACHING_KEY = "teaching-courses:first";
const fetchTeaching = () => listMyCourses("teaching");

/** The teaching list's first page (a prefetch asked moments ago stands for it). */
export function loadTeachingCourses(): Promise<PageOut<CourseCard>> {
  return pageLoad(TEACHING_KEY, fetchTeaching, TEACHING_CACHE);
}
export function prefetchTeachingCourses(): void {
  intentLoad(TEACHING_KEY, fetchTeaching, TEACHING_CACHE);
}
