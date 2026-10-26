"use client";

import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useOrg } from "@/components/lms/org/OrgShell";
import { ExamTemplateEditor } from "@/components/lms/examTemplates/ExamTemplateEditor";

export default function OrgExamTemplatePage() {
  const { lang, t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
  const { templateId } = useParams<{ templateId: string }>();
  const crumbsFor = (title?: string) => crumbs(
    { label: t("examTemplates.nav.title"), href: `/${lang}/org/${org.id}/exam-templates` },
    ...(title ? [{ label: title }] : []),
  );
  return <ExamTemplateEditor key={templateId} area={{ kind: "org", orgId: org.id, readOnly }} templateId={templateId} crumbs={crumbsFor} />;
}
