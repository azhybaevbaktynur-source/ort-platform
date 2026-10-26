"use client";

import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { ExamTemplateEditor } from "@/components/lms/examTemplates/ExamTemplateEditor";

export default function AdminExamTemplatePage() {
  const { lang, t } = useTranslation();
  const adminCrumbs = useAdminCrumbs();
  const { templateId } = useParams<{ templateId: string }>();
  const crumbs = (title?: string) => adminCrumbs(
    { label: t("examTemplates.nav.title"), href: `/${lang}/admin/exam-templates` },
    ...(title ? [{ label: title }] : []),
  );
  return <ExamTemplateEditor key={templateId} area={{ kind: "platform" }} templateId={templateId} crumbs={crumbs} />;
}
