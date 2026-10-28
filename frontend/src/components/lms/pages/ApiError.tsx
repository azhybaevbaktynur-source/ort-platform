"use client";

// Phase 8a S4b: error line for pages / course files / announcements. Own codes are translated from
// pages.errors / courseFiles.errors / announcements.errors; everything else falls back to ErrorMessage.
import React from "react";
import Link from "next/link";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import type { LockReason, ModuleLockedDetails } from "@/lib/lms/pagesTypes";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { buttonClasses } from "@/components/ui";

const GROUPS = ["pages", "courseFiles", "announcements"] as const;

export function useContentErrorText() {
  const { t } = useTranslation();
  return (e: unknown): string | null => {
    const code = (e as { code?: string } | null)?.code;
    if (!code) return null;
    for (const g of GROUPS) {
      const key = `${g}.errors.${code}`;
      const text = t(key, ((e as { details?: Record<string, unknown> }).details ?? {}) as Record<string, string | number>);
      if (text !== key) return text;
    }
    return null;
  };
}

/** Error box; shows the module-locked state for 423 instead when `locked` is a LockedState host. */
export function ContentError({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const text = useContentErrorText()(error);
  if (!error) return null;
  if (!text) return <ErrorMessage error={error} onRetry={onRetry} className={className} />;
  return (
    <div role="alert" className={`rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className ?? ""}`}>
      {text}
    </div>
  );
}

export function isModuleLocked(e: unknown): boolean {
  const x = e as { status?: number; code?: string } | null;
  return !!x && (x.status === 423 || x.code === "module_locked");
}

function useReasonText() {
  const { lang, t } = useTranslation();
  return (r: LockReason): string => {
    const title = pickLocalized(r.title ?? null, lang as Lang);
    if (r.kind === "unlock_at") return t("pages.locked.reasonUnlockAt", { date: fmtShortDateTime(r.at, lang) });
    if (r.kind === "prerequisite") return t("pages.locked.reasonPrerequisite", { title: title || t("pages.locked.aModule") });
    if (r.kind === "sequential") return t("pages.locked.reasonSequential", { title: title || t("pages.locked.anItem") });
    return t("pages.locked.reasonOther");
  };
}

/** 423 `module_locked`: friendly state with the reasons and a way back to Modules. */
export function LockedState({ error, courseId, compact = false }: { error: unknown; courseId: string; compact?: boolean }) {
  const { lang, t } = useTranslation();
  const reasonText = useReasonText();
  const d = ((error as { details?: ModuleLockedDetails } | null)?.details ?? {}) as ModuleLockedDetails;
  const reasons = d.reasons ?? d.lock_reasons ?? [];
  const moduleTitle = pickLocalized(d.module_title ?? null, lang as Lang);
  return (
    <div role="status" className={`rounded-2xl border border-slate-200 bg-slate-50 p-5 text-center ${compact ? "" : "mx-auto max-w-xl sm:p-8"}`}>
      <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-slate-200 text-slate-700">
        <Lock className="h-5 w-5" aria-hidden="true" />
      </span>
      <h2 className="text-lg font-semibold text-slate-900">{t("pages.locked.title")}</h2>
      <p className="mt-1 text-sm text-slate-600">
        {moduleTitle ? t("pages.locked.bodyModule", { title: moduleTitle }) : t("pages.locked.body")}
      </p>
      {reasons.length > 0 && (
        <ul className="mx-auto mt-3 max-w-sm space-y-1 text-left text-sm text-slate-800">
          {reasons.map((r, i) => (
            <li key={i} className="flex gap-2"><span aria-hidden="true">•</span><span className="min-w-0 break-words">{reasonText(r)}</span></li>
          ))}
        </ul>
      )}
      <Link href={`/${lang}/courses/${courseId}/modules`} className={`${buttonClasses({ variant: "primary" })} mt-4`}>
        {t("pages.locked.toModules")}
      </Link>
    </div>
  );
}
