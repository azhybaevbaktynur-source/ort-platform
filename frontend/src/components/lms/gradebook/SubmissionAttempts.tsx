"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import type { SchemeLabelValue, SubmissionAttemptOut } from "@/lib/lms/gradingTypes";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { btnDanger } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { canVoid, fmtPointsOf, lateParts } from "./gradebookModel";

/** Counted attempts of a submission with their own grade, the kept marker and a Void action. */
export function SubmissionAttempts({
  attempts, labels, keptAttemptId, attemptHref, canManage, onVoid,
}: {
  attempts: SubmissionAttemptOut[];
  /** the column scheme's label map; each grade's own `labels` wins */
  labels?: Record<string, SchemeLabelValue> | null;
  keptAttemptId: string | null;
  attemptHref: (attemptId: string) => string;
  canManage: boolean;
  onVoid: (a: SubmissionAttemptOut) => void;
}) {
  const { t } = useTranslation();
  const labelText = useSchemeLabel();
  if (attempts.length === 0) return <p className="text-sm text-slate-500">{t("gradebook.panel.noAttempts")}</p>;
  return (
    <ul className="space-y-2">
      {attempts.map((a) => {
        const kept = a.id === keptAttemptId || !!a.grade?.is_kept;
        const late = lateParts(a.late_seconds);
        const g = a.grade;
        const gradeText = g ? [fmtNum(g.display_value), g.label ? labelText(g.label, { ...(labels ?? {}), ...(g.labels ?? {}) }) : ""].filter(Boolean).join(" · ") : "";
        const pct = g ? fmtPercentile(g.percentile) : "";
        return (
          <li key={a.id} className={`rounded-xl border p-3 text-sm ${kept ? "border-brand-500 bg-brand-50" : "border-slate-200"}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-900">
                {a.attempt_no !== null ? t("gradebook.panel.attemptN", { n: a.attempt_no }) : t("gradebook.panel.attempt")}
              </span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{t(`results.status.${a.status}`)}</span>
              {kept && <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">{t("gradebook.panel.kept")}</span>}
              {late && (
                <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-800">
                  {t("gradebook.panel.lateBy", { days: late.days, hours: late.hours })}
                </span>
              )}
            </div>
            <dl className="mt-1 grid grid-cols-[auto,1fr] gap-x-3 text-xs text-slate-600">
              <dt>{t("gradebook.panel.points")}</dt>
              <dd>{fmtPointsOf(a.raw_score, a.points_possible) || "—"}</dd>
              {gradeText && (<><dt>{t("gradebook.panel.grade")}</dt><dd className="font-medium text-slate-900">{gradeText}</dd></>)}
              {pct && (<><dt>{t("gradebook.panel.percentile")}</dt><dd>{pct}</dd></>)}
              <dt>{t("gradebook.panel.submitted")}</dt>
              <dd>{fmtDateTime(a.submitted_at) || "—"}</dd>
            </dl>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <Link href={attemptHref(a.id)} className="text-sm font-medium text-brand-700 hover:underline">{t("gradebook.panel.openAttempt")}</Link>
              {canManage && canVoid(a) && (
                <button type="button" onClick={() => onVoid(a)} className={btnDanger}>{t("gradebook.void.action")}</button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
