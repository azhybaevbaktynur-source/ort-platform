"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { apiErrorText } from "@/components/lms/org/OrgUi";

type T = (key: string, params?: Record<string, string | number>) => string;

/** The text of a privacy route's own code, or null for every other code. */
export function ownPrivacyErrorText(t: T, error: unknown): string | null {
  const code = (error as { code?: string } | null)?.code;
  if (!code) return null;
  const key = `privacy.errors.${code}`;
  const text = t(key);
  return text !== key ? text : null;
}

/** Text of an error of the privacy routes: `privacy.errors.<code>`, else the LMS-wide text. */
export function privacyErrorText(t: T, error: unknown): string {
  return ownPrivacyErrorText(t, error) ?? apiErrorText(t, error);
}

export function PrivacyError({ error, className = "" }: { error: unknown; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <p role="alert" className={`flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800 ${className}`}>
      <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
      <span className="min-w-0 break-words">{privacyErrorText(t, error)}</span>
    </p>
  );
}
