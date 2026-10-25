"use client";

import React from "react";
import { CircleAlert, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { Badge, Button, EmptyState, ErrorState, LoadingState, cn, type BadgeTone } from "@/components/ui";

type T = (key: string, params?: Record<string, string | number>) => string;

/** Text of an API error: Phase 6 codes from `organizations.errors.*`, everything else from `lms.errors.*`. */
export function apiErrorText(t: T, error: unknown): string {
  const e = error as { code?: string; details?: Record<string, unknown> } | null;
  const code = e?.code;
  const orgKey = `organizations.errors.${code}`;
  const orgText = code ? t(orgKey) : orgKey;
  const text = orgText !== orgKey ? orgText : t(lmsErrorKey(code));
  const retry = e?.details && typeof e.details.retry_after_seconds === "number" ? e.details.retry_after_seconds : null;
  return retry !== null ? `${text} ${t("lms.common.retryAfter", { seconds: retry })}` : text;
}

export function useApiErrorText() {
  const { t } = useTranslation();
  return (error: unknown) => apiErrorText(t, error);
}

/**
 * Error box for Phase 6 endpoints (shown inside a form, a dialog or above a list): what happened in plain
 * words, plus Retry when retrying can help.
 */
export function OrgError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <div role="alert" className={cn("flex flex-col gap-3 rounded-xl border border-danger-200 bg-danger-50 px-3.5 py-3 sm:flex-row sm:items-start", className)}>
      <p className="flex min-w-0 flex-1 items-start gap-2 text-sm leading-5 text-danger-800">
        <CircleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        <span className="min-w-0 break-words">{apiErrorText(t, error)}</span>
      </p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} leftIcon={<RefreshCw aria-hidden="true" className="h-4 w-4" />}>
          {t("ui.retry")}
        </Button>
      )}
    </div>
  );
}

/** A whole list or page failed to load: centered `ErrorState` with the specific text and Retry. */
export function LoadError({ error, onRetry, action }: { error: unknown; onRetry?: () => void; action?: React.ReactNode }) {
  const { t } = useTranslation();
  return <ErrorState message={apiErrorText(t, error)} onRetry={onRetry} action={action} />;
}

const TONE: Record<string, BadgeTone> = {
  active: "success",
  suspended: "warning",
  invited: "info",
  pending: "info",
  accepted: "success",
  revoked: "neutral",
  expired: "neutral",
  removed: "neutral",
  blocked: "danger",
  granted: "success",
  notGranted: "neutral",
};

/** Small status badge; `labelKey` is a full i18n key, `tone` is the state name. */
export function OrgBadge({ tone, labelKey }: { tone: string; labelKey: string }) {
  const { t } = useTranslation();
  return <Badge tone={TONE[tone] ?? "neutral"}>{t(labelKey)}</Badge>;
}

const COURSE_TONE: Record<string, BadgeTone> = { draft: "warning", published: "success", concluded: "neutral" };

/** Course status (draft / published / concluded) on the design-system `Badge`. */
export function CourseStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Badge tone={COURSE_TONE[status] ?? "neutral"}>{t(`courses.status.${status}`)}</Badge>;
}

/** "System account" badge (admin M5): accounts the platform needs; they cannot be edited. */
export function SystemAccountBadge() {
  const { t } = useTranslation();
  return (
    <Badge tone="system" icon={<ShieldCheck aria-hidden="true" />} title={t("organizations.admin.systemAccountHint")}>
      {t("organizations.admin.systemAccount")}
    </Badge>
  );
}

/** Loading placeholder in the page layout (never a blank page). */
export function Loading({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation();
  return <LoadingState label={t("lms.common.loading")} rows={rows} />;
}

/** Empty state: what this place is for plus an optional next step. */
export function EmptyBox({ text, description, children }: { text: string; description?: string; children?: React.ReactNode }) {
  return <EmptyState title={text} description={description} action={children} />;
}
