"use client";

// TEACHER_TO_STUDENT_MAP S3 (G1, §2.4): on the exam-prep home, the lesson courses attached to the current exam as one
// "Уроки" section of course cards (joined: progress, opens the overview; not joined: a one-tap join like the platform
// courses; staff of the lesson course: no join), and the "Продолжить урок" strip from `/me/home`'s `modules_next`,
// kept to the current exam and its lesson courses (hidden when empty). The rows come from the student shell (it reads
// them for the sidebar) when it shows this exam, else from one request.
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, PlayCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { joinOpenCourse } from "@/lib/lms/catalog";
import { listLessonCourses, type LessonCourseOut } from "@/lib/lms/courses";
import type { HomeModuleNextOut } from "@/lib/lms/homeTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Button, ErrorState } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { ItemKindIcon, itemHref } from "@/components/lms/modules/moduleUi";
import { lessonRoute } from "@/components/lms/modules/lessons";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { SideRow, SideSection } from "./TodoList";
import { useErrorText } from "./useErrorText";

/** The lesson courses of `examId`: null while unknown; [] when there are none or the read failed (nothing to show). */
export function useLessonCourseRows(examId: string): LessonCourseOut[] | null {
  const shell = useStudentShellDataContext();
  const fromShell = shell && shell.current?.id === examId;
  const [own, setOwn] = useState<{ examId: string; rows: LessonCourseOut[] } | null>(null);
  useEffect(() => {
    if (fromShell) return;
    const ctl = new AbortController();
    listLessonCourses(examId, ctl.signal).then(
      (rows) => { if (!ctl.signal.aborted) setOwn({ examId, rows }); },
      () => { if (!ctl.signal.aborted) setOwn({ examId, rows: [] }); },
    );
    return () => ctl.abort();
  }, [examId, fromShell]);
  if (fromShell) return shell.lessonCourses;
  return own?.examId === examId ? own.rows : null;
}

/** "Продолжить урок": the next item of the exam and of its lesson courses (the server's order, at most three). */
export function ContinueLessons({ rows }: { rows: HomeModuleNextOut[] }) {
  const { lang, t } = useTranslation();
  if (rows.length === 0) return null;
  const untitled = t("courses.list.untitled");
  return (
    <SideSection id="home-continue" title={t("home.prep.continueLesson.title")}>
      <ul className="divide-y divide-slate-100">
        {rows.map((r) => {
          const base = `/${lang}/courses/${r.course_id}`;
          const kind = r.kind ?? "page";
          const href = (kind === "assignment" ? itemHref(base, kind, r.link) : null) ?? lessonRoute(base, r.module_id, r.item_id);
          const course = pickLocalized(r.course_title, lang) || untitled;
          const mod = r.module_title ? pickLocalized(r.module_title, lang) : "";
          return (
            <SideRow key={`${r.course_id}:${r.item_id}`} href={href}
              icon={(
                <span aria-hidden="true" className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  {r.is_video && kind === "url"
                    ? <PlayCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
                    : <ItemKindIcon kind={kind} assignmentKind={r.link?.assignment_kind} />}
                </span>
              )}
              title={pickLocalized(r.title, lang) || untitled}
              lines={<span className="block break-words">{mod ? `${course} · ${mod}` : course}</span>}
              aside={<ChevronRight aria-hidden="true" className="mt-1.5 h-4 w-4 text-slate-400" />} />
          );
        })}
      </ul>
    </SideSection>
  );
}

/** The "Уроки" section: every lesson course of the exam as a card (nothing while unknown or with none). */
export function LessonCourses({ rows, grid }: { rows: LessonCourseOut[] | null; grid: string }) {
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
      router.push(`/${lang}/courses/${res.course.id}/modules`);
    } catch (e) {
      setError({ id, error: e });
      setJoining(null);
    }
  };

  return (
    <section aria-labelledby="home-lesson-courses" className="min-w-0">
      <h2 id="home-lesson-courses" className="text-lg font-semibold leading-7 text-slate-900">{t("student.nav.lessonsGroup")}</h2>
      <p className="mb-3 text-sm leading-5 text-slate-600">{t("home.prep.lessonCourses.subtitle")}</p>
      <ul className={grid}>
        {rows.map((r) => {
          const staff = !!r.is_staff;
          const href = staff ? `/${lang}/courses/${r.id}` : r.enrolled ? `/${lang}/courses/${r.id}/modules` : `/${lang}/courses/catalog/${r.id}`;
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
