"use client";

// Lesson course requests C3 (R2): where the result of a lesson quiz leads. The quiz's syllabus row is the lesson the
// attempt was started from (`?return=/…/modules/{m}/items/{i}`), else the first row holding this quiz; «Следующий урок»
// is the row after it in course order (the same list the lesson page and its pager use). Locks are the server's: a
// locked next row is not offered.
import { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getModules } from "@/lib/lms/modules";
import { isStaffModules } from "@/lib/lms/modulesTypes";
import { inCourseSpace } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { isLocked, lessonHref, lessonList, lessonRoute, type LessonRef } from "@/components/lms/modules/lessons";

export interface QuizLesson {
  /** The lesson page of the quiz's row. */
  lessonHref: string;
  /** The next open row (null: the last row, or the next one is locked). */
  nextHref: string | null;
  /** Уроки (the syllabus). */
  syllabusHref: string;
}

const LESSON_PATH = /\/modules\/([^/?#]+)\/items\/([^/?#]+)/;

/** The quiz's row: the lesson of `returnPath` when it holds this quiz, else the first row linking the assessment. */
export function findQuizLesson(lessons: LessonRef[], assessmentId: string, returnPath: string | null): LessonRef | null {
  const m = returnPath ? LESSON_PATH.exec(returnPath) : null;
  if (m) {
    const hit = lessons.find((l) => l.mod.id === m[1] && l.item.id === m[2]);
    if (hit && hit.item.link?.assessment_id === assessmentId) return hit;
  }
  return lessons.find((l) => l.item.kind === "assignment" && l.item.link?.assessment_id === assessmentId) ?? null;
}

/** null while unknown, when `assessmentId` is null, or when no syllabus row holds the quiz. */
export function useQuizLesson(courseId: string, assessmentId: string | null, returnPath: string | null): QuizLesson | null {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const [out, setOut] = useState<QuizLesson | null>(null);
  const space = inCourseSpace(course);
  useEffect(() => {
    if (!assessmentId) { setOut(null); return; }
    let live = true;
    const base = `/${lang}/courses/${courseId}`;
    getModules(courseId)
      .then((res) => {
        if (!live || isStaffModules(res)) return;
        const lessons = lessonList(res.modules ?? []);
        const here = findQuizLesson(lessons, assessmentId, returnPath);
        if (!here) { setOut(null); return; }
        const next = here.index < lessons.length - 1 ? lessons[here.index + 1] : null;
        setOut({
          lessonHref: lessonRoute(base, here.mod.id, here.item.id),
          nextHref: next && !isLocked(next.mod, next.item) ? lessonHref(base, next) : null,
          syllabusHref: `${base}/${space ? "lessons" : "modules"}`,
        });
      })
      .catch(() => { if (live) setOut(null); }); // the result page keeps its own actions
    return () => { live = false; };
  }, [courseId, assessmentId, returnPath, lang, space]);
  return out;
}
