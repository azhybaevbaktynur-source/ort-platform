"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { PageHeader } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { RosterImportSlot } from "@/components/lms/org/RosterImportSlot";

/** Phase 9 (PHASE_9_DESIGN 4.4, 8.1): roster import in the org area; the wizard itself is slice S3's. */
export default function OrgRosterImportPage() {
  const { t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
  return (
    <div>
      <PageHeader title={t("organizations.org.rosterImport")} breadcrumbs={crumbs({ label: t("organizations.org.rosterImport") })} />
      <RosterImportSlot orgId={org.id} readOnly={readOnly} />
    </div>
  );
}
