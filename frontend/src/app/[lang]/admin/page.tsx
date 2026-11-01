"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { HardDrive, UserCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { StorageLevelBanner } from "@/components/lms/admin/StorageLevelBanner";
import { getStorageSummary, type StorageLevel } from "@/lib/lms/storage";
import { PageHeader, StatTile, cn, focusRing } from "@/components/ui";

export default function AdminOverviewPage() {
  const { lang, t } = useTranslation();
  const { pending } = useAdminSummary();
  const [storageLevel, setStorageLevel] = useState<StorageLevel | null>(null);
  useEffect(() => { getStorageSummary().then((s) => setStorageLevel(s.level)).catch(() => setStorageLevel(null)); }, []);
  const base = `/${lang}/admin`;
  return (
    <div>
      <PageHeader title={t("platformAdmin.overview.title")} />
      <StorageLevelBanner level={storageLevel ?? "ok"} className="mb-6">
        <Link href={`${base}/storage`} className={cn("mt-1 inline-flex min-h-11 items-center font-semibold underline", focusRing)}>{t("storage.banner.open")}</Link>
      </StorageLevelBanner>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile href={`${base}/teacher-requests`} icon={<UserCheck />} label={t("platformAdmin.overview.pendingRequests")} value={pending ?? "—"} />
        <StatTile href={`${base}/storage`} icon={<HardDrive />} label={t("storage.totals.level")}
          value={storageLevel ? t(`storage.level.${storageLevel}`) : "—"} />
      </div>
    </div>
  );
}
