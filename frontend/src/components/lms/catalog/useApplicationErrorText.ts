"use client";

// Phase 9 S4: error text for the catalog, the apply flow, the applications inbox and the form builder. S4 codes have
// their own sentences (`applications.errors.*`); everything else falls back to the shared LMS / organization texts.
// Never shows a submitted answer: the server's details name field keys and codes only.
import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { LMS_ERROR_CODES } from "@/lib/lms/types";

const KNOWN = new Set<string>(LMS_ERROR_CODES);

export const S4_ERROR_CODES = [
  "form_required", "form_needs_catalog", "form_answered", "form_draft_exists", "form_retired", "form_not_draft",
  "form_not_found", "too_many_fields", "application_pending", "application_decided", "application_not_found", "form_changed",
  "course_full", "course_not_open", "template_locked", "already_enrolled",
] as const;
const S4 = new Set<string>(S4_ERROR_CODES);

export function useApplicationErrorText() {
  const { t } = useTranslation();
  return useCallback((error: unknown): string => {
    if (!error) return "";
    const code = (error as { code?: string } | null)?.code;
    if (code === "network") return t("ui.error.offline");
    if (code && S4.has(code)) return t(`applications.errors.${code}`);
    if (code === "validation_failed") return t("applications.errors.validation_failed");
    if (code && code !== "unknown" && KNOWN.has(code)) return t(`lms.errors.${code}`);
    if (code) {
      const orgKey = `organizations.errors.${code}`;
      const orgText = t(orgKey);
      if (orgText !== orgKey) return orgText;
    }
    return t("ui.error.body");
  }, [t]);
}
