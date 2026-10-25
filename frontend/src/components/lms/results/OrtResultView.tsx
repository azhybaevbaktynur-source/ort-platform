"use client";

import React from "react";
import { Award } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultSection } from "@/lib/lms/attemptTypes";
import type { AttemptGradeOut } from "@/lib/lms/gradingTypes";
import { fmtPoints } from "@/components/lms/assessments/format";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { GradeBadge } from "./GradeBadge";

/** Scaled (ORT style) result: overall value, percentile, golden banner and per-section scaled values. Server values only. */
export function OrtResultView({ grade, sections, children }: {
  grade: AttemptGradeOut;
  sections: AttemptResultSection[];
  /** Shown between the scaled grade card and the section table (the raw score line, R3). */
  children?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const label = useSchemeLabel();
  const byPos = new Map((grade.sections ?? []).map((s) => [s.pos, s.display_value]));
  const flags = Object.entries(grade.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  return (
    <div className="space-y-4">
      {flags.length > 0 && (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-gold-300 bg-gold-50 px-4 py-3 text-sm font-semibold text-gold-900">
          <Award className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
          <span>{flags.map((k) => label(k, grade.labels)).join(", ")}</span>
        </div>
      )}
      <GradeBadge grade={grade} />
      {children}
      {sections.length > 0 && (
        // S7b, R1: no minimum width, so nothing is cut at 375 px; names wrap, numbers do not, the percentile gets its own line.
        <table className="w-full text-sm">
          <caption className="mb-2 text-left text-sm font-semibold text-slate-900">{t("results.grade.sectionsTitle")}</caption>
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-600">
              <th scope="col" className="py-2 pr-3 font-medium">{t("results.section")}</th>
              <th scope="col" className="whitespace-nowrap py-2 pr-3 font-medium">{t("results.grade.raw")}</th>
              <th scope="col" className="whitespace-nowrap py-2 pr-2 text-right font-medium">
                <span className="sm:hidden">{t("results.grade.scaledShort")}</span>
                <span className="hidden sm:inline">{t("results.grade.scaled")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sections.map((s, idx) => {
              const v = byPos.get(s.pos);
              return (
                <tr key={s.pos} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium text-slate-900">
                    {s.key && t(`sections.${s.key}`) !== `sections.${s.key}` ? t(`sections.${s.key}`) : t("results.sectionN", { n: idx + 1 })}
                  </td>
                  <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{fmtPoints(s.raw)} / {fmtPoints(s.possible)}</td>
                  <td className="whitespace-nowrap py-2 pr-2 text-right font-semibold tabular-nums">{v === undefined || v === null ? "—" : fmtNum(v)}</td>
                </tr>
              );
            })}
            <tr className="bg-slate-50 font-semibold">
              <td className="py-2 pl-2 pr-3">{t("results.grade.overall")}</td>
              <td colSpan={2} className="py-2 pr-2 text-right tabular-nums">
                <span className="whitespace-nowrap">{fmtNum(grade.display_value) || "—"}</span>
                {grade.percentile !== null && grade.percentile !== undefined && (
                  <span className="block text-xs font-normal text-slate-600">{t("results.grade.percentile", { value: fmtPercentile(grade.percentile) })}</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
