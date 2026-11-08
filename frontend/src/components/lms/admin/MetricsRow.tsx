"use client";

// FB8-5 S4 (STAFF_UX_AUDIT §6): the admin overview's metrics row, from `GET /platform/overview` (D-FB8-5-4).
import React from "react";
import { ClipboardCheck, Crown, GraduationCap, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { PlatformOverviewOut } from "@/lib/lms/admin";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { ErrorState, Skeleton, StatTile } from "@/components/ui";

export function MetricsRow({ data, error, onRetry }: {
  data: PlatformOverviewOut | null; error: { code?: string } | null; onRetry: () => void;
}) {
  const { lang, t } = useTranslation();
  if (error && !data) return <ErrorState variant="inline" message={t(lmsErrorKey(error.code))} onRetry={onRetry} />;
  const base = `/${lang}/admin`;
  const fmt = (n: number | undefined) => (n === undefined ? <Skeleton className="mt-1 h-6 w-12" /> : n.toLocaleString(lang === "en" ? "en-US" : "ru-RU"));
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="overview-metrics">
      <StatTile size="sm" href={`${base}/users`} icon={<Users />} label={t("platformAdmin.overview.metrics.users")} value={fmt(data?.users_total)} />
      <StatTile size="sm" icon={<GraduationCap />} label={t("platformAdmin.overview.metrics.activeStudents")} value={fmt(data?.active_students_7d)} />
      <StatTile size="sm" href={`${base}/access`} icon={<Crown />} label={t("platformAdmin.overview.metrics.pro")} value={fmt(data?.pro_active)} />
      <StatTile size="sm" icon={<ClipboardCheck />} label={t("platformAdmin.overview.metrics.tests")} value={fmt(data?.attempts_submitted_7d)} />
    </div>
  );
}
