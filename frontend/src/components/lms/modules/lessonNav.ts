"use client";

// Student UI U7 (STUDENT_UI_DESIGN §2.2): the "Видеоуроки" sub-links of the student sidebar: the first five modules of
// the current course that hold lessons. Kept per course for this tab (memory + sessionStorage); the syllabus writes it
// whenever it loads, so the sidebar asks the server at most once per course and tab, and only on a wide screen (the
// phone "More" sheet shows what is already known). The links only scroll the syllabus; the server decides every lock.
import { useEffect, useState } from "react";
import { getModules } from "@/lib/lms/modules";
import { isStaffModules, type ModuleStudentOut } from "@/lib/lms/modulesTypes";
import type { LocalizedText } from "@/lib/lms/types";

export interface LessonModuleLink {
  id: string;
  title: LocalizedText;
}

const KEY = "ort_lesson_modules";
const MAX = 5;
const LESSON_KINDS = new Set(["page", "url", "file"]);
let memory: Record<string, LessonModuleLink[]> | null = null;
const listeners = new Set<() => void>();
const loading = new Set<string>();

function read(): Record<string, LessonModuleLink[]> {
  if (memory) return memory;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    memory = raw ? (JSON.parse(raw) as Record<string, LessonModuleLink[]>) : {};
  } catch {
    memory = {};
  }
  return memory;
}

/** Called by the syllabus with the modules it just loaded. */
export function rememberLessonModules(courseId: string, modules: ModuleStudentOut[]) {
  const links = modules
    .filter((m) => m.items.some((i) => LESSON_KINDS.has(i.kind)))
    .slice(0, MAX)
    .map((m) => ({ id: m.id, title: m.title }));
  const prev = read()[courseId];
  if (prev && JSON.stringify(prev) === JSON.stringify(links)) return;
  memory = { ...read(), [courseId]: links };
  try { window.sessionStorage.setItem(KEY, JSON.stringify(memory)); } catch { /* the cache is optional */ }
  listeners.forEach((l) => l());
}

/** The sub-links of `courseId` (null: not known yet). `fetchIfMissing`: ask the server once when nothing is cached. */
export function useLessonModules(courseId: string | null, enabled: boolean, fetchIfMissing: boolean): LessonModuleLink[] | null {
  // `version` > 0 only after mount: the server render and the first client render agree (no cache read)
  const [version, bump] = useState(0);
  useEffect(() => {
    const on = () => bump((n) => n + 1);
    listeners.add(on);
    on();
    return () => { listeners.delete(on); };
  }, []);
  const known = version > 0 && enabled && courseId ? read()[courseId] ?? null : null;
  useEffect(() => {
    if (!enabled || !courseId || !fetchIfMissing || read()[courseId] || loading.has(courseId)) return;
    loading.add(courseId);
    getModules(courseId)
      .then((out) => { if (!isStaffModules(out)) rememberLessonModules(courseId, out.modules ?? []); })
      .catch(() => undefined) // the sidebar simply shows no sub-links
      .finally(() => loading.delete(courseId));
  }, [enabled, courseId, fetchIfMissing]);
  return known;
}
