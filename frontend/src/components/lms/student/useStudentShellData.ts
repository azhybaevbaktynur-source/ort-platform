"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BOOTSTRAP_KEY, BOOTSTRAP_OPTIONS, fetchBootstrap, getBootstrap, reloadBootstrap, type BootstrapOut } from "@/lib/lms/bootstrap";
import type { MyAccessOut } from "@/lib/lms/access";
import { getCourse, type LessonCourseOut } from "@/lib/lms/courses";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { revalidate, useCached } from "@/lib/lms/swr";
import type { CourseOut } from "@/lib/lms/types";

/*
 * Student UI U2 (STUDENT_UI_DESIGN §2.2): what the student shell needs besides MeOut: the student's exam-prep courses
 * (`HomeCourseOut.student_layout`), the current one (this device remembers the last opened), what that course has
 * (lessons, practice) and the student's pass. TEACHER_TO_STUDENT_MAP §2.4: plus the lesson courses attached to each
 * exam, and a lesson course's exam (`exam_course_id`), so inside a lesson course the current exam is the one it belongs to.
 * PERFORMANCE_AUDIT S2: all of it comes from `GET /me/bootstrap` (the courses, the pass and every exam's lesson courses
 * in one answer, cached per token by `swr`, shown at once while a fresh one loads); it only draws the menu, the server
 * decides every request.
 */

export interface StudentCourseFeatures {
  modules: boolean;
  practice: boolean;
}

export interface StudentShellData {
  /** Exam-prep courses of the student, in the home's order. */
  courses: HomeCourseOut[];
  loaded: boolean;
  current: HomeCourseOut | null;
  setCurrent: (id: string) => void;
  features: StudentCourseFeatures | null;
  access: MyAccessOut | null;
  /** U9: the student left this course: drop it from the list at once, then read the list again. */
  forget: (id: string) => void;
  /** TEACHER_TO_STUDENT_MAP §2.4: the lesson courses of the current exam (null: not known yet). */
  lessonCourses: LessonCourseOut[] | null;
  /** The exam the lesson course of the current path belongs to (null: the path is not inside a lesson course). */
  lessonCourseExam: string | null;
}

const CURRENT_KEY = "ort_student_course";
const NO_COURSES: HomeCourseOut[] = [];
const NO_LESSONS: Record<string, LessonCourseOut[]> = {};
const NO_IDS: string[] = [];

function readCurrent(): string | null {
  try { return window.localStorage.getItem(CURRENT_KEY); } catch { return null; }
}

function writeCurrent(id: string) {
  try { window.localStorage.setItem(CURRENT_KEY, id); } catch { /* private mode: the first course is used */ }
}

const featuresOf = (c: CourseOut): StudentCourseFeatures => ({ modules: !!c.features?.modules, practice: !!c.features?.practice });

/** Asks the bootstrap again, sharing a request already running (e.g. the one `meStale` started after a join). */
const refreshBootstrap = () => revalidate(BOOTSTRAP_KEY, fetchBootstrap, BOOTSTRAP_OPTIONS);

/**
 * `pathCourseId`: the course of the current path, if any; `declared`: the course the course layout loaded (saves a
 * request and tells about a course joined a moment ago); `onHome`: the path is the home (`/courses`).
 */
