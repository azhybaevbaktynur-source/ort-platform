"use client";

import React from "react";
import { Award } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptGradeOut, Num } from "@/lib/lms/gradingTypes";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { ScaleText } from "@/components/lms/grading/schemes/SchemeBadges";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";

/** Display text for a grade value as sent by the server (never computed here); percent schemes get a % sign. */
export function useGradeText() {
  const label = useSchemeLabel();
  return (g: { display_value?: Num | null; label?: string | null }, schemeType?: string): string => {
    const v = fmtNum(g.display_value);
    const l = g.label ? label(g.label) : "";
    if (v && schemeType === "percent") return `${v}%`;
    if (v && l) return `${v} · ${l}`;
    return v || l;
  };
}

/** Big grade value, label, percentile, threshold flags and kept/not-released markers. */
export function GradeBadge({ grade, showKept = true }: { grade: AttemptGradeOut; showKept?: boolean }) {
  const { t } = useTranslation();
  const label = useSchemeLabel();
  const text = useGradeText();
  const main = text(grade, grade.scheme_type);
  const flags = Object.entries(grade.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  const pct = fmtPercentile(grade.percentile);
  return (
    <div className="rounded-2xl border border-brand-200 bg-brand-50 p-4" role="group" aria-label={t("results.grade.title")}>
      <p className="text-xs font-medium text-brand-700">{t("results.grade.title")}</p>
      <p className="break-words text-4xl font-bold text-slate-900">{main || "—"}</p>
      <p className="mt-1 text-xs text-slate-600">
        <ScaleText min={grade.scale_min} max={grade.scale_max} />
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {pct && <span className="rounded-full bg-white px-2.5 py-0.5 font-medium text-slate-800">{t("results.grade.percentile", { value: pct })}</span>}
        {grade.passed !== null && grade.passed !== undefined && grade.scheme_type !== "pass_fail" && (
          <span className={`rounded-full px-2.5 py-0.5 font-semibold ${grade.passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
            {label(grade.passed ? "pass" : "fail")}
          </span>
        )}
        {flags.map((k) => (
          <span key={k} className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 font-semibold text-amber-900">
            <Award className="h-3.5 w-3.5" aria-hidden="true" />{label(k)}
          </span>
        ))}
        {showKept && grade.is_kept && <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 font-medium text-indigo-800">{t("results.grade.kept")}</span>}
        {!grade.released && <span className="rounded-full bg-slate-200 px-2.5 py-0.5 font-medium text-slate-700">{t("results.grade.notReleased")}</span>}
      </div>
    </div>
  );
}
