"use client";

import { useTranslation } from "@/lib/i18n/context";

const KNOWN = new Set(["points_possible_mismatch", "uncategorized_excluded"]);

/** Text for a gradebook/totals warning code; unknown codes get a generic sentence. */
export function useWarningText(): (code: string) => string {
  const { t } = useTranslation();
  return (code: string) => t(`gradebook.warnings.${KNOWN.has(code) ? code : "unknown"}`);
}
