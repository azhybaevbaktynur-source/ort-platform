"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BOOTSTRAP_KEY, BOOTSTRAP_OPTIONS, fetchBootstrap, getBootstrap, reloadBootstrap, type BootstrapOut } from "@/lib/lms/bootstrap";
import type { MyAccessOut } from "@/lib/lms/access";
import type { LessonCourseOut } from "@/lib/lms/courses";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { revalidate, useCached } from "@/lib/lms/swr";
import type { CourseOut } from "@/lib/lms/types";

/*
 * Student UI U2, reduced by step 3a S3 (STUDENT_IA_DESIGN §2.1, §6.4): what the student frame needs besides MeOut: the
 * student's courses (every one, in the home's order: the «Мои курсы» rows, «Продолжить» in the phone bar), the pass,
 * and each exam course's attached lesson courses (the Уроки tab reads them from here, no request of its own). There is
 * no "current course" any more: a course space is about one course, the frame about the person. All of it comes from
 * `GET /me/bootstrap` (cached per token by `swr`, shown at once while a fresh one loads); it only draws the menu, the
 * server decides every request.
 */

export interface StudentShellData {
  /** Every student course, in the home's order (newest enrolment first). */
  courses: HomeCourseOut[];
  loaded: boolean;
  access: MyAccessOut | null;
  /** U9: the student left this course: drop it from the list at once, then read the list again. */
  forget: (id: string) => void;
  /** TEACHER_TO_STUDENT_MAP §2.4: an exam course's lesson courses from the bootstrap (null: not known here). */
  lessonCoursesOf: (examId: string) => LessonCourseOut[] | null;
}

const NO_COURSES: HomeCourseOut[] = [];
const NO_LESSONS: Record<string, LessonCourseOut[]> = {};
const NO_IDS: string[] = [];

/** Asks the bootstrap again, sharing a request already running (e.g. the one `meStale` started after a join). */
const refreshBootstrap = () => revalidate(BOOTSTRAP_KEY, fetchBootstrap, BOOTSTRAP_OPTIONS);

/**
 * `declared`: the course the course layout loaded (tells about a course joined a moment ago); `onHome`: the path is
 * the hub (`/home`).
 */
export function useStudentShellData({ enabled, declared, onHome, pathKey }: {
  enabled: boolean;
  declared: CourseOut | null;
  onHome: boolean;
  /** Changes on every navigation (the access is read again after leaving /pro). */
  pathKey: string;
}): StudentShellData {
  const boot = useCached<BootstrapOut>(enabled ? BOOTSTRAP_KEY : null, fetchBootstrap, BOOTSTRAP_OPTIONS);
  const student = boot.data?.student ?? null;
  const loading = useRef<Set<string>>(new Set());

  const once = useCallback(async (key: string, run: () => Promise<unknown>) => {
    if (loading.current.has(key)) return;
    loading.current.add(key);
    try { await run(); } catch { /* the menu falls back to what it knows */ } finally { loading.current.delete(key); }
  }, []);

  // U9: a course just left disappears at once; the next bootstrap answer (without it) replaces this
  const [gone, setGone] = useState<{ ids: string[]; of: BootstrapOut | null }>({ ids: [], of: null });
  const goneIds = gone.of === boot.data ? gone.ids : NO_IDS;

  const allCourses = student?.courses ?? NO_COURSES;
  const courses = useMemo(() => {
    const list = allCourses.filter((c) => !goneIds.includes(c.id));
    return list.length ? list : NO_COURSES;
  }, [allCourses, goneIds]);
  const known = !!boot.data;
  const lessonsByExam = student?.lesson_courses ?? NO_LESSONS;

  // back on the hub: the cached answer, asked again once it is older than its freshness (a join or leave already
  // asked through `meStale`)
  const firstHome = useRef(true);
  useEffect(() => {
    if (!enabled || !onHome) return;
    if (firstHome.current) { firstHome.current = false; return; }
    void getBootstrap().catch(() => undefined);
  }, [enabled, onHome]);

  // the course layout loaded a course of this student that the list does not have yet (joined a moment ago): once
  const declaredMine = !!declared && declared.my_enrollment.role === "student" && !declared.my_enrollment.read_only;
  const asked = useRef<Set<string>>(new Set());
  const missing = declaredMine && known && !courses.some((c) => c.id === declared?.id);
  useEffect(() => {
    if (!enabled || !missing || !declared || asked.current.has(`course:${declared.id}`)) return;
    asked.current.add(`course:${declared.id}`);
    void once("bootstrap", refreshBootstrap);
  }, [enabled, missing, declared, once]);

  // §2.4: a lesson course joined a moment ago still shows as not joined in its exam's rows: the bootstrap is asked once
  const joinedStale = declaredMine && !!declared?.exam_course_id
    && !!lessonsByExam[declared.exam_course_id]?.some((r) => r.id === declared.id && !r.enrolled);
  useEffect(() => {
    if (!enabled || !joinedStale || !declared || asked.current.has(`lesson:${declared.id}`)) return;
    asked.current.add(`lesson:${declared.id}`);
    void once("bootstrap", refreshBootstrap);
  }, [enabled, joinedStale, declared, once]);

  const lessonCoursesOf = useCallback((examId: string) => (known && examId in lessonsByExam ? lessonsByExam[examId] : null),
    [known, lessonsByExam]);

  const forget = useCallback((id: string) => {
    setGone((prev) => ({ ids: [...(prev.of === boot.data ? prev.ids : []), id], of: boot.data }));
    void once("bootstrap", refreshBootstrap);
  }, [boot.data, once]);

  // the pass: read again after leaving /pro (a code may have been redeemed there)
  const lastPath = useRef(pathKey);
  useEffect(() => {
    if (!enabled) return;
    const leftUnlock = lastPath.current !== pathKey && /\/pro$/.test(lastPath.current);
    lastPath.current = pathKey;
    if (leftUnlock) void once("bootstrap", reloadBootstrap);
  }, [enabled, pathKey, once]);

  return { courses, loaded: known, access: student?.access ?? null, forget, lessonCoursesOf };
}
