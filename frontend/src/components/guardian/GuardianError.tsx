"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

/** The text of a parent-route error (`guardian.errors.<code>`), or null when the code has none of its own. */
export function useGuardianErrorText() {
  const { t } = useTranslation();
  return (error: unknown): string | null => {
    const code = (error as { code?: string } | null)?.code;
    if (!code) return null;
    const key = `guardian.errors.${code}`;
    const text = t(key);
    return text === key ? null : text;
  };
}

export function GuardianError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const text = useGuardianErrorText();
  if (!error) return null;
  const own = text(error);
  if (!own) return <ErrorMessage error={error} onRetry={onRetry} className={className} />;
  return (
    <p role="alert" className={`rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>{own}</p>
  );
}
