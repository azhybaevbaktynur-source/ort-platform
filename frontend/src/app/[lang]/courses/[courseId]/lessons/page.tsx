"use client";

// Step 3a S2 (STUDENT_IA_DESIGN §3.2, D5): `/courses/{c}/lessons` is the Уроки tab of the course space: the syllabus
// (`StudentSyllabus`), then for an exam course the section «Курсы с уроками к экзамену» (the lesson courses attached to
// the exam as cards; joined: their Обзор; not joined: the catalog landing, which joins). Anyone else (staff, read-only
// viewers) keeps the lesson-course list of TEACHER_TO_STUDENT_MAP §2.4 at this URL.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listLessonCourses, type LessonCourseOut } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { inCourseSpace, templateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { COURSE_GRID, CourseCard } from "@/components/lms/course/CourseCard";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { LessonCourses, useLessonCourseRows } from "@/components/lms/home/LessonCourses";
import { StudentSyllabus } from "@/components/lms/modules/StudentSyllabus";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { ProCallout } from "@/components/lms/access/ProCallout";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";

export default function LessonsRoute() {
  const { course } = useCourse();
  return inCourseSpace(course) ? <LessonsTab /> : <LessonCoursesPage />;
}

/** The Уроки tab: the syllabus, then the exam's lesson courses (D5). */
function LessonsTab() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const exam = templateUi(course).studentLayout === "exam_prep";
  const rows = useLessonCourseRows(exam ? course.id : null);
  const access = useStudentShellDataContext()?.access ?? null;
  const lessonCourses = rows && rows.length > 0 ? (
    <>
      {access && !access.active && !course.features?.modules && rows.some((r) => r.has_paid_modules) && <ProCallout variant="course" />}
      <LessonCourses rows={rows} grid={COURSE_GRID} title={t("course.overview.lessonCourses")} subtitle={null} headingId="lesson-courses" />
    </>
  ) : null;
  if (!course.features?.modules) {
    // an exam course with lesson courses only: the tab title and the cards (the tab is hidden otherwise)
    return (
      <div className="flex w-full flex-col gap-4 lg:gap-6">
        <StudentPageHeader title={t("course.tabs.lessons")} />
        {rows === null ? <LoadingState rows={3} /> : lessonCourses}
      </div>
    );
  }
  return <StudentSyllabus after={lessonCourses} />;
}

/** TEACHER_TO_STUDENT_MAP §2.4 (R5): "Все уроки", every lesson course attached to the exam as cards (staff, readers). */
function LessonCoursesPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const access = useStudentShellDataContext()?.access ?? null;
  const [rows, setRows] = useState<LessonCourseOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listLessonCourses(course.id));
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  const examTitle = pickLocalized(course.title, lang, course.default_language);
  return (
    <div className="flex w-full flex-col gap-6">
      <StudentPageHeader title={t("student.nav.allLessons")} subtitle={examTitle || undefined} />
      {error && !rows ? (
        <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />
      ) : !rows ? (
        <LoadingState rows={3} />
      ) : rows.length === 0 ? (
        <EmptyState mascot="reading" title={t("student.lessonCourses.emptyTitle")} description={t("student.lessonCourses.emptyBody")} />
      ) : (
        <>
        {access && !access.active && rows.some((r) => r.has_paid_modules) && <ProCallout variant="course" />}
        <ul className={COURSE_GRID}>
          {rows.map((r) => (
            <CourseCard key={r.id} headingLevel={2}
              href={r.enrolled ? `/${lang}/courses/${r.id}` : `/${lang}/courses/catalog/${r.id}`}
              progress={r.enrolled ? r.progress : null}
              course={{
                id: r.id, title: r.title, languages: [], default_language: course.default_language,
                is_platform_course: r.is_platform_course, cover_url: r.cover_url, lessons_count: r.lessons_count,
                has_paid_tests: r.has_paid_modules,
              }} />
          ))}
        </ul>
        </>
      )}
    </div>
  );
}
