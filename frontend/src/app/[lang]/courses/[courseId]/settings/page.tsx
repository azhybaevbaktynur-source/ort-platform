"use client";

/*
 * FB8-5 S3 (STAFF_UX_AUDIT 5, D-FB8-5-3): course settings in six sections, one per `?section=` link (deep-linkable):
 * General (default), Cover, Enrollment, Access / Pro, Grading, Danger zone. Each section is its own component in
 * `components/lms/course/settings/` and keeps its own Save (one sticky save bar stays deferred, UX T28). Cover is
 * hidden from the non-admin staff of a platform course (the server refuses them: 403 platform_course_admin_only),
 * Danger zone from everyone but the owner. An unknown or hidden section shows General. Fix round 2026-11-12 (1d): Access
 * / Pro only for a platform admin on a platform course (from `useLmsMe`, the DB-backed answer); the course status card
 * lives at the top of General for every teacher.
 */
import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse, type CourseStaffOut } from "@/lib/lms/types";
import { useAuth } from "@/lib/auth-context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCourse } from "@/components/lms/CourseContext";
import { CourseGradingSection } from "@/components/lms/grading/settings/CourseGradingSection";
import { GeneralSection } from "@/components/lms/course/settings/GeneralSection";
import { CoverSettingsSection } from "@/components/lms/course/settings/CoverSettingsSection";
import { EnrollmentSection } from "@/components/lms/course/settings/EnrollmentSection";
import { AccessSection } from "@/components/lms/course/settings/AccessSection";
import { DangerSection } from "@/components/lms/course/settings/DangerSection";
import { SETTINGS_SECTIONS, SectionLayout, type SettingsSection } from "@/components/lms/course/settings/shared";
import { PageHeader, TabsNav } from "@/components/ui";

function Settings({ course }: { course: CourseStaffOut }) {
  const { lang, t } = useTranslation();
  const { setCourse } = useCourse();
  const { userProfile } = useAuth();
  const { me } = useLmsMe();
  const params = useSearchParams();
  const base = `/${lang}/courses/${course.id}/settings`;

  const visible = SETTINGS_SECTIONS.filter((s) =>
    s === "cover" ? !course.is_platform_course || !!userProfile?.is_platform_admin
      : s === "access" ? course.is_platform_course && !!me?.is_platform_admin
        : s === "danger" ? course.is_owner : true);
  const asked = params.get("section") as SettingsSection | null;
  const section: SettingsSection = asked && visible.includes(asked) ? asked : "general";
  // The API returns CourseStaffOut for every course mutation; keep the shared context in sync.
  const apply = (c: CourseStaffOut) => setCourse(c);
  const courseName = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");

  return (
    <div className="w-full">
      <PageHeader title={t("courses.settings.pageTitle")} description={courseName} className="mb-3" />
      <TabsNav label={t("courses.settings.sectionsLabel")} className="mb-6 border-b border-slate-200"
        items={visible.map((s) => ({
          href: s === "general" ? base : `${base}?section=${s}`,
          label: t(`courses.settings.sections.${s}`),
          active: s === section,
        }))} />
      {/* key: a section opened again starts from the saved course */}
      <div key={section}>
        {section === "general" && <GeneralSection course={course} onSaved={apply} />}
        {section === "cover" && <CoverSettingsSection course={course} onSaved={apply} />}
        {section === "enrollment" && <EnrollmentSection course={course} onSaved={apply} />}
        {section === "access" && <AccessSection course={course} onSaved={apply} />}
        {section === "grading" && (
          <SectionLayout>
            <CourseGradingSection courseId={course.id} languages={course.languages} defaultLanguage={course.default_language} />
          </SectionLayout>
        )}
        {section === "danger" && <DangerSection course={course} onSaved={apply} />}
      </div>
    </div>
  );
}

function SettingsGate() {
  const { course } = useCourse();
  const { t } = useTranslation();
  if (!isStaffCourse(course) || course.my_enrollment.role !== "teacher") {
    return <p className="text-sm text-slate-600">{t("lms.errors.forbidden")}</p>;
  }
  // key resets the form state when the course id changes
  return <Settings key={course.id} course={course} />;
}

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsGate />
    </Suspense>
  );
}
