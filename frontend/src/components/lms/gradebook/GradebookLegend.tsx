"use client";

import React from "react";
import { AlertCircle, Award, Clock, EyeOff, Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";

/** Key for the cell markers. */
export function GradebookLegend() {
  const { t } = useTranslation();
  const item = (icon: React.ReactNode, label: string) => (
    <li className="inline-flex items-center gap-1">{icon}<span>{label}</span></li>
  );
  return (
    <ul aria-label={t("gradebook.legend.title")} className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      {item(<AlertCircle className="h-3.5 w-3.5 text-indigo-600" aria-hidden="true" />, t("gradebook.states.needs_review"))}
      {item(<Pencil className="h-3 w-3 text-violet-600" aria-hidden="true" />, t("gradebook.flags.overridden"))}
      {item(<Clock className="h-3 w-3 text-orange-600" aria-hidden="true" />, t("gradebook.flags.late"))}
      {item(<EyeOff className="h-3 w-3 text-slate-400" aria-hidden="true" />, t("gradebook.flags.unreleased"))}
      {item(<Award className="h-3 w-3 text-amber-500" aria-hidden="true" />, t("gradebook.flags.threshold"))}
      {item(<span className="rounded bg-slate-100 px-1 text-[10px] font-semibold text-slate-600">{t("gradebook.cell.excusedShort")}</span>, t("gradebook.states.excused"))}
      {item(<span className="rounded bg-red-50 px-1 text-[10px] font-semibold text-red-700">{t("gradebook.states.missing")}</span>, t("gradebook.legend.missing"))}
    </ul>
  );
}
