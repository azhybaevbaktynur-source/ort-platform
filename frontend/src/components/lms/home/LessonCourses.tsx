"use client";

// TEACHER_TO_STUDENT_MAP S3 (G1, §2.4), step 3a S2: the lesson courses attached to an exam as one section of course
// cards (joined: progress, opens the overview; not joined: a one-tap join; staff of the lesson course: no join), on the
// exam's Уроки tab and Обзор. The rows come from the student shell's bootstrap when it has them, else from one request.
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { joinOpenCourse } from "@/lib/lms/catalog";
import { listLessonCourses, type LessonCourseOut } from "@/lib/lms/courses";
import type { Lang } from "@/lib/lms/types";
import { Button, ErrorState } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { useErrorText } from "./useErrorText";

/** The lesson courses of `examId`: null while unknown; [] when there are none or the read failed (nothing to show). */
/** Step 3a S2: `examId` null asks nothing (a course that is not an exam course) and gives []. */
export function useLessonCourseRows(examId: string | null): LessonCourseOut[] | null {
  const shell = useStudentShellDataContext();
  // step 3a S3: the bootstrap's rows of this exam (no "current course" any more), else one request
  const shellRows = examId && shell ? shell.lessonCoursesOf(examId) : null;
  const fromShell = !!shellRows;
  const [own, setOwn] = useState<{ examId: string; rows: LessonCourseOut[] } | null>(null);
  useEffect(() => {
    if (fromShell || !examId) return;
    const ctl = new AbortController();
    listLessonCourses(examId, ctl.signal).then(
      (rows) => { if (!ctl.signal.aborted) setOwn({ examId, rows }); },
      () => { if (!ctl.signal.aborted) setOwn({ examId, rows: [] }); },
    );
    return () => ctl.abort();
  }, [examId, fromShell]);
  if (!examId) return [];
  if (shellRows) return shellRows;
  return own?.examId === examId ? own.rows : null;
}

/** The "Уроки" section: every lesson course of the exam as a card (nothing while unknown or with none). */
export function LessonCourses({ rows, grid, title, subtitle, headingId = "home-lesson-courses" }: {
  rows: LessonCourseOut[] | null; grid: string;
  /** step 3a S2: the Уроки tab names the section «Курсы с уроками к экзамену» (no subtitle) */
  title?: string; subtitle?: string | null; headingId?: string;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const [joining, setJoining] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; error: unknown } | null>(null);
  if (!rows || rows.length === 0) return null;

  const join = async (id: string) => {
    setJoining(id);
    setError(null);
    try {
      const res = await joinOpenCourse(id);
      router.push(`/${lang}/courses/${res.course.id}`); // step 3a S2: «Записаться» lands on the Обзор
    } catch (e) {
      setError({ id, error: e });
      setJoining(null);
    }
  };

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <h2 id={headingId} className={subtitle === null ? "mb-3 text-lg font-semibold leading-7 text-slate-900" : "text-lg font-semibold leading-7 text-slate-900"}>{title ?? t("student.nav.lessonsGroup")}</h2>
      {subtitle !== null && <p className="mb-3 text-sm leading-5 text-slate-600">{subtitle ?? t("home.prep.lessonCourses.subtitle")}</p>}
      <ul className={grid}>
        {rows.map((r) => {
          const staff = !!r.is_staff;
          const href = staff ? `/${lang}/courses/${r.id}` : r.enrolled ? `/${lang}/courses/${r.id}` : `/${lang}/courses/catalog/${r.id}`;
          return (
            <CourseCard key={r.id} href={href} progress={r.enrolled ? r.progress : null}
              course={{
                id: r.id, title: r.title, languages: [], default_language: lang as Lang,
                is_platform_course: r.is_platform_course, cover_url: r.cover_url, lessons_count: r.lessons_count,
                has_paid_tests: r.has_paid_modules,
              }}
              action={!r.enrolled && !staff ? (
                <>
                  {/* the Next card holds the page's primary button */}
                  <Button fullWidth variant="secondary" loading={joining === r.id} disabled={joining !== null && joining !== r.id}
                    onClick={() => void join(r.id)}>
                    {t("catalog.join")}
                  </Button>
                  {error?.id === r.id && <ErrorState variant="inline" message={errorText(error.error)} className="mt-3" />}
                </>
              ) : undefined} />
          );
        })}
      </ul>
    </section>
  );
}
