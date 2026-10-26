"use client";

import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { ExamTemplateEditor } from "@/components/lms/examTemplates/ExamTemplateEditor";

export default function MyExamTemplatePage() {
  const { lang, t } = useTranslation();
  const { templateId } = useParams<{ templateId: string }>();
  const crumbs = (title?: string) => [
    { label: t("examTemplates.list.pageTitle"), href: `/${lang}/exam-templates` },
    ...(title ? [{ label: title }] : []),
  ];
  return <ExamTemplateEditor key={templateId} area={{ kind: "teacher" }} templateId={templateId} crumbs={crumbs} />;
}
