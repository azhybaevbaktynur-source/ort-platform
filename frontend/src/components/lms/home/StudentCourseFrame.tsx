"use client";

// Phase 6b S6b: the frame of a course for a student: title with breadcrumbs (no teacher states such as
// "Published" or "My role", UX S3/S5) and one scrollable tab row (UX S12). The people tab is called
// "Teachers" for students, since it lists only the course staff (UX S14).
import React from "react";
import { usePathname } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { PageHeader, Skeleton, TabsNav } from "@/components/ui";

export function StudentCourseTabs({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const features = course.features; // Phase 8a S4a
  const pathname = usePathname();
  const base = `/${lang}/courses/${courseId}`;
  // --- Phase 7a S5: "Assignments" replaces the "Assessments" entry (the lobby URLs under /assessments stay and keep it active) ---
  // --- Phase 8a S4a: Modules / Files / Announcements only when the course has published content of that kind
  // (`features`, PHASE_8A_DESIGN 8.2), so a course without structure (every ORT course today) keeps its tab row ---
  // Phase 8a UX: pages (opened from modules) keep "Modules" active; the course home page (home_kind = page) keeps "Home".
  const onHomePage = course.home_kind === "page" && !!course.home_page_id && pathname === `${base}/pages/${course.home_page_id}`;
  const tabs: { href: string; label: string; exact?: boolean; also?: string; force?: boolean; never?: boolean }[] = [
    { href: base, label: t("courses.home.tab"), exact: true, force: onHomePage },
    ...(features?.modules ? [{ href: `${base}/modules`, label: t("modules.tab"), also: `${base}/pages`, never: onHomePage }] : []),
    { href: `${base}/assignments`, label: t("assignments.tab"), also: `${base}/assessments` },
    ...(features?.files ? [{ href: `${base}/files`, label: t("courseFiles.title") }] : []),
    ...(features?.announcements ? [{ href: `${base}/announcements`, label: t("announcements.title") }] : []),
    { href: `${base}/grades`, label: t("gradebook.tab") },
    { href: `${base}/people`, label: t("courses.people.tabStudent") },
  ];
  return (
    <TabsNav label={t("courses.home.tabsLabel")} className="mb-6"
      items={tabs.map((tab) => ({
        href: tab.href, label: tab.label,
        active: !!tab.force || (!tab.never && (tab.exact ? pathname === tab.href : pathname.startsWith(tab.href) || (!!tab.also && pathname.startsWith(tab.also)))),
      }))} />
  );
  // --- Phase 7a S5 end ---
}

export function StudentCourseHeader({ course }: { course: CourseOut }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  return (
    <PageHeader title={title} className="mb-4"
      breadcrumbs={[{ label: t("lms.nav.myCourses"), href: `/${lang}/courses` }, { label: title }]} />
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
