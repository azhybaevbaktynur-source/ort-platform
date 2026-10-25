"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { ImportPanel } from "@/components/lms/content/import/ImportPanel";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { PageHeader } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";

export default function BankImportPage() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const crumbs = useTabCrumbs("bank", [{ label: t("bank.import.title") }], course.id);
  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={t("bank.import.title")} className="mb-2" />
      {canEdit ? (
        <ImportPanel />
      ) : (
        <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("bank.concluded")}</p>
      )}
    </div>
  );
}
