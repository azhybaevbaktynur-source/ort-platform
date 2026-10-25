"use client";

import React from "react";
import { Award } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptGradeOut, Num, SchemeLabelValue } from "@/lib/lms/gradingTypes";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { ScaleText } from "@/components/lms/grading/schemes/SchemeBadges";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { Badge } from "@/components/ui";

/**
 * Display text for a grade value as sent by the server (never computed here); percent schemes get a % sign.
 * The label is resolved through the grade's own `labels`, else `fallbackLabels` (e.g. the scheme ref's map).
 */
export function useGradeText() {
  const label = useSchemeLabel();
  return (g: { display_value?: Num | null; label?: string | null; labels?: Record<string, SchemeLabelValue> | null },
    schemeType?: string, fallbackLabels?: Record<string, SchemeLabelValue> | null): string => {
    const v = fmtNum(g.display_value);
    const l = g.label ? label(g.label, { ...(fallbackLabels ?? {}), ...(g.labels ?? {}) }) : "";
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
      <p className="mt-1 text-xs text-slate-700">
        <ScaleText min={grade.scale_min} max={grade.scale_max} />
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {pct && <Badge className="border-brand-200 bg-white text-sm text-slate-800">{t("results.grade.percentile", { value: pct })}</Badge>}
        {grade.passed !== null && grade.passed !== undefined && grade.scheme_type !== "pass_fail" && (
          <Badge tone={grade.passed ? "success" : "danger"}>{label(grade.passed ? "pass" : "fail")}</Badge>
        )}
        {flags.map((k) => (
          <Badge key={k} tone="warning" icon={<Award aria-hidden="true" />}>{label(k, grade.labels)}</Badge>
        ))}
        {showKept && grade.is_kept && <Badge tone="info" className="bg-white">{t("results.grade.kept")}</Badge>}
        {!grade.released && <Badge tone="neutral">{t("results.grade.notReleased")}</Badge>}
      </div>
    </div>
  );
}
