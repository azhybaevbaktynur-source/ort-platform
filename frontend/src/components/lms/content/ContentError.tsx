"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { CONTENT_ERROR_CODES } from "@/lib/lms/contentTypes";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

const CONTENT_KNOWN = new Set<string>(CONTENT_ERROR_CODES);

/** Error box for content endpoints: Phase 2 codes are translated here, everything else falls through to ErrorMessage. */
export function ContentError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string }).code;
  if (code && CONTENT_KNOWN.has(code)) {
    return (
      <div role="alert" className={`flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <p className="flex-1">{t(`lms.errors.${code}`)}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="font-semibold underline">{t("lms.common.retry")}</button>
        )}
      </div>
    );
  }
  return <ErrorMessage error={error} onRetry={onRetry} className={className} />;
}
