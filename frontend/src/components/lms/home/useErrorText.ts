"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { LMS_ERROR_CODES } from "@/lib/lms/types";

const KNOWN = new Set<string>(LMS_ERROR_CODES);

/**
 * Phase 6b S6b: what happened and what to do, for `ErrorState`'s message. Network problems say "no connection";
 * known API codes use their own text; anything else keeps the generic "check your connection and retry".
 */
export function useErrorText() {
  const { t } = useTranslation();
  return useCallback((error: unknown): string => {
    const code = (error as { code?: string } | null)?.code;
    if (code === "network") return t("ui.error.offline");
    if (code && code !== "unknown" && KNOWN.has(code)) return t(`lms.errors.${code}`);
    return t("ui.error.body");
  }, [t]);
}
