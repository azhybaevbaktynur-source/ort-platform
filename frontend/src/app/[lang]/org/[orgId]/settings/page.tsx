"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getOrgSettings, type OrgSettingsViewOut } from "@/lib/lms/organizations";
import { LoadingState, PageHeader } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { OrgSettingsForm } from "@/components/lms/org/OrgSettingsForm";
import { LoadError } from "@/components/lms/org/OrgUi";

/** Phase 9 S2 (PHASE_9_DESIGN 4.3, 8.1): organization settings (root only; departments read them). */
export default function OrgSettingsPage() {
  const { t } = useTranslation();
  const { org, readOnly, crumbs, reload } = useOrg();
  const [view, setView] = useState<OrgSettingsViewOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setView(await getOrgSettings(org.id));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div>
      <PageHeader title={t("orgSettings.title")} description={t("orgSettings.intro")} breadcrumbs={crumbs({ label: t("orgSettings.nav") })} />
      {error && !view ? <LoadError error={error} onRetry={load} /> : !view ? <LoadingState label={t("lms.common.loading")} /> : (
        <OrgSettingsForm view={view} readOnly={readOnly} onSaved={(v) => { setView(v); void reload(); }} />
      )}
    </div>
  );
}
