"use client";

// FB8-5 S4 (STAFF_UX_AUDIT §6, D-FB8-5-5): the full system health card, moved off the overview (which keeps one line).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminCrumbs, useAdminSummary } from "@/components/lms/admin/AdminShell";
import { HealthCard } from "@/components/lms/admin/HealthCard";
import { PageHeader, STAFF_WIDTH, cn } from "@/components/ui";

export default function AdminHealthPage() {
  const { t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const { error } = useAdminSummary();
  return (
    <div className={cn("w-full", STAFF_WIDTH.list)}>
      <PageHeader breadcrumbs={crumbs({ label: t("adminHealth.page.title") })} title={t("adminHealth.page.title")}
        description={t("adminHealth.description")} />
      {/* only once the shell's summary did not refuse: an admin who must set up two-step login is sent away first */}
      {error?.code !== "mfa_enrollment_required" && <HealthCard heading={false} />}
    </div>
  );
}
