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
export function OrtResultView({ grade, sections }: { grade: AttemptGradeOut; sections: AttemptResultSection[] }) {
  const { t } = useTranslation();
  const label = useSchemeLabel();
  const byPos = new Map((grade.sections ?? []).map((s) => [s.pos, s.display_value]));
  const flags = Object.entries(grade.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  return (
    <div className="space-y-4">
      {flags.length > 0 && (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          <Award className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
          <span>{flags.map((k) => label(k, grade.labels)).join(", ")}</span>
        </div>
      )}
      <GradeBadge grade={grade} />
      {sections.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[20rem] text-sm">
            <caption className="mb-2 text-left text-sm font-semibold text-slate-900">{t("results.grade.sectionsTitle")}</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="py-2 pr-3 font-medium">{t("results.section")}</th>
                <th className="py-2 pr-3 font-medium">{t("results.grade.raw")}</th>
                <th className="py-2 font-medium">{t("results.grade.scaled")}</th>
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
                    <td className="py-2 pr-3">{fmtPoints(s.raw)} / {fmtPoints(s.possible)}</td>
                    <td className="py-2 font-semibold">{v === undefined || v === null ? "—" : fmtNum(v)}</td>
                  </tr>
                );
              })}
              <tr className="bg-slate-50 font-semibold">
                <td className="py-2 pr-3">{t("results.grade.overall")}</td>
                <td className="py-2 pr-3" />
                <td className="py-2">
                  {fmtNum(grade.display_value) || "—"}
                  {grade.percentile !== null && grade.percentile !== undefined && (
                    <span className="ml-2 text-xs font-normal text-slate-500">{t("results.grade.percentile", { value: fmtPercentile(grade.percentile) })}</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
