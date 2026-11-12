"use client";

import type { PrivacyState } from "@/components/privacy/privacyApi";
import type { MyAccessOut } from "./access";
import { lmsFetch } from "./client";
import type { LessonCourseOut } from "./courses";
import type { ExamPrepOut } from "./examPrep";
import type { HomeCourseOut, HomeOut } from "./homeTypes";
import type { ActivityOut } from "./progress";
import { cached, markStale, peek, revalidate, type SwrOptions } from "./swr";
import type { MeOut } from "./types";

/*
 * PERFORMANCE_AUDIT §5.2 (slice S2): `GET /me/bootstrap`, what the app shell needs on load in one request. Each part is
 * the answer of the route the shell called before (`/me/lms`, `/me/home/courses?limit=50`, `/me/access`, the count of
 * `/me/invitations`, `/me/privacy` without `requests`, `/courses/{exam}/lesson-courses`), so the shapes stay the same.
 * Cached through `swr` (60 s, this tab's sessionStorage, per token); a join or leave asks it again (`meStale` ->
 * `reloadBootstrap`).
 *
 * PERFORMANCE_AUDIT P2 (fix round 2026-11-12): on the student home, the first bootstrap request of a page load asks
 * `?include=home` as well: `/me/home` and the home exam course's exam-prep page and 7-day activity come in the same
 * answer, so a cold home is one request. Those parts go to the home's own cache entries (`pageData.ts` takes them
 * through `onBootstrapHome`), never into the cached bootstrap, whose shape stays the same for every other reader.
 */

export interface BootstrapStudentOut {
  /** Every student course of the caller (the home's cards; the shell keeps the exam-prep ones). */
  courses: HomeCourseOut[];
  /** Null without an exam-prep course, or in Student view. */
  access: MyAccessOut | null;
  /** Exam course id -> its lesson courses, for every exam-prep course of `courses`. */
  lesson_courses: Record<string, LessonCourseOut[]>;
}

export interface BootstrapOut {
  me: MeOut;
  pending_invitations: number;
  /** Null in Student view. */
  privacy: Omit<PrivacyState, "requests"> | null;
  /** Null for a person who teaches and learns nowhere. */
  student: BootstrapStudentOut | null;
}

export const BOOTSTRAP_KEY = "bootstrap";
export const BOOTSTRAP_OPTIONS: SwrOptions = { ttl: 60_000, storage: "session" };

/** P2: the home's own reads, as `?include=home` adds them (only for a person the student shell is for). */
export interface BootstrapHomeParts {
  home: HomeOut;
  /** Exam course id -> `GET /courses/{id}/exam-prep` (the home's exam course; empty without one). */
  exam_prep: Record<string, ExamPrepOut>;
  /** Step 3a S1: `{all: the 7-day activity over all the student's courses}` (was the exam course's). */
  activity: Record<string, ActivityOut>;
}

type BootstrapWithHome = BootstrapOut & {
  home?: HomeOut | null;
  exam_prep?: Record<string, ExamPrepOut> | null;
  activity?: Record<string, ActivityOut> | null;
};

let homeSink: ((parts: BootstrapHomeParts) => void) | null = null;
// P3: parts that came before `pageData.ts` was loaded (a sign-in prefetch answered on the login page); kept for the
// home of the same session for a few seconds only
let homePending: { parts: BootstrapHomeParts; at: number; token: string } | null = null;
const PENDING_MS = 10_000;

function tokenNow(): string {
  try { return window.localStorage.getItem("ort_token") ?? ""; } catch { return ""; }
}

/** `pageData.ts` receives the home's parts here (set once, when it loads). */
export function onBootstrapHome(sink: (parts: BootstrapHomeParts) => void): void {
  homeSink = sink;
  const pending = homePending;
  homePending = null;
  if (pending && Date.now() - pending.at <= PENDING_MS && pending.token === tokenNow()) sink(pending.parts);
}

function deliverHome(parts: BootstrapHomeParts): void {
  if (homeSink) homeSink(parts);
  else homePending = { parts, at: Date.now(), token: tokenNow() };
}

