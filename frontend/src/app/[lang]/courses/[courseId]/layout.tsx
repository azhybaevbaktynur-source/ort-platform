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
import { StaffCourseBar } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { useDeclareArea } from "@/components/lms/LmsShell"; // Phase 6b integration
// --- Phase 6 S6b begin --- (student course frame, skeleton)
import { CourseLoadingSkeleton, StudentCourseHeader, StudentCourseTabs } from "@/components/lms/home/StudentCourseFrame";
// --- Phase 6 S6b end ---

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

  // Phase 6b integration: course pages are Teaching for staff and Learning for students (header area switcher)
  const staffRole = course?.my_enrollment?.role === "teacher" || course?.my_enrollment?.role === "assistant";
  useDeclareArea(course ? (staffRole ? "teaching" : "learning") : null);

  const missing = (error as { status?: number } | null)?.status === 404;
  if (missing && !course) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("courses.notFound.title")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t("courses.notFound.body")}</p>
        <div className="mt-5 flex flex-wrap justify-center gap-3 text-sm font-medium">
          <Link href={`/${lang}/courses`} className="rounded-xl bg-brand-600 px-4 py-2 text-white hover:bg-brand-700">{t("courses.home.backToList")}</Link>
          <Link href={`/${lang}/courses/join`} className="rounded-xl border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-50">{t("courses.notFound.join")}</Link>
          {/* --- Phase 6 S6b: the catalog has its own page --- */}
          <Link href={`/${lang}/courses/catalog`} className="rounded-xl border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-50">{t("lms.nav.catalog")}</Link>
        </div>
      </div>
    );
  }
  if (error && !course) {
    return (
      <div className="space-y-4">
        <ErrorMessage error={error} onRetry={reload} />
        <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("courses.home.backToList")}</Link>
      </div>
    );
  }
  // --- Phase 6 S6b begin --- (UX S16: skeleton in the page layout instead of a loading line)
  if (!course) return <CourseLoadingSkeleton />;
  // student view: breadcrumbs + title without teacher states, scrollable tabs (UX S3, S5, S12, S14)
  if (course.my_enrollment.role === "student") {
    return (
      <CourseContext.Provider value={{ course, reload, setCourse }}>
        <StudentCourseHeader course={course} />
        <StudentCourseTabs courseId={course.id} />
        {children}
      </CourseContext.Provider>
    );
  }
  // --- Phase 6 S6b end ---

  const isTeacher = course.my_enrollment.role === "teacher";
  const staff = isStaffCourse(course);
  // --- Phase 6b S5c: staff course frame on the design system (course bar + scrollable tabs; pages own the h1) ---
  const role = course.my_enrollment.role;
  if (staff && (role === "teacher" || role === "assistant")) {
    return (
      <CourseContext.Provider value={{ course, reload, setCourse }}>
        <StaffCourseBar course={course} />
        <CourseTabs courseId={course.id} showSettings={isTeacher} />
        {children}
      </CourseContext.Provider>
    );
  }
  // --- Phase 6b S5c end ---
  // Fallback frame (any other role), unchanged.
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
