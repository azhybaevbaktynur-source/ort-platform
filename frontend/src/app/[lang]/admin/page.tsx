"use client";

import React from "react";
import Link from "next/link";
import { HardDrive, UserCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { StorageLevelBanner } from "@/components/lms/admin/StorageLevelBanner";
import { HealthCard } from "@/components/lms/admin/HealthCard";
import { RecentExamsCard, RevealAlert, useAccessOverview } from "@/components/lms/access/AdminAccessUi";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { ErrorState, PageHeader, Skeleton, StatTile, cn, focusRing } from "@/components/ui";

/** S3 access (design 7.6, 7.7): the reveal alert and the exams published in the last 14 days with their tier. */
function AccessAttention() {
  const { data } = useAccessOverview();
  return (
    <div className="mt-6 space-y-4">
      {data?.reveal_alert && <RevealAlert count={data.reveals_last_hour} />}
      <RecentExamsCard data={data} compact />
    </div>
  );
}

export default function AdminOverviewPage() {
  const { lang, t } = useTranslation();
  const { pending, storageLevel, error, refresh } = useAdminSummary();
  const base = `/${lang}/admin`;
  const waiting = <Skeleton className="mt-1 h-7 w-16" />;
  return (
    <div>
      <PageHeader title={t("platformAdmin.overview.title")} />
      <StorageLevelBanner level={storageLevel ?? "ok"} className="mb-6">
        <Link href={`${base}/storage`} className={cn("mt-1 inline-flex min-h-11 items-center font-semibold underline", focusRing)}>{t("storage.banner.open")}</Link>
      </StorageLevelBanner>
      {error && pending === null
        ? <ErrorState variant="inline" message={t(lmsErrorKey(error.code))} onRetry={refresh} />
        : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile href={`${base}/teacher-requests`} icon={<UserCheck />} label={t("platformAdmin.overview.pendingRequests")} value={pending ?? waiting} />
            <StatTile href={`${base}/storage`} icon={<HardDrive />} label={t("storage.nav")}
              value={storageLevel ? t(`storage.level.${storageLevel}`) : waiting} />
          </div>
        )}
      {/* S3: only once the summary answered, so an admin who must set up two-step login sends no extra refused call */}
      {!error && pending !== null && <AccessAttention />}
      {!error && <HealthCard />}
    </div>
  );
}
