"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getStudentView } from "@/lib/api";
import { getMyAccess, type MyAccessOut } from "@/lib/lms/access";
import { getCourse, listLessonCourses, type LessonCourseOut } from "@/lib/lms/courses";
import { listHomeCourses } from "@/lib/lms/home";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import type { CourseOut } from "@/lib/lms/types";

/*
 * Student UI U2 (STUDENT_UI_DESIGN §2.2): what the student shell needs besides MeOut: the student's exam-prep courses
 * (`HomeCourseOut.student_layout`), the current one (this device remembers the last opened), what that course has
 * (lessons, practice) and the student's pass. Like `useLmsMe`, answers are kept per token (memory + this tab's
 * sessionStorage) and shown at once while fresh ones load; they only draw the menu, the server decides every request.
 * TEACHER_TO_STUDENT_MAP §2.4: plus the lesson courses attached to each exam (cached per exam like `features`), and a
 * lesson course's exam (`exam_course_id`), so inside a lesson course the current exam is the one it belongs to.
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

interface Cache {
  token: string;
  courses: HomeCourseOut[] | null;
  access: MyAccessOut | null;
  features: Record<string, StudentCourseFeatures>;
  /** exam id -> its lesson courses */
  lessons: Record<string, LessonCourseOut[]>;
  /** lesson course id -> its exam id */
  examOf: Record<string, string>;
}

// v2 (TEACHER_TO_STUDENT_MAP §2.4): `lessons` and `examOf` added; an older saved shape is dropped
const CACHE_KEY = "ort_student_shell_v2";
const CURRENT_KEY = "ort_student_course";
const COURSES_LIMIT = 50;
let memory: Cache | null = null;
const NO_COURSES: HomeCourseOut[] = [];

function activeToken(): string {
  if (typeof window === "undefined") return "";
  return (getStudentView()?.token ?? window.localStorage.getItem("ort_token") ?? "").slice(-16);
}

function emptyCache(token: string): Cache {
  return { token, courses: null, access: null, features: {}, lessons: {}, examOf: {} };
}

function readCache(): Cache {
  const token = activeToken();
  if (memory?.token === token) return memory;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    const saved = raw ? (JSON.parse(raw) as Partial<Cache>) : null;
    if (saved && saved.token === token) {
      memory = {
        token, courses: saved.courses ?? null, access: saved.access ?? null, features: saved.features ?? {},
        lessons: saved.lessons ?? {}, examOf: saved.examOf ?? {},
      };
      return memory;
    }
  } catch { /* storage blocked or a bad value */ }
  memory = emptyCache(token);
  return memory;
}

function writeCache(patch: Partial<Omit<Cache, "token">>): Cache {
  const next = { ...readCache(), ...patch };
  memory = next;
  try { window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(next)); } catch { /* the cache is optional */ }
  return next;
}

function readCurrent(): string | null {
  try { return window.localStorage.getItem(CURRENT_KEY); } catch { return null; }
}

function writeCurrent(id: string) {
  try { window.localStorage.setItem(CURRENT_KEY, id); } catch { /* private mode: the first course is used */ }
}

