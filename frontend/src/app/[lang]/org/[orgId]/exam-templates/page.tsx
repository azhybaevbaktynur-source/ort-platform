"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useOrg } from "@/components/lms/org/OrgShell";
import { ExamTemplatesPage } from "@/components/lms/examTemplates/ExamTemplatesPage";

export default function OrgExamTemplatesPage() {
  const { t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
  return (
    <ExamTemplatesPage area={{ kind: "org", orgId: org.id, readOnly }}
      breadcrumbs={crumbs({ label: t("examTemplates.nav.title") })} />
  );
}
