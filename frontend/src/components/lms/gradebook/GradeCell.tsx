"use client";

import React from "react";
import { AlertCircle, Award, Ban, Clock, EyeOff, Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import type { CellView } from "./gradebookModel";

/** Text description of a cell (state + markers) for screen readers and tooltips. */
export function useCellDescription(): (v: CellView) => string {
  const { t } = useTranslation();
  const labelText = useSchemeLabel();
  return (v: CellView) => {
    const parts = [t(`gradebook.states.${v.kind}`)];
    if (v.value) parts.push(v.value);
    if (v.label) parts.push(labelText(v.label));
    if (v.points) parts.push(t("gradebook.cell.points", { points: v.points }));
    if (v.late) parts.push(t("gradebook.flags.late"));
    if (v.overridden) parts.push(t("gradebook.flags.overridden"));
    if (v.unreleased) parts.push(t("gradebook.flags.unreleased"));
    for (const k of v.thresholds) parts.push(labelText(k));
    return parts.join(", ");
  };
}

/** Small marker icons shared by the grid cell and the legend. */
export function CellMarkers({ v }: { v: Pick<CellView, "late" | "overridden" | "unreleased" | "thresholds"> }) {
  return (
    <span className="inline-flex items-center gap-0.5" aria-hidden="true">
      {v.overridden && <Pencil className="h-3 w-3 text-violet-600" />}
      {v.late && <Clock className="h-3 w-3 text-orange-600" />}
      {v.unreleased && <EyeOff className="h-3 w-3 text-slate-400" />}
      {v.thresholds.length > 0 && <Award className="h-3 w-3 text-amber-500" />}
    </span>
  );
}

/** Visible content of one gradebook cell. */
export function CellBody({ v }: { v: CellView }) {
  const { t } = useTranslation();
  const labelText = useSchemeLabel();
  if (v.kind === "none") return <span className="text-slate-300">—</span>;
  if (v.kind === "missing") {
    return <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-semibold text-red-700">{t("gradebook.states.missing")}</span>;
  }
  if (v.kind === "excused") {
    return <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-600">{t("gradebook.cell.excusedShort")}</span>;
  }
  if (v.kind === "no_attempts") {
    return <Ban className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />;
  }
  const main = v.value || (v.label ? labelText(v.label) : "") || v.points || "—";
  const sub = v.value ? (v.label ? labelText(v.label) : v.points) : v.label ? v.points : "";
  return (
    <span className="flex flex-col items-start leading-tight">
      <span className="flex items-center gap-1">
        {v.kind === "needs_review" && <AlertCircle className="h-3.5 w-3.5 text-indigo-600" aria-hidden="true" />}
        <span className={`font-semibold ${v.unreleased ? "text-slate-500" : "text-slate-900"}`}>{main}</span>
        <CellMarkers v={v} />
      </span>
      {sub && <span className="text-[11px] text-slate-500">{sub}</span>}
      {v.kind === "needs_review" && <span className="text-[11px] font-medium text-indigo-700">{t("gradebook.states.needs_review")}</span>}
    </span>
  );
}
