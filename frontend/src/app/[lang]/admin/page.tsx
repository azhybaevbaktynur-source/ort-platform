"use client";

// FB8-5 S4 (STAFF_UX_AUDIT §6): metrics row, "Needs attention", quick actions, the health status line (full card on
// /admin/health) and the recent exams card.
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Plus, UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getPlatformOverview, type PlatformOverviewOut } from "@/lib/lms/admin";
import type { LmsApiError } from "@/lib/lms/client";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { MetricsRow } from "@/components/lms/admin/MetricsRow";
import { NeedsAttention } from "@/components/lms/admin/NeedsAttention";
import { HealthLine, failedHealthChecks, usePlatformHealth } from "@/components/lms/admin/HealthLine";
import { RecentExamsCard, useAccessOverview } from "@/components/lms/access/AdminAccessUi";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { ErrorState, LinkButton, PageHeader, STAFF_WIDTH, cn } from "@/components/ui";

function useOverview(enabled: boolean) {
  const [data, setData] = useState<PlatformOverviewOut | null>(null);
  const [error, setError] = useState<LmsApiError | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { setData(await getPlatformOverview()); } catch (e) { setError(e as LmsApiError); }
  }, []);
  useEffect(() => { if (enabled) void load(); }, [enabled, load]);
  return { data, error, reload: load };
}

export default function AdminOverviewPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { pending, storageLevel, error, refresh } = useAdminSummary();
  const base = `/${lang}/admin`;
  // S3: the other calls go out only once the summary answered, so an admin who must set up two-step login sends no
  // extra refused calls
  const ready = !error && pending !== null;
  const overview = useOverview(ready);
  const { data: access } = useAccessOverview(ready);
  const { health, failed } = usePlatformHealth(ready);

  return (
    <div className={cn("w-full", STAFF_WIDTH.list)}>
      <PageHeader title={t("platformAdmin.overview.title")}
        overflow={[{ id: "main", items: [
          { id: "health", label: t("platformAdmin.overview.menu.health") },
          { id: "audit", label: t("platformAdmin.overview.menu.auditLog") },
        ] }]}
        onOverflow={(id) => router.push(id === "health" ? `${base}/health` : `${base}/audit-log`)} />
      {error && pending === null
        ? <ErrorState variant="inline" message={t(lmsErrorKey(error.code))} onRetry={refresh} />
        : (
          <div className="space-y-4">
            <MetricsRow data={overview.data} error={overview.error} onRetry={() => void overview.reload()} />
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <NeedsAttention pending={pending} storageLevel={storageLevel}
                reveals={overview.data ? { count: overview.data.reveals_last_hour, alert: overview.data.reveal_alert } : null}
                failedChecks={health ? failedHealthChecks(health) : null} />
              <section aria-labelledby="quick-actions-title" className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
                <h2 id="quick-actions-title" className="text-base font-semibold text-slate-900">{t("platformAdmin.overview.quick.title")}</h2>
                <div className="mt-3 flex flex-wrap gap-2 lg:flex-col lg:items-stretch">
                  <LinkButton href={`/${lang}/courses/new`} variant="secondary" size="sm" leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>
                    {t("platformAdmin.overview.quick.newCourse")}
                  </LinkButton>
                  <LinkButton href={`${base}/access`} variant="secondary" size="sm" leftIcon={<UserPlus aria-hidden="true" className="h-4 w-4" />}>
                    {t("platformAdmin.overview.quick.grantPro")}
                  </LinkButton>
                  <LinkButton href={`${base}/access/vouchers`} variant="secondary" size="sm" leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />}>
                    {t("platformAdmin.overview.quick.codes")}
                  </LinkButton>
                </div>
              </section>
            </div>
            {ready && <HealthLine health={health} failed={failed} />}
            {ready && <RecentExamsCard data={access} compact />}
          </div>
        )}
    </div>
  );
}