const featuresOf = (c: CourseOut): StudentCourseFeatures => ({ modules: !!c.features?.modules, practice: !!c.features?.practice });

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
  const [cache, setCache] = useState<Cache | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const loading = useRef<Set<string>>(new Set());

  const once = useCallback(async (key: string, run: () => Promise<void>) => {
    if (loading.current.has(key)) return;
    loading.current.add(key);
    try { await run(); } catch { /* the menu falls back to what it knows */ } finally { loading.current.delete(key); }
  }, []);

  const loadCourses = useCallback(() => once("courses", async () => {
    const page = await listHomeCourses(null, COURSES_LIMIT);
    // §2.4: the lesson courses the student joined name their exam (the shell keeps the exam chip inside them)
    const examOf = { ...readCache().examOf };
    for (const c of page.items) if (c.exam_course_id) examOf[c.id] = c.exam_course_id;
    setCache(writeCache({ courses: page.items.filter((c) => c.student_layout === "exam_prep"), examOf }));
  }), [once]);

  const loadAccess = useCallback(() => once("access", async () => {
    setCache(writeCache({ access: await getMyAccess() }));
  }), [once]);

  // §2.4: the lesson courses of one exam; a refused or failed read leaves an empty group (no retry loop)
  const loadLessons = useCallback((examId: string) => once(`lessons:${examId}`, async () => {
    let rows: LessonCourseOut[];
    try {
      rows = await listLessonCourses(examId);
    } catch {
      rows = readCache().lessons[examId] ?? [];
    }
    const examOf = { ...readCache().examOf };
    for (const r of rows) examOf[r.id] = examId;
    setCache(writeCache({ lessons: { ...readCache().lessons, [examId]: rows }, examOf }));
  }), [once]);

  // first use: the cached answer at once, then fresh courses
  useEffect(() => {
    if (!enabled) return;
    setCache(readCache());
    setCurrentId(readCurrent());
    void loadCourses();
  }, [enabled, loadCourses]);

  // back on the home: the list again (a course may have been joined or left), the lesson rows too
  const firstHome = useRef(true);
  const freshLessons = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!enabled || !onHome) return;
    if (firstHome.current) { firstHome.current = false; return; }
    freshLessons.current.clear();
    void loadCourses();
  }, [enabled, onHome, loadCourses]);

  const courses = cache?.courses ?? NO_COURSES;
  const known = cache?.courses != null;

  // the course layout loaded an exam-prep course this list does not have yet (joined a moment ago)
  const declaredExamPrep = !!declared && declared.template?.student_layout === "exam_prep" && declared.my_enrollment.role === "student";
  useEffect(() => {
    if (!enabled || !declared) return;
    setCache(writeCache({ features: { ...readCache().features, [declared.id]: featuresOf(declared) } }));
  }, [enabled, declared]);
  const missing = declaredExamPrep && known && !courses.some((c) => c.id === declared?.id);
  useEffect(() => {
    if (enabled && missing) void loadCourses();
  }, [enabled, missing, loadCourses]);

  // §2.4: a lesson course of the path names its exam (the layout's course first, then what the lists told)
  const lessonCourseExam = !pathCourseId
    ? null
    : declared?.id === pathCourseId
      ? declared.exam_course_id ?? null
      : cache?.examOf[pathCourseId] ?? null;
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
  // when the student is inside it, else one request (an older backend or cache without `features`)
  const features = current ? current.features ?? cache?.features[current.id] ?? null : null;
  const waitForLayout = !!current && pathCourseId === current.id && declared?.id !== current.id;
  useEffect(() => {
    if (!enabled || !current || features || waitForLayout) return;
    const id = current.id;
    void once(`course:${id}`, async () => {
      const c = await getCourse(id);
      setCache(writeCache({ features: { ...readCache().features, [id]: featuresOf(c) } }));
    });
  }, [enabled, current, features, waitForLayout, once]);

  // §2.4: the current exam's lesson courses: the cached rows at once, read again once per shell and exam (and after
  // the home), and when the student just joined one the rows still show as not joined
  const currentExamId = current?.id ?? null;
  const lessonCourses = currentExamId ? cache?.lessons[currentExamId] ?? null : null;
  const joinedStale = !!declared && declared.my_enrollment.role === "student" && !declared.my_enrollment.read_only
    && !!lessonCourses?.some((r) => r.id === declared.id && !r.enrolled);
  useEffect(() => {
    if (!enabled || !currentExamId) return;
    if (freshLessons.current.has(currentExamId) && !joinedStale) return;
    freshLessons.current.add(currentExamId);
    void loadLessons(currentExamId);
  }, [enabled, currentExamId, joinedStale, onHome, loadLessons]);

  const forget = useCallback((id: string) => {
    const known = readCache().courses;
    if (known) setCache(writeCache({ courses: known.filter((c) => c.id !== id) }));
    void loadCourses();
  }, [loadCourses]);

  // the pass: only students with an exam course see the access pill; read again after leaving /pro
  const hasCourses = courses.length > 0;
  const lastPath = useRef(pathKey);
  useEffect(() => {
    if (!enabled || !hasCourses) return;
    const leftUnlock = lastPath.current !== pathKey && /\/pro$/.test(lastPath.current);
    lastPath.current = pathKey;
    if (!readCache().access || leftUnlock) void loadAccess();
  }, [enabled, hasCourses, pathKey, loadAccess]);
  const firstAccess = useRef(true);
  useEffect(() => {
    if (!enabled || !hasCourses || !firstAccess.current) return;
    firstAccess.current = false;
    if (readCache().access) void loadAccess(); // a cached pass shown at once is refreshed once per shell
  }, [enabled, hasCourses, loadAccess]);

  return {
    courses, loaded: known, current, setCurrent, features, access: cache?.access ?? null, forget, lessonCourses, lessonCourseExam,
  };
}
