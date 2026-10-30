"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { PageHeader } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { RosterImportWizard } from "@/components/lms/org/RosterImportWizard";
import { listDepartments } from "@/lib/lms/organizations";

/** Phase 9 (PHASE_9_DESIGN 4.4, 8.1): roster import in the org area; teacher imports may target a department of the subtree. */
export default function OrgRosterImportPage() {
  const { t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    let alive = true;
    // The list starts with the organization itself; the wizard offers it as its default ("this organization").
    listDepartments(org.id)
      .then((rows) => { if (alive) setDepartments(rows.filter((d) => d.id !== org.id).map((d) => ({ id: d.id, name: d.name }))); })
      .catch(() => { if (alive) setDepartments([]); });
    return () => { alive = false; };
  }, [org.id]);
  return (
    <div>
      <PageHeader title={t("organizations.org.rosterImport")} breadcrumbs={crumbs({ label: t("organizations.org.rosterImport") })} />
      <RosterImportWizard orgId={org.id} readOnly={readOnly} departments={departments} />
    </div>
  );
}
