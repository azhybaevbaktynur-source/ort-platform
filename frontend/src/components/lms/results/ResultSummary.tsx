"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultOut } from "@/lib/lms/attemptTypes";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";

export function ResultSummary({ result }: { result: AttemptResultOut }) {
  const { t } = useTranslation();
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" aria-label={t("results.title")}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-500">{t("results.rawScore")}</p>
          <p className="text-3xl font-bold text-slate-900">
            {fmtPoints(result.raw_score)} <span className="text-lg font-medium text-slate-500">/ {fmtPoints(result.points_possible)}</span>
          </p>
        </div>
        {result.submitted_at && <p className="text-xs text-slate-500">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at) })}</p>}
      </div>
      {result.pending_review > 0 && (
        <p role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
          {t("results.pendingReview", { n: result.pending_review })}
        </p>
      )}
      {result.sections.length > 0 && (
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
                  <td className="py-2 pr-3 font-medium text-slate-900">{s.key && t(`sections.${s.key}`) !== `sections.${s.key}` ? t(`sections.${s.key}`) : t("results.sectionN", { n: idx + 1 })}</td>
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
