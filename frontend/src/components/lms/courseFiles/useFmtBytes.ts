"use client";

import { useTranslation } from "@/lib/i18n/context";

/** "1.5 MB" with translated units (decimal, as the storage limits are). */
export function useFmtBytes() {
  const { t } = useTranslation();
  return (n: number): string => {
    if (n >= 1_000_000) return t("courseFiles.units.mb", { n: (n / 1_000_000).toFixed(n >= 100_000_000 ? 0 : 1) });
    if (n >= 1_000) return t("courseFiles.units.kb", { n: Math.round(n / 1_000) });
    return t("courseFiles.units.b", { n });
  };
}