export function useStudentShellData({ enabled, pathCourseId, declared, onHome, pathKey }: {
  enabled: boolean;
  pathCourseId: string | null;
  declared: CourseOut | null;
  onHome: boolean;
  /** Changes on every navigation (the access is read again after leaving /pro). */
  pathKey: string;
}): StudentShellData {
  const boot = useCached<BootstrapOut>(enabled ? BOOTSTRAP_KEY : null, fetchBootstrap, BOOTSTRAP_OPTIONS);
  const student = boot.data?.student ?? null;
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [extraFeatures, setExtraFeatures] = useState<Record<string, StudentCourseFeatures>>({});
  const loading = useRef<Set<string>>(new Set());

  const once = useCallback(async (key: string, run: () => Promise<unknown>) => {
    if (loading.current.has(key)) return;
    loading.current.add(key);
    try { await run(); } catch { /* the menu falls back to what it knows */ } finally { loading.current.delete(key); }
  }, []);

  useEffect(() => {
    if (enabled) setCurrentId(readCurrent());
  }, [enabled]);

  // U9: a course just left disappears at once; the next bootstrap answer (without it) replaces this
  const [gone, setGone] = useState<{ ids: string[]; of: BootstrapOut | null }>({ ids: [], of: null });
  const goneIds = gone.of === boot.data ? gone.ids : NO_IDS;

  const allCourses = student?.courses ?? NO_COURSES;
  const courses = useMemo(() => {
    const list = allCourses.filter((c) => c.student_layout === "exam_prep" && !goneIds.includes(c.id));
    return list.length ? list : NO_COURSES;
  }, [allCourses, goneIds]);
  const known = !!boot.data;
  const lessonsByExam = student?.lesson_courses ?? NO_LESSONS;

  // §2.4: lesson course -> its exam: the lesson courses the student joined name it, and every exam's rows list theirs
  const examOf = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [examId, rows] of Object.entries(lessonsByExam)) for (const r of rows) out[r.id] = examId;
    for (const c of allCourses) if (c.exam_course_id) out[c.id] = c.exam_course_id;
    return out;
  }, [allCourses, lessonsByExam]);

  // back on the home: the cached answer, asked again once it is older than its freshness (a join or leave already
  // asked through `meStale`)
  const firstHome = useRef(true);
  useEffect(() => {
    if (!enabled || !onHome) return;
    if (firstHome.current) { firstHome.current = false; return; }
    void getBootstrap().catch(() => undefined);
  }, [enabled, onHome]);

  // the course layout loaded an exam-prep course this list does not have yet (joined a moment ago): once per course
  const declaredExamPrep = !!declared && declared.template?.student_layout === "exam_prep" && declared.my_enrollment.role === "student";
  useEffect(() => {
    if (!enabled || !declared) return;
    const f = featuresOf(declared);
    setExtraFeatures((prev) => {
      const had = prev[declared.id];
      return had && had.modules === f.modules && had.practice === f.practice ? prev : { ...prev, [declared.id]: f };
    });
  }, [enabled, declared]);
  const asked = useRef<Set<string>>(new Set());
  const missing = declaredExamPrep && known && !courses.some((c) => c.id === declared?.id);
  useEffect(() => {
    if (!enabled || !missing || !declared || asked.current.has(`course:${declared.id}`)) return;
    asked.current.add(`course:${declared.id}`);
    void once("bootstrap", refreshBootstrap);
  }, [enabled, missing, declared, once]);

  // §2.4: a lesson course of the path names its exam (the layout's course first, then what the lists told)
  const lessonCourseExam = !pathCourseId
    ? null
    : declared?.id === pathCourseId
      ? declared.exam_course_id ?? null
      : examOf[pathCourseId] ?? null;
  // the current course: the one being viewed (or the exam of the lesson course being viewed) when it is an exam course,
  // else the remembered one, else the first
  const viewedId = lessonCourseExam ?? pathCourseId;
  const viewed = viewedId && courses.some((c) => c.id === viewedId) ? viewedId : null;
  useEffect(() => {
    if (viewed && viewed !== currentId) {
      setCurrentId(viewed);
      writeCurrent(viewed);
    }
  }, [viewed, currentId]);
  const current = courses.find((c) => c.id === (viewed ?? currentId)) ?? courses[0] ?? null;

  const setCurrent = useCallback((id: string) => {
    setCurrentId(id);
    writeCurrent(id);
  }, []);

  // what the current course has: with the course list (U9: the same menu on every page), else from the course layout
  // when the student is inside it, else one request (an older backend without `features`)
  const features = current ? current.features ?? extraFeatures[current.id] ?? null : null;
  const waitForLayout = !!current && pathCourseId === current.id && declared?.id !== current.id;
  useEffect(() => {
    if (!enabled || !current || features || waitForLayout) return;
    const id = current.id;
    void once(`course:${id}`, async () => {
      const c = await getCourse(id);
      setExtraFeatures((prev) => ({ ...prev, [id]: featuresOf(c) }));
    });
  }, [enabled, current, features, waitForLayout, once]);

  // §2.4: the current exam's lesson courses (from the bootstrap); when the student just joined one and the rows still
  // show it as not joined, the bootstrap is asked again once
  const currentExamId = current?.id ?? null;
  const lessonCourses = currentExamId && known ? lessonsByExam[currentExamId] ?? [] : null;
  const joinedStale = !!declared && declared.my_enrollment.role === "student" && !declared.my_enrollment.read_only
    && !!lessonCourses?.some((r) => r.id === declared.id && !r.enrolled);
  useEffect(() => {
    if (!enabled || !joinedStale || !declared || asked.current.has(`lesson:${declared.id}`)) return;
    asked.current.add(`lesson:${declared.id}`);
    void once("bootstrap", refreshBootstrap);
  }, [enabled, joinedStale, declared, once]);

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

  return {
    courses, loaded: known, current, setCurrent, features, access: student?.access ?? null, forget, lessonCourses, lessonCourseExam,
  };
}
