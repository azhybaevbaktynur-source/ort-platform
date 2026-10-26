"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { ExamTemplatesPage } from "@/components/lms/examTemplates/ExamTemplatesPage";

export default function AdminExamTemplatesPage() {
  const { t } = useTranslation();
  const crumbs = useAdminCrumbs();
  return <ExamTemplatesPage area={{ kind: "platform" }} breadcrumbs={crumbs({ label: t("examTemplates.nav.title") })} />;
}
