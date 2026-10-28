"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultOut, AttemptResultSection } from "@/lib/lms/attemptTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { AttemptGradeOut } from "@/lib/lms/gradingTypes";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { useTemplateUi } from "@/lib/lms/templates";
import { GradeBadge } from "./GradeBadge";
import { OrtResultView } from "./OrtResultView";

export function ResultSummary({ result, grade: gradeProp }: { result: AttemptResultOut; grade?: AttemptGradeOut | null }) {
  const { lang, t } = useTranslation();
  const ui = useTemplateUi();
  // Phase 7b S7: general exams name their sections by title (as the lobby does); ORT keys keep their labels first
  const sectionTitle = (title: AttemptResultSection["title"]) => (typeof title === "string" ? title : pickLocalized(title ?? null, lang));
  const grade = gradeProp ?? result.grade ?? null;
  // Phase 8b S3 (PHASE_8B_DESIGN 8.2): the result payload names the view (the server falls back to the course
  // template, so ORT is "ort"); a payload without the field keeps the course template's choice.
  const scaled = (result.result_view ?? ui.resultView) === "ort" && !!grade && !!grade.sections && grade.sections.length > 0;
  const pending = result.pending_review > 0 ? (
    <p role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
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
            {result.submitted_at && <p className="text-xs text-slate-600">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at) })}</p>}
          </div>
          <OrtResultView grade={grade} sections={result.sections}>
            <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-slate-700">
              <span>{t("results.rawScore")}</span>
              <span className="font-semibold tabular-nums text-slate-900">{fmtPoints(result.raw_score)} / {fmtPoints(result.points_possible)}</span>
            </p>
            {pending}
          </OrtResultView>
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
            {result.submitted_at && <p className="text-xs text-slate-600">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at) })}</p>}
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
              {result.sections.map((s, idx) => (
                <tr key={s.pos} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium text-slate-900">{s.key && t(`sections.${s.key}`) !== `sections.${s.key}` ? t(`sections.${s.key}`) : sectionTitle(s.title) || t("results.sectionN", { n: idx + 1 })}</td>
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
