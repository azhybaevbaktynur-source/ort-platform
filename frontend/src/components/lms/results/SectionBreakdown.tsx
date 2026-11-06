"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultOut } from "@/lib/lms/attemptTypes";
import type { AttemptGradeOut } from "@/lib/lms/gradingTypes";
import { fmtPoints } from "@/components/lms/assessments/format";
import { fmtNum } from "@/components/lms/grading/schemes/params";
import { cn } from "@/components/ui";
import { useResultSectionName } from "./ResultSummary";

/**
 * SF-1 (STUDENT_UI_FIX_PLAN §2.2 item 5): the per-section rows of a result, in the attempt's section order: a neutral
 * section tag, the raw "12 / 30" with a thin bar of that ratio and, for scaled schemes (ORT), the scaled value; then
 * the overall row. Every number is the server's (`result.sections`, `grade.sections`). It stays a table with the
 * caption "results.grade.sectionsTitle" (the ORT DOM checks read its rows).
 */
export function SectionBreakdown({ result, grade, className }: {
  result: AttemptResultOut;
  /** The grade with per-section scaled values (scaled view); null for points-only results. */
  grade: AttemptGradeOut | null;
  className?: string;
}) {
  const { t } = useTranslation();
  const sectionName = useResultSectionName(result.sections);
  const scaled = !!grade?.sections && grade.sections.length > 0;
  const byPos = new Map((grade?.sections ?? []).map((s) => [s.pos, s.display_value]));
  if (result.sections.length === 0) return null;
  return (
    <table className={cn("w-full text-sm", className)}>
      <caption className="mb-2 text-left text-base font-semibold text-slate-900">{t("results.grade.sectionsTitle")}</caption>
      <thead>
        <tr className="border-b border-slate-200 text-left text-xs text-slate-600">
          <th scope="col" className="py-2 pr-3 font-medium">{t("results.section")}</th>
          <th scope="col" className="whitespace-nowrap py-2 pr-3 font-medium">{t("results.grade.raw")}</th>
          <th scope="col" className="whitespace-nowrap py-2 text-right font-medium">
            {scaled ? (
              <>
                <span className="sm:hidden">{t("results.grade.scaledShort")}</span>
                <span className="hidden sm:inline">{t("results.grade.scaled")}</span>
              </>
            ) : t("results.correct")}
          </th>
        </tr>
      </thead>
      <tbody>
        {result.sections.map((s) => {
          const raw = Number(s.raw);
          const possible = Number(s.possible);
          const ratio = possible > 0 && Number.isFinite(raw) ? Math.max(0, Math.min(1, raw / possible)) : 0;
          const v = byPos.get(s.pos);
          return (
            <tr key={s.pos} className="border-b border-slate-100 align-middle">
              <td className="py-3 pr-3">
                <span className="inline-flex max-w-full rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold leading-5 text-slate-700">
                  <span className="min-w-0 break-words">{sectionName(s.pos)}</span>
                </span>
              </td>
              <td className="py-3 pr-3">
                <span className="whitespace-nowrap font-medium tabular-nums text-slate-900">{fmtPoints(s.raw)} / {fmtPoints(s.possible)}</span>
                <span aria-hidden="true" className="mt-1.5 block h-1.5 w-full max-w-40 overflow-hidden rounded-full bg-slate-100">
                  <span className="block h-full rounded-full bg-brand-500" style={{ width: `${Math.round(ratio * 100)}%` }} />
                </span>
              </td>
              <td className="whitespace-nowrap py-3 text-right font-semibold tabular-nums text-slate-900">
                {scaled ? (v === undefined || v === null ? "—" : fmtNum(v)) : s.correct}
              </td>
            </tr>
          );
        })}
        <tr className="font-semibold text-slate-900">
          <td className="py-3 pr-3">{t("results.grade.overall")}</td>
          <td className="whitespace-nowrap py-3 pr-3 tabular-nums">{fmtPoints(result.raw_score)} / {fmtPoints(result.points_possible)}</td>
          <td className="whitespace-nowrap py-3 text-right tabular-nums">{scaled ? fmtNum(grade?.display_value) || "—" : ""}</td>
        </tr>
      </tbody>
    </table>
  );
}
