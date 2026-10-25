"use client";

import React from "react";
import { AlertCircle, ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

/**
 * Error box for Phase 6 endpoints: codes with a text in `organizations.errors.*` are shown with it,
 * everything else falls back to the shared `ErrorMessage` (lms.errors.*).
 */
export function OrgError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string }).code;
  const key = code ? `organizations.errors.${code}` : "";
  const text = key ? t(key) : key;
  if (!code || text === key) return <ErrorMessage error={error} onRetry={onRetry} className={className} />;
  return (
    <div role="alert" className={`flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <p className="flex-1">{text}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-semibold underline">{t("lms.common.retry")}</button>
      )}
    </div>
  );
}

const BADGE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  suspended: "bg-amber-100 text-amber-900",
  invited: "bg-sky-100 text-sky-800",
  pending: "bg-sky-100 text-sky-800",
  accepted: "bg-emerald-100 text-emerald-800",
  revoked: "bg-slate-100 text-slate-700",
  expired: "bg-slate-100 text-slate-700",
  removed: "bg-slate-100 text-slate-700",
  blocked: "bg-red-100 text-red-800",
  granted: "bg-emerald-100 text-emerald-800",
  notGranted: "bg-slate-100 text-slate-700",
};

/** Small status badge; `labelKey` is a full i18n key, `tone` picks the colors. */
export function OrgBadge({ tone, labelKey }: { tone: string; labelKey: string }) {
  const { t } = useTranslation();
  return <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${BADGE[tone] || BADGE.revoked}`}>{t(labelKey)}</span>;
}

/** "System account" badge (admin M5): accounts the platform needs; they cannot be edited. */
export function SystemAccountBadge() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-800" title={t("organizations.admin.systemAccountHint")}>
      <ShieldCheck className="h-3 w-3" aria-hidden="true" />{t("organizations.admin.systemAccount")}
    </span>
  );
}

/** Loading line in the page layout (never a blank page). */
export function Loading() {
  const { t } = useTranslation();
  return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
}

/** Empty state: what this place is for plus an optional next step. */
export function EmptyBox({ text, children }: { text: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-600">
      <p>{text}</p>
      {children ? <div className="mt-3 flex flex-wrap justify-center gap-2">{children}</div> : null}
    </div>
  );
}

/** One number with a label (overview tiles). */
export function StatTile({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

export const btn = {
  primary: "inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50",
  secondary: "inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50",
  danger: "inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50",
  small: "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50",
  smallDanger: "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50",
};
export const inputCls = "w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-50";
export const labelCls = "mb-1 block text-sm font-medium text-slate-700";
export const cardCls = "rounded-2xl border border-slate-200 bg-white p-5";
