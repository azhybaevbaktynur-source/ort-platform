"use client";

// TEACHER_TO_STUDENT_MAP §2.4 (R5): `/courses/{exam}/lessons`, "Все уроки": every lesson course attached to the exam as
// cards, linked from the sidebar only when the УРОКИ group has more rows than it shows. Joined: the course overview;
// not joined: its catalog landing (which joins).
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listLessonCourses, type LessonCourseOut } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { COURSE_GRID, CourseCard } from "@/components/lms/course/CourseCard";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { ProCallout } from "@/components/lms/access/ProCallout";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";

export default function LessonCoursesPage() {
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
              href={r.enrolled ? `/${lang}/courses/${r.id}/modules` : `/${lang}/courses/catalog/${r.id}`}
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
