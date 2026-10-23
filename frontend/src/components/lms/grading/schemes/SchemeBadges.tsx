"use client";

import React from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { Num, SchemeSummaryOut } from "@/lib/lms/gradingTypes";
import { fmtNum } from "./params";

/** Type, ownership and status chips for a scheme. */
export function SchemeBadges({ scheme }: { scheme: Pick<SchemeSummaryOut, "type" | "is_system" | "is_mine" | "deleted_at"> }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">{t(`schemes.types.${scheme.type}`)}</span>
      {scheme.is_system && (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-xs font-semibold text-white">
          <Lock className="h-3 w-3" aria-hidden="true" />{t("schemes.library.system")}
        </span>
      )}
      {scheme.is_mine && !scheme.is_system && (
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">{t("schemes.library.mine")}</span>
      )}
      {scheme.deleted_at && (
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">{t("schemes.library.deleted")}</span>
      )}
    </span>
  );
}

/** "Scale 60-245" when the version has a scale. */
export function ScaleText({ min, max }: { min: Num | null | undefined; max: Num | null | undefined }) {
  const { t } = useTranslation();
  const a = fmtNum(min);
  const b = fmtNum(max);
  if (!a || !b) return null;
  return <span>{t("schemes.library.scale", { min: a, max: b })}</span>;
}
