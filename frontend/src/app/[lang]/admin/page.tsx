"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, ChevronRight, ClipboardList, GraduationCap, HardDrive, UserCheck, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { StorageLevelBanner } from "@/components/lms/admin/StorageLevelBanner";
import { getStorageSummary, type StorageLevel } from "@/lib/lms/storage";
import { Card, PageHeader, StatTile, cn, focusRing } from "@/components/ui";

export default function AdminOverviewPage() {
  const { lang, t } = useTranslation();
  const { pending } = useAdminSummary();
  const [storageLevel, setStorageLevel] = useState<StorageLevel | null>(null);
  useEffect(() => { getStorageSummary().then((s) => setStorageLevel(s.level)).catch(() => setStorageLevel(null)); }, []);
  const base = `/${lang}/admin`;
  const sections = [
    { href: `${base}/organizations`, label: t("organizations.nav.organizations"), hint: t("platformAdmin.overview.orgsHint"), icon: <Building2 /> },
    { href: `${base}/users`, label: t("platformAdmin.nav.users"), hint: t("platformAdmin.overview.usersHint"), icon: <Users /> },
    { href: `${base}/courses`, label: t("platformAdmin.nav.courses"), hint: t("platformAdmin.overview.coursesHint"), icon: <GraduationCap /> },
    { href: `${base}/audit-log`, label: t("platformAdmin.nav.auditLog"), hint: t("platformAdmin.overview.auditHint"), icon: <ClipboardList /> },
  ];
  return (
    <div>
      <PageHeader title={t("platformAdmin.overview.title")} />
      <StorageLevelBanner level={storageLevel ?? "ok"} className="mb-6">
        <Link href={`${base}/storage`} className={cn("mt-1 inline-flex min-h-11 items-center font-semibold underline", focusRing)}>{t("storage.banner.open")}</Link>
      </StorageLevelBanner>
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <StatTile href={`${base}/teacher-requests`} icon={<UserCheck />} label={t("platformAdmin.overview.pendingRequests")} value={pending ?? "—"} />
        <StatTile href={`${base}/storage`} icon={<HardDrive />} label={t("storage.totals.level")}
          value={storageLevel ? t(`storage.level.${storageLevel}`) : "—"} hint={t("storage.title")} />
      </div>
      <Card padding="none" title={t("platformAdmin.overview.sections")}>
        <ul className="divide-y divide-slate-100 border-t border-slate-100">
          {sections.map((s) => (
            <li key={s.href}>
              <Link href={s.href} className={cn("flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-slate-50 sm:px-6", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}>
                <span aria-hidden="true" className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 [&>svg]:h-5 [&>svg]:w-5">{s.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold leading-6 text-slate-900">{s.label}</span>
                  <span className="block text-sm leading-5 text-slate-600">{s.hint}</span>
                </span>
                <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-500" />
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
