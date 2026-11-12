"use client";

// FB8-5 S4 (STAFF_UX_AUDIT §6): what the admin should look at now. Each row shows only when it applies; with none,
// one line says everything is fine.
import React from "react";
import Link from "next/link";
import { CheckCircle2, ChevronRight, HardDrive, KeyRound, ShieldAlert, UserCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { Badge, Card, ErrorState, Skeleton, cn, focusRing } from "@/components/ui";

export interface AttentionInput {
  /** Pending teacher requests (the shell's live summary); null while loading. */
  pending: number | null;
  storageLevel: "ok" | "warn" | "full" | null;
  reveals: { count: number; alert: boolean } | null;
  /** Failed health checks; null while the check runs or when it failed to answer. */
  failedChecks: number | null;
  /** FIX_ROUND_2026-11-12 1a: the shell's summary failed (after its retries); only this card shows it, with a retry. */
  summaryError?: { code?: string } | null;
  onRetry?: () => void;
}

interface Row {
  id: string;
  icon: React.ReactNode;
  text: string;
  href: string;
  badge: React.ReactNode;
}

export function NeedsAttention({ pending, storageLevel, reveals, failedChecks, summaryError, onRetry }: AttentionInput) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/admin`;
  const rows: Row[] = [];
  if (pending && pending > 0) {
    rows.push({ id: "requests", icon: <UserCheck />, text: t("platformAdmin.overview.pendingRequests"),
      href: `${base}/teacher-requests`, badge: <Badge tone="info">{pending}</Badge> });
  }
  if (storageLevel && storageLevel !== "ok") {
    rows.push({ id: "storage", icon: <HardDrive />, text: t(`platformAdmin.overview.attention.storage.${storageLevel}`),
      href: `${base}/storage`, badge: <Badge tone={storageLevel === "full" ? "danger" : "warning"}>{t(`storage.level.${storageLevel}`)}</Badge> });
  }
  if (reveals?.alert) {
    rows.push({ id: "reveals", icon: <KeyRound />, text: t("platformAdmin.overview.attention.reveals"),
      href: `${base}/access/vouchers`, badge: <Badge tone="danger">{reveals.count}</Badge> });
  }
  if (failedChecks && failedChecks > 0) {
    rows.push({ id: "health", icon: <ShieldAlert />, text: t("platformAdmin.overview.attention.health"),
      href: `${base}/health`, badge: <Badge tone="danger">{failedChecks}</Badge> });
  }
  const loaded = pending !== null || storageLevel !== null;
  const failed = !loaded && !!summaryError; // a value loaded before stays shown
  return (
    <Card title={t("platformAdmin.overview.attention.title")} headingLevel={2} data-testid="needs-attention">
      {failed && <ErrorState variant="inline" message={t(lmsErrorKey(summaryError?.code))} onRetry={onRetry}
        className={rows.length > 0 ? "mb-3" : undefined} />}
      {failed && rows.length === 0 ? null : !loaded && !failed ? <Skeleton className="h-6 w-2/3" /> : rows.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-slate-700">
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-success-700" />
          {t("platformAdmin.overview.attention.none")}
        </p>
      ) : (
        <ul className="-my-1 divide-y divide-slate-100">
          {rows.map((r) => (
            <li key={r.id} data-attention={r.id}>
              <Link href={r.href} className={cn("flex min-h-11 items-center gap-3 rounded-lg py-2 text-sm text-slate-800 hover:text-brand-700", focusRing)}>
                <span aria-hidden="true" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700 [&>svg]:h-4 [&>svg]:w-4">{r.icon}</span>
                <span className="min-w-0 flex-1 font-medium">{r.text}</span>
                {r.badge}
                <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
