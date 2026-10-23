"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { GRADING_ERROR_CODES, type SchemeParamsInvalidDetails } from "@/lib/lms/gradingTypes";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";

const KNOWN = new Set<string>(GRADING_ERROR_CODES);

/**
 * Error box for grading endpoints: Phase 4 codes are translated here (with the field paths of
 * `scheme_params_invalid`), everything else falls through to AssessmentError -> ContentError -> ErrorMessage.
 */
export function SchemeError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const e = error as { code?: string; details?: SchemeParamsInvalidDetails };
  if (!e.code || !KNOWN.has(e.code)) return <AssessmentError error={error} onRetry={onRetry} className={className} />;
  const paths = e.code === "scheme_params_invalid" && Array.isArray(e.details?.errors)
    ? e.details!.errors!.map((x) => (Array.isArray(x.loc) ? x.loc.join(".") : "")).filter(Boolean).slice(0, 10)
    : [];
  return (
    <div role="alert" className={`flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p>{t(`lms.errors.${e.code}`)}</p>
        {paths.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-xs">
            {paths.map((p, i) => <li key={i}><code className="break-all">{p}</code></li>)}
          </ul>
        )}
      </div>
      {onRetry && <button type="button" onClick={onRetry} className="font-semibold underline">{t("lms.common.retry")}</button>}
    </div>
  );
}
