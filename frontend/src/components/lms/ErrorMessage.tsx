"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LMS_ERROR_CODES } from "@/lib/lms/types";

const KNOWN = new Set<string>(LMS_ERROR_CODES);

export function lmsErrorKey(code: string | undefined): string {
  return `lms.errors.${code && KNOWN.has(code) ? code : "unknown"}`;
}

export function ErrorMessage({
  error,
  onRetry,
  className = "",
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  if (!error) return null;
  const e = error as { code?: string; details?: Record<string, unknown> };
  const retry = e.details && typeof e.details.retry_after_seconds === "number" ? e.details.retry_after_seconds : null;
  // --- Phase 6 S4b begin --- (6a error codes have their text in organizations.errors.*)
  const orgKey = `organizations.errors.${e.code}`;
  const orgText = e.code && !KNOWN.has(e.code) ? t(orgKey) : orgKey;
  const text = orgText !== orgKey ? orgText : t(lmsErrorKey(e.code));
  // --- Phase 6 S4b end ---
  return (
    <div role="alert" className={`flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <div className="flex-1">
        <p>{text}</p>
        {retry !== null && <p className="mt-0.5 text-xs">{t("lms.common.retryAfter", { seconds: retry })}</p>}
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-semibold underline">
          {t("lms.common.retry")}
        </button>
      )}
    </div>
  );
}