// one combined request per page load, the first on the home (a client navigation back to the home asks its own reads)
let homeAsked = false;
let homeRequest: Promise<BootstrapOut> | null = null;
// the exam course this device remembers (`useStudentShellData`'s CURRENT_KEY): the server takes it when it is one of
// the student's exam courses, else the first, as the shell does
const CURRENT_COURSE_KEY = "ort_student_course";

function onHome(): boolean {
  if (typeof window === "undefined") return false;
  return /^\/(en|ky|ru)\/courses\/?$/.test(window.location.pathname);
}

function rememberedCourse(): string | undefined {
  try { return window.localStorage.getItem(CURRENT_COURSE_KEY) ?? undefined; } catch { return undefined; }
}

function fetchBoot(withHome: boolean): Promise<BootstrapOut> {
  if (!withHome) return lmsFetch<BootstrapOut>("/me/bootstrap");
  homeAsked = true;
  const p = lmsFetch<BootstrapWithHome>("/me/bootstrap", { params: { include: "home", course: rememberedCourse() } }).then((b) => {
    const { home, exam_prep, activity, ...shell } = b;
    if (home) deliverHome({ home, exam_prep: exam_prep ?? {}, activity: activity ?? {} });
    return shell;
  });
  homeRequest = p;
  const done = () => { if (homeRequest === p) homeRequest = null; };
  p.then(done, done);
  return p;
}

/** The shell's fetcher: on the home, the first request of this page load carries the home's reads too. */
export const fetchBootstrap = () => fetchBoot(!homeAsked && onHome());

/**
 * P2: a running bootstrap that carries the home's reads, so the home waits for it instead of asking them alone; on the
 * home, when this page load has not asked one yet, it asks it now (shared with the shell's request of the same key).
 * Null when there is none to wait for.
 */
export function homeBootstrap(): Promise<BootstrapOut> | null {
  if (homeRequest) return homeRequest;
  if (homeAsked || !onHome()) return null;
  const p = revalidate(BOOTSTRAP_KEY, () => fetchBoot(true), BOOTSTRAP_OPTIONS);
  homeAsked = true; // a request without the home's reads was already running: the home asks its own after it
  return homeRequest ?? p;
}

/**
 * PERFORMANCE_AUDIT P3: sign-in has just stored the token (password, the two-step code, Google): ask the bootstrap now,
 * before the route change to `dest`, so the first page finds it running or cached (`swr` shares one request per key;
 * the page's own `useCached` waits for this one). Only for the app's pages under `/courses`; with the home's reads
 * when `dest` is the home, unless the login answer says the person runs the platform (the server leaves the student
 * parts out for anyone who teaches and answers only `me` under the two-step gate, whatever is asked).
 */
export function prefetchBootstrap(dest: string, isPlatformAdmin: boolean): void {
  if (typeof window === "undefined") return;
  let path: string;
  try { path = new URL(dest, window.location.origin).pathname; } catch { return; }
  if (!/^\/(en|ky|ru)\/courses(\/|$)/.test(path)) return;
  const home = /^\/(en|ky|ru)\/courses\/?$/.test(path);
  revalidate(BOOTSTRAP_KEY, () => fetchBoot(home && !isPlatformAdmin), BOOTSTRAP_OPTIONS).catch(() => undefined);
  if (home) homeAsked = true; // this page load's request for the home is the one above
}

/** The bootstrap: cached at once when fresh, the cached one plus a background refresh when stale. */
export const getBootstrap = () => cached(BOOTSTRAP_KEY, fetchBootstrap, BOOTSTRAP_OPTIONS);

/**
 * After a join, leave or other change of the shell's data: the cached answer stays on screen (the frame does not blank),
 * a request asked before the change is dropped, and the server is asked again now.
 */
export function reloadBootstrap(): Promise<BootstrapOut> {
  markStale(BOOTSTRAP_KEY);
  // P2: never with the home's reads: the home reads itself again on the same signal (`StudentHome`)
  return revalidate(BOOTSTRAP_KEY, () => fetchBoot(false), BOOTSTRAP_OPTIONS);
}

/** The cached bootstrap (fresh or stale), read synchronously; null when none. */
export const peekBootstrap = (): BootstrapOut | null => peek<BootstrapOut>(BOOTSTRAP_KEY)?.value ?? null;
