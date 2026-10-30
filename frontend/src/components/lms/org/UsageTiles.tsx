"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getOrgUsage, type DepartmentUsageOut, type TreeUsageOut } from "@/lib/lms/organizations";
import { Card, LoadingState, Table, type TableColumn } from "@/components/ui";
import { OrgError } from "./OrgUi";

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.3): the "By department" card of the organization overview (GET /org/{id}/usage).
 * Hidden when the organization has no departments; a table on desktop, stacked rows at 375 px (`Table`).
 */
export function UsageByDepartment({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const [usage, setUsage] = useState<TreeUsageOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setUsage(await getOrgUsage(orgId));
    } catch (e) {
      setError(e);
    }
  }, [orgId]);
  useEffect(() => { void load(); }, [load]);

  if (usage && usage.by_department.length === 0) return null;
  const columns: TableColumn<DepartmentUsageOut>[] = [
    { key: "name", header: t("departments.usageDepartment"), primary: true, cell: (d) => <span className="break-words font-medium">{d.name}</span> },
    { key: "courses", header: t("organizations.counts.courses"), cell: (d) => d.courses },
    { key: "teachers", header: t("organizations.counts.teachers"), cell: (d) => d.teachers },
    { key: "students", header: t("organizations.counts.students"), cell: (d) => d.students },
  ];
  return (
    <Card title={t("departments.usageTitle")} padding={usage ? "none" : "md"} className="mb-6">
      {error ? <OrgError error={error} onRetry={load} /> : !usage ? <LoadingState label={t("lms.common.loading")} rows={1} /> : (
        <Table columns={columns} rows={usage.by_department} rowKey={(d) => d.id} caption={t("departments.usageTitle")} />
      )}
    </Card>
  );
}
