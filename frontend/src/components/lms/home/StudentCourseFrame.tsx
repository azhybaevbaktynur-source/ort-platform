"use client";

// Phase 6b S6b: the frame of a course for a student: title with breadcrumbs (no teacher states such as
// "Published" or "My role", UX S3/S5). Phase 8c S1: the tab row is replaced by the course sidebar
// (components/lms/course/CourseSidebar.tsx, PHASE_8C_DESIGN §2.1).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse, type CourseOut } from "@/lib/lms/types";
import { PageHeader, Skeleton } from "@/components/ui";

export function StudentCourseHeader({ course }: { course: CourseOut }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  // Phase 9 UX: an org admin reading a course of their organization (no enrollment, staff serializer) goes back to
  // the course's page in the organization area, not to "My courses" (the course is not one of theirs)
  const orgReader = !!course.my_enrollment.read_only && isStaffCourse(course) && !!course.organization_id && !!course.organization_name;
  const parent = orgReader
    ? { label: course.organization_name as string, href: `/${lang}/org/${course.organization_id}/courses/${course.id}` }
    : { label: t("lms.nav.myCourses"), href: `/${lang}/courses` };
  return (
    <PageHeader title={title} className="mb-4" breadcrumbs={[parent, { label: title }]} />
  );
}

/** Loading frame of a course page: header and tabs in place, cards as skeletons (UX S16). */
export function CourseLoadingSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true">
        <Skeleton className="mb-3 h-4 w-32" />
        <Skeleton className="mb-5 h-8 w-2/3 sm:w-1/3" />
        <div className="mb-6 flex gap-4 border-b border-slate-200 pb-3">
          <Skeleton className="h-5 w-16" /><Skeleton className="h-5 w-20" /><Skeleton className="h-5 w-16" />
        </div>
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
              <Skeleton className="mb-3 h-5 w-1/2" />
              <Skeleton className="mb-2 h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
