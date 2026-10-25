"use client";

import React from "react";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { StorageLevel } from "@/lib/lms/storage";
import { cn } from "@/components/ui";

/** Amber at >= warn, red when full (Phase 5 R2 free-tier guard). Renders nothing at level ok. */
export function StorageLevelBanner({ level, className = "", children }: { level: StorageLevel; className?: string; children?: React.ReactNode }) {
  const { t } = useTranslation();
  if (level === "ok") return null;
  const full = level === "full";
  return (
    <div role="alert" className={cn("flex gap-3 rounded-2xl border p-4 text-sm leading-6",
      full ? "border-danger-200 bg-danger-50 text-danger-800" : "border-warning-200 bg-warning-50 text-warning-900", className)}>
      <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{t(full ? "storage.banner.fullTitle" : "storage.banner.warnTitle")}</p>
        <p>{full ? t("files.errors.storage_full") : t("storage.banner.warnBody")}</p>
        {children}
      </div>
    </div>
  );
}
