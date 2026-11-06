"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { courseNavRole, hiddenAreaFor } from "@/lib/lms/nav";
import { isStaffCourse, type CourseOut } from "@/lib/lms/types";
import { CourseContext } from "@/components/lms/CourseContext";
import { StatusBadge } from "@/components/lms/course/CourseCard";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StaffCourseBar } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { useDeclareArea, useDeclareStudentCourse } from "@/components/lms/LmsShell"; // Phase 6b integration; Student UI U2
import { templateUi } from "@/lib/lms/templates"; // Student UI U2
// --- Phase 8c S1 begin --- (course sidebar, Student view, hidden areas: PHASE_8C_DESIGN §2, §6)
import { CourseSidebar } from "@/components/lms/course/CourseSidebar";
import { AreaUnavailable } from "@/components/lms/course/AreaUnavailable";
// --- Phase 8c S1 end ---
// --- Phase 6 S6b begin --- (student course frame, skeleton)
import { CourseLoadingSkeleton, StudentCourseHeader } from "@/components/lms/home/StudentCourseFrame";
// --- Phase 6 S6b end ---

export default function CourseLayout({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const params = useParams<{ courseId: string }>();
  const pathname = usePathname() || "";
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
  }, [reload, courseId]);

  // Phase 6b integration: course pages are Teaching for staff and Learning for students (header area switcher).
  // Phase 8c S1 (§2.5): inside a course the Teaching sub-menu is hidden; the sidebar is the course's navigation.
  // Phase 9 UX: the server's staff serializer decides (org admins reading a course of their organization get it too).
  const staffRole = !!course && isStaffCourse(course);
  useDeclareArea(course ? (staffRole ? "teaching" : "learning") : null, { hideSections: true });
  useDeclareStudentCourse(course); // Student UI U2: the student shell's links for this course

  // Phase 11 S3 (invariant 1): the gate refuses the course but never an open attempt; the player needs no course frame
  if ((error as { code?: string } | null)?.code === "consent_required" && /\/attempts\/[^/]+$/.test(pathname)) return <>{children}</>;

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
  // --- Phase 6 S6b end ---

  const base = `/${lang}/courses/${course.id}`;
  const ctx = { course, reload, setCourse };
  const role = course.my_enrollment.role;
  const staff = isStaffCourse(course);
  // --- Phase 8b S5: an exam template's sandbox (template preview result pages) has no course frame: its course
  // pages are not part of the product (every course-level write answers 409 `sandbox_course`); the page's own
  // "Back" link (`?return=`) leads to the constructor ---
  if (staff && course.sandbox_for_template_id) {
    return <CourseContext.Provider value={ctx}>{children}</CourseContext.Provider>;
  }
  // --- Phase 8c S1 begin --- (PHASE_8C_DESIGN §2.1, P8C-8: player, result and review pages under /attempts/** keep
  // today's full-width column without the sidebar, so the ORT result and review stay pixel-identical) ---
  const attemptsPage = pathname === `${base}/attempts` || pathname.startsWith(`${base}/attempts/`);
  const staffFrame = staff && (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;
  const header = staffFrame
    ? <StaffCourseBar course={course} titleAsHeading={pathname === base} studentViewButton />
    : role === "student"
      ? <StudentCourseHeader course={course} />
      : (
        // Fallback frame (any other role), unchanged.
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("courses.home.backToList")}</Link>
          <h1 className="text-2xl font-bold text-slate-900">{pickLocalized(course.title, lang, course.default_language)}</h1>
          <StatusBadge status={course.status} />
        </div>
      );
  if (attemptsPage) {
    return (
      <CourseContext.Provider value={ctx}>
        {header}
        {children}
      </CourseContext.Provider>
    );
  }
  // students (and org admins reading the course) opening an area whose link is hidden get the "not available" page
  const hidden = hiddenAreaFor(course, courseNavRole(course), pathname);
  // --- Student UI U2 (STUDENT_UI_DESIGN §2.2): inside an exam-prep course the student shell's sidebar navigates, so
  // the course sidebar is not shown; the assessment lobby keeps today's frame to the pixel (§2.4) ---
  const lobby = /^\/[^/]+\/courses\/[^/]+\/assessments\/[^/]+$/.test(pathname);
  if (!staffFrame && role === "student" && templateUi(course).studentLayout === "exam_prep" && !lobby) {
    // Student UI U4 (§3.2) / U6 (§3.3) / U7 (§3.5): Тесты, Аналитика and the lesson pages have their own title (course
    // name as subtitle); the course page only redirects there
    const ownTitle = pathname === base || pathname === `${base}/tests` || pathname === `${base}/progress`
      || pathname === `${base}/modules` || pathname.startsWith(`${base}/modules/`)
      || pathname === `${base}/saved` || pathname === `${base}/practice`; // U8: Сохранённые, Практика
    return (
      <CourseContext.Provider value={ctx}>
        {ownTitle ? null : <StudentCourseHeader course={course} breadcrumbs={false} />}
        {hidden ? <AreaUnavailable courseId={course.id} /> : children}
      </CourseContext.Provider>
    );
  }
  return (
    <CourseContext.Provider value={ctx}>
      {header}
      <CourseSidebar course={course}>
        {hidden ? <AreaUnavailable courseId={course.id} /> : children}
      </CourseSidebar>
    </CourseContext.Provider>
  );
  // --- Phase 8c S1 end ---
}
