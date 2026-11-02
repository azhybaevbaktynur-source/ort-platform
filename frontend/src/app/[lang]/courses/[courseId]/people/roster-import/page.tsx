"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { RosterImportWizard } from "@/components/lms/org/RosterImportWizard";
import { EmptyState, LinkButton, PageHeader } from "@/components/ui";

/** Accounts (docs/phases/ACCOUNTS.md D): the organization's roster import, for this course's students. The org routes decide. */
export default function CourseRosterImportPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const title = t("rosterImport.title");
  const breadcrumbs = useTabCrumbs("people", [{ label: title }], course.id);
  const people = `/${lang}/courses/${course.id}/people`;
  if (!isStaffCourse(course) || !course.can_import_roster || !course.organization_id) {
    return (
      <EmptyState title={t("rosterImport.notAvailable")}
        action={<LinkButton variant="secondary" href={people}>{t("courses.people.tab")}</LinkButton>} />
    );
  }
  return (
    <div>
      <PageHeader title={title} breadcrumbs={breadcrumbs} />
      <RosterImportWizard orgId={course.organization_id} course={{ id: course.id, title: pickLocalized(course.title, lang, course.default_language) }} />
    </div>
  );
}
