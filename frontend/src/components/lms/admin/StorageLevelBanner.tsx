"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { StorageLevel } from "@/lib/lms/storage";

/** Amber at >= warn, red when full (Phase 5 R2 free-tier guard). Renders nothing at level ok. */
export function StorageLevelBanner({ level, className = "", children }: { level: StorageLevel; className?: string; children?: React.ReactNode }) {
  const { t } = useTranslation();
  if (level === "ok") return null;
  const full = level === "full";
  return (
    <div role="alert" className={`rounded-xl border px-4 py-3 text-sm ${full ? "border-red-300 bg-red-50 text-red-800" : "border-amber-300 bg-amber-50 text-amber-900"} ${className}`}>
      <p className="font-semibold">{t(full ? "storage.banner.fullTitle" : "storage.banner.warnTitle")}</p>
      <p className="mt-1">{full ? t("files.errors.storage_full") : t("storage.banner.warnBody")}</p>
      {children}
    </div>
  );
}
