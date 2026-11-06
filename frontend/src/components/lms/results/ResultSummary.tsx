"use client";

import React, { useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultOut, AttemptResultSection } from "@/lib/lms/attemptTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { AttemptGradeOut } from "@/lib/lms/gradingTypes";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { useTemplateUi } from "@/lib/lms/templates";
import { Award } from "lucide-react";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { GradeBadge } from "./GradeBadge";
import { SectionBreakdown } from "./SectionBreakdown"; // SF-1: replaces OrtResultView's table

/**
 * One name per result section, shared by the summary table and the answer review (Phase 8b UX): the label of a
 * known section key (ORT) first, then the section's own title (general exams, as the lobby does), then
 * "Section n" by order (`pos` only when the section is not in the list).
 */
export function useResultSectionName(sections: AttemptResultOut["sections"]) {
  const { lang, t } = useTranslation();
  return useCallback((pos: number) => {
    const idx = sections.findIndex((s) => s.pos === pos);
    const s: AttemptResultSection | undefined = idx >= 0 ? sections[idx] : undefined;
    if (s?.key && t(`sections.${s.key}`) !== `sections.${s.key}`) return t(`sections.${s.key}`);
    const title = s?.title;
    const named = typeof title === "string" ? title : pickLocalized(title ?? null, lang);
    return named || t("results.sectionN", { n: idx >= 0 ? idx + 1 : pos });
  }, [sections, lang, t]);
}

/**
 * Phase 8b S3 (PHASE_8B_DESIGN 8.2): the result payload names the view (the server falls back to the course template,
 * so ORT is "ort"); a payload without the field keeps the course template's choice. Scaled = that view with
 * per-section scaled values.
 */
export function isScaledResult(result: AttemptResultOut, grade: AttemptGradeOut | null, templateView: string): boolean {
  return (result.result_view ?? templateView) === "ort" && !!grade && !!grade.sections && grade.sections.length > 0;
}

export function ResultSummary({ result, grade: gradeProp }: { result: AttemptResultOut; grade?: AttemptGradeOut | null }) {
  const { lang, t } = useTranslation();
  const ui = useTemplateUi();
  const sectionName = useResultSectionName(result.sections);
  const label = useSchemeLabel();
  const grade = gradeProp ?? result.grade ?? null;
  const scaled = isScaledResult(result, grade, ui.resultView);
  const flags = Object.entries(grade?.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  const pending = result.pending_review > 0 ? (
    <p role="status" className="rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-900">
      {t("results.pendingReview", { n: result.pending_review })}
    </p>
  ) : null;
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" aria-label={t("results.title")}>
      {scaled && grade ? (
        // S7b, R3: ORT opens with the scaled grade; the raw points are a small line under it.
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <p className="text-base font-semibold text-slate-900">{t("results.finishedIntro")}</p>
            {result.submitted_at && <p className="text-xs text-slate-600">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at, lang) })}</p>}
          </div>
          {flags.length > 0 && (
            <div role="status" className="flex items-center gap-2 rounded-xl border border-gold-300 bg-gold-50 px-4 py-3 text-sm font-semibold text-gold-900">
              <Award className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
              <span>{flags.map((k) => label(k, grade.labels)).join(", ")}</span>
            </div>
          )}
          <GradeBadge grade={grade} />
          <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-slate-700">
            <span>{t("results.rawScore")}</span>
            <span className="font-semibold tabular-nums text-slate-900">{fmtPoints(result.raw_score)} / {fmtPoints(result.points_possible)}</span>
          </p>
          {pending}
          <SectionBreakdown result={result} grade={grade} />
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-slate-600">{t("results.rawScore")}</p>
              <p className="text-3xl font-bold text-slate-900">
                {fmtPoints(result.raw_score)} <span className="text-lg font-medium text-slate-600">/ {fmtPoints(result.points_possible)}</span>
              </p>
            </div>
            {result.submitted_at && <p className="text-xs text-slate-600">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at, lang) })}</p>}
          </div>
          {pending}
          {grade && <GradeBadge grade={grade} />}
        </>
      )}
      {!scaled && result.sections.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="py-2 pr-3 font-medium">{t("results.section")}</th>
                <th className="py-2 pr-3 font-medium">{t("results.points")}</th>
                <th className="py-2 pr-3 font-medium">{t("results.answered")}</th>
                <th className="py-2 font-medium">{t("results.correct")}</th>
              </tr>
            </thead>
            <tbody>
              {result.sections.map((s) => (
                <tr key={s.pos} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium text-slate-900">{sectionName(s.pos)}</td>
                  <td className="py-2 pr-3">{fmtPoints(s.raw)} / {fmtPoints(s.possible)}</td>
                  <td className="py-2 pr-3">{s.answered}</td>
                  <td className="py-2">{s.correct}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
