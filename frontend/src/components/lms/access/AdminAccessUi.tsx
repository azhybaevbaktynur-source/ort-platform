"use client";

// S3 access, platform admin: the attention block (exams published in the last 14 days with
// their tier, and the alert after more than 20 codes shown in an hour). Used by /admin/access and the overview.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDate } from "@/lib/format";
import { getAccessOverview, type AccessOverviewOut, type AccessTier, type BatchOut } from "@/lib/lms/access";
import type { LmsApiError } from "@/lib/lms/client";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { Badge, Card, ErrorState, Skeleton, cn, focusRing } from "@/components/ui";

export function TierBadge({ tier }: { tier: AccessTier }) {
  const { t } = useTranslation();
  return <Badge tone={tier === "paid" ? "warning" : "neutral"}>{t(tier === "paid" ? "access.paid" : "access.free")}</Badge>;
}

export function useAccessOverview(enabled = true) {
  const [data, setData] = useState<AccessOverviewOut | null>(null);
  // FIX_ROUND_2026-11-12 1a: the failure is kept (an inline error with a retry, not an endless skeleton) and never
  // clears an answer already loaded
  const [error, setError] = useState<LmsApiError | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { setData(await getAccessOverview()); } catch (e) { setError(e as LmsApiError); }
  }, []);
  useEffect(() => { if (enabled) void load(); }, [enabled, load]);
  return { data, error, reload: load };
}

export function RevealAlert({ count, className }: { count: number; className?: string }) {
  const { lang, t } = useTranslation();
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-2xl border border-danger-200 bg-danger-50 p-4 text-sm leading-5 text-danger-900", className)}>
      <AlertTriangle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
      <p>
        {t("access.admin.revealAlert", { count })}{" "}
        <Link href={`/${lang}/admin/audit-log`} className={cn("font-semibold underline", focusRing)}>{t("platformAdmin.nav.auditLog")}</Link>
      </p>
    </div>
  );
}

/** Exams of platform courses published in the last 14 days, with their tier (design 7.7). */
export function RecentExamsCard({ data, error, onRetry, compact = false, className }: {
  data: AccessOverviewOut | null; error?: { code?: string } | null; onRetry?: () => void; compact?: boolean; className?: string;
}) {
  const { lang, t } = useTranslation();
  const manage = `/${lang}/admin/access/exams`;
  return (
    <Card className={className} data-testid="recent-exams" title={t("access.admin.recent.title")} description={t("access.admin.recent.hint")}
      actions={compact ? <Link href={manage} className={cn("inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>{t("access.admin.recent.manage")}</Link> : undefined}>
      {!data && error ? <ErrorState variant="inline" message={t(lmsErrorKey(error.code))} onRetry={onRetry} />
        : !data ? <Skeleton className="h-6 w-2/3" /> : data.recent_exams.length === 0 ? (
        <p className="text-sm text-slate-600">{t("access.admin.recent.empty")}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.recent_exams.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5">
              <span className="min-w-0">
                <span className="block break-words font-medium text-slate-900">{pickLocalized(e.title, lang) || t("assessments.untitled")}</span>
                <span className="block text-sm text-slate-600">{pickLocalized(e.course_title, lang)} · {fmtApiDate(e.published_at, lang)}</span>
              </span>
              <TierBadge tier={e.access_tier} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** "30 days" or "until 31/05/2027" (the end date is the last day, Bishkek time). */
export function batchLength(b: Pick<BatchOut, "duration_days" | "ends_on">, t: (k: string, v?: Record<string, string | number>) => string, lang: string): string {
  if (b.duration_days) return t("access.admin.batches.lengthDaysValue", { count: b.duration_days });
  return b.ends_on ? t("access.admin.batches.lengthUntil", { date: fmtApiDate(b.ends_on, lang) }) : "";
}
