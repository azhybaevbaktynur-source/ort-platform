"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse, type CourseOut } from "@/lib/lms/types";
import { CourseContext } from "@/components/lms/CourseContext";
import { CourseTabs } from "@/components/lms/CourseTabs";
import { StatusBadge } from "@/components/lms/CourseCard";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

export default function CourseLayout({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const params = useParams<{ courseId: string }>();
  const courseId = params.courseId;
  const [course, setCourse] = useState<CourseOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(async () => {
    try {
      setCourse(await getCourse(courseId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId]);

  useEffect(() => {
    setCourse(null);
    void reload();
  }, [reload]);

  if (error && !course) {
    return (
      <div className="space-y-4">
        <ErrorMessage error={error} onRetry={reload} />
        <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("courses.home.backToList")}</Link>
      </div>
    );
  }
  if (!course) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  const isTeacher = course.my_enrollment.role === "teacher";
  const staff = isStaffCourse(course);
  return (
    <CourseContext.Provider value={{ course, reload, setCourse }}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("courses.home.backToList")}</Link>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-900">{pickLocalized(course.title, lang, course.default_language)}</h1>
        <StatusBadge status={course.status} />
      </div>
      <CourseTabs courseId={course.id} showSettings={isTeacher && staff} />
      {children}
    </CourseContext.Provider>
  );
}
