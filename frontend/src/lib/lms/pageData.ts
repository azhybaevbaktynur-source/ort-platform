"use client";

import { useEffect } from "react";
import { getExamPrep, type ExamPrepOut } from "./examPrep";
import { getActivity, getProgress, type ActivityDays, type ActivityOut, type ProgressOut } from "./progress";
import { listMyCourses } from "./courses";
import { homeBootstrap, onBootstrapHome } from "./bootstrap"; // PERFORMANCE_AUDIT P2
import { getHome } from "./home";
import { getModules } from "./modules"; // step 3a S2
import { isStaffModules, type ModulesStudentOut } from "./modulesTypes";
import type { HomeOut } from "./homeTypes";
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

/*
 * PERFORMANCE_AUDIT P2: the home's reads (`/me/home`, the exam course's exam-prep page and 7-day activity) can come
 * inside the shell's bootstrap (`bootstrap.ts`, `?include=home`). They land here like a prefetch that just answered, so
 * the page that draws them takes them once without asking; while that bootstrap is running, the home's reads wait for it
 * (`viaBootstrap`) instead of asking alone, and ask alone only when it did not carry them.
 */
const HOME_KEY = "home";
const HOME_CACHE: SwrOptions = { ttl: 15_000 };
const HOME_ACTIVITY_DAYS: ActivityDays = 7;
const HOME_ACTIVITY_KEY = "home:activity";

onBootstrapHome((parts) => {
  const at = Date.now();
  const land = <T,>(key: string, value: T, opts: SwrOptions) => { prefetched.set(key, at); put(key, value, opts); };
  land(HOME_KEY, parts.home, HOME_CACHE);
  for (const [id, prep] of Object.entries(parts.exam_prep)) land(examPrepKey(id), prep, EXAM_PREP_CACHE);
  // step 3a S1: the bootstrap's activity is `{all: …}` (every course of the student), the home streak strip's own key
  for (const [id, a] of Object.entries(parts.activity)) land(id === "all" ? HOME_ACTIVITY_KEY : activityKey(id, HOME_ACTIVITY_DAYS), a, ANALYTICS_CACHE);
});

/** `fetcher`, unless a running bootstrap brings this key's answer (then that answer, used up). */
function viaBootstrap<T>(key: string, fetcher: () => Promise<T>): () => Promise<T> {
  return async () => {
    const boot = homeBootstrap();
    if (boot) {
      await boot.catch(() => undefined); // the shell shows a failed bootstrap; the page then asks its own
      const at = prefetched.get(key);
      const e = peek<T>(key);
      if (at !== undefined && e && e.at >= at) {
        prefetched.delete(key);
        return e.value;
      }
    }
    return fetcher();
  };
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
const fetchExamPrep = (courseId: string) => viaBootstrap(examPrepKey(courseId), () => getExamPrep(courseId)); // P2

/** The exam-prep page for a reader that does not draw it (the checklist): a fresh cached answer, else one request. */
export function loadExamPrep(courseId: string): Promise<ExamPrepOut> {
  const key = examPrepKey(courseId);
  const e = peek<ExamPrepOut>(key);
  if (e && Date.now() - e.at <= EXAM_PREP_CACHE.ttl!) return Promise.resolve(e.value);
  return revalidate(key, fetchExamPrep(courseId), EXAM_PREP_CACHE);
}

/** The exam-prep page of a page that draws it: the cached answer at once, asked again on mount (one request at most). */
export function useExamPrep(courseId: string | null) {
  // step 3a S2: a null id (a course that is not an exam course) reads nothing and keeps the hook order
  const key = courseId ? examPrepKey(courseId) : null;
  const state = useCached<ExamPrepOut>(key, fetchExamPrep(courseId ?? ""), EXAM_PREP_CACHE);
  useEffect(() => {
    if (!key || !courseId) return;
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

/** P2: the home's `/me/home` (asked on every mount, as before; from the bootstrap when it brought it). */
export function loadHome(): Promise<HomeOut> {
  return pageLoad(HOME_KEY, viaBootstrap(HOME_KEY, () => getHome()), HOME_CACHE);
}

/**
 * Step 3a S3 (OPEN Q2): the hub's «Серия N дней» reads the bootstrap's cross-course activity only (there is no other
 * cross-course read): call after `loadHome()` answered (the bootstrap that carried the home landed it by then). Any
 * age is fine (a quiet line); null when this tab never had it.
 */
export function peekHomeActivity(): ActivityOut | null {
  return peek<ActivityOut>(HOME_ACTIVITY_KEY)?.value ?? null;
}

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

/* Step 3a S2 (STUDENT_IA_DESIGN §6.4): the student's modules of a course (Обзор: next lesson, header progress; the
 * Уроки tab link prefetches it). Asked again on every mount, like the exam-prep page. A staff answer reads as empty. */
const MODULES_CACHE: SwrOptions = { ttl: 15_000 };
export const modulesKey = (courseId: string) => `modules:student:${courseId}`;
const fetchModules = (courseId: string) => async (): Promise<ModulesStudentOut> => {
  const out = await getModules(courseId);
  return isStaffModules(out) ? { modules: [], up_next: null } : { modules: out.modules ?? [], up_next: out.up_next ?? null, progress: out.progress };
};

/** The student modules of a page that draws them (`enabled` false: no read, `data` stays null). */
export function useStudentModules(courseId: string, enabled = true) {
  const key = enabled ? modulesKey(courseId) : null;
  const state = useCached<ModulesStudentOut>(key, fetchModules(courseId), MODULES_CACHE);
  useEffect(() => {
    if (!key) return;
    pageLoad(key, fetchModules(courseId), MODULES_CACHE).catch(() => { /* `useCached` reports a missing answer */ });
  }, [key, courseId]);
  return state;
}
/** A fresh modules answer from another reader (the Уроки tab after a fact): every reader sees it. */
export function putStudentModules(courseId: string, data: ModulesStudentOut): void {
  put(modulesKey(courseId), data, MODULES_CACHE);
}
export function prefetchModules(courseId: string): void {
  intentLoad(modulesKey(courseId), fetchModules(courseId), MODULES_CACHE);
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
