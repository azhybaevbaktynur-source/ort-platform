"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getCourse } from "@/lib/lms/courses";
import { isStudentView, setStudentView } from "@/lib/api";
import { pickLocalized } from "@/lib/lms/localized";
import { courseNavRole, hiddenAreaFor } from "@/lib/lms/nav";
import { isStaffCourse, type CourseOut } from "@/lib/lms/types";
import { CourseContext } from "@/components/lms/CourseContext";
import { StatusBadge } from "@/components/lms/CourseCard";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StaffCourseBar } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { useDeclareArea } from "@/components/lms/LmsShell"; // Phase 6b integration
// --- Phase 8c S1 begin --- (course sidebar, Student view, hidden areas: PHASE_8C_DESIGN §2, §6)
import { CourseSidebar } from "@/components/lms/course/CourseSidebar";
import { StudentViewBanner } from "@/components/lms/course/StudentViewBanner";
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
  // Phase 8c S1: the per-tab Student view flag (read after mount; the request header follows the same flag)
  const [viewing, setViewing] = useState(false);

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
    setViewing(isStudentView(courseId));
    void reload();
  }, [reload, courseId]);

  // Phase 8c S1: the server ignores the header for anyone but real course staff (org admins, platform admins,
  // sandbox staff, students): a staff-shaped answer means the mode does not apply here, so the flag is dropped.
  const studentView = viewing && !!course && !isStaffCourse(course);
  useEffect(() => {
    if (viewing && course && isStaffCourse(course)) {
      setStudentView(courseId, false);
      setViewing(false);
    }
  }, [viewing, course, courseId]);

  // Phase 6b integration: course pages are Teaching for staff and Learning for students (header area switcher).
  // Phase 8c S1 (§2.5): inside a course the Teaching sub-menu is hidden; the sidebar is the course's navigation.
  // Phase 9 UX: the server's staff serializer decides (org admins reading a course of their organization get it too).
  const staffRole = studentView || (!!course && isStaffCourse(course));
  useDeclareArea(course ? (staffRole ? "teaching" : "learning") : null, { hideSections: true });

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
  const banner = studentView ? <StudentViewBanner courseId={course.id} /> : null;
  const header = staffFrame
    ? <StaffCourseBar course={course} titleAsHeading={pathname === base} studentViewButton />
    : role === "student" || studentView
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
        {banner}
        {header}
        {children}
      </CourseContext.Provider>
    );
  }
  // students (and org admins reading the course) opening an area whose link is hidden get the "not available" page
  const hidden = hiddenAreaFor(course, courseNavRole(course), pathname);
  return (
    <CourseContext.Provider value={ctx}>
      {banner}
      {header}
      <CourseSidebar course={course}>
        {hidden ? <AreaUnavailable courseId={course.id} /> : children}
      </CourseSidebar>
    </CourseContext.Provider>
  );
  // --- Phase 8c S1 end ---
}
