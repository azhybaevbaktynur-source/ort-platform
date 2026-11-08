"use client";

import type { PrivacyState } from "@/components/privacy/privacyApi";
import type { MyAccessOut } from "./access";
import { lmsFetch } from "./client";
import type { LessonCourseOut } from "./courses";
import type { HomeCourseOut } from "./homeTypes";
import { cached, markStale, peek, revalidate, type SwrOptions } from "./swr";
import type { MeOut } from "./types";

/*
 * PERFORMANCE_AUDIT §5.2 (slice S2): `GET /me/bootstrap`, what the app shell needs on load in one request. Each part is
 * the answer of the route the shell called before (`/me/lms`, `/me/home/courses?limit=50`, `/me/access`, the count of
 * `/me/invitations`, `/me/privacy` without `requests`, `/courses/{exam}/lesson-courses`), so the shapes stay the same.
 * Cached through `swr` (60 s, this tab's sessionStorage, per token); a join or leave asks it again (`meStale` ->
 * `reloadBootstrap`).
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

export const fetchBootstrap = () => lmsFetch<BootstrapOut>("/me/bootstrap");

/** The bootstrap: cached at once when fresh, the cached one plus a background refresh when stale. */
export const getBootstrap = () => cached(BOOTSTRAP_KEY, fetchBootstrap, BOOTSTRAP_OPTIONS);

/**
 * After a join, leave or other change of the shell's data: the cached answer stays on screen (the frame does not blank),
 * a request asked before the change is dropped, and the server is asked again now.
 */
export function reloadBootstrap(): Promise<BootstrapOut> {
  markStale(BOOTSTRAP_KEY);
  return revalidate(BOOTSTRAP_KEY, fetchBootstrap, BOOTSTRAP_OPTIONS);
}

/** The cached bootstrap (fresh or stale), read synchronously; null when none. */
export const peekBootstrap = (): BootstrapOut | null => peek<BootstrapOut>(BOOTSTRAP_KEY)?.value ?? null;
