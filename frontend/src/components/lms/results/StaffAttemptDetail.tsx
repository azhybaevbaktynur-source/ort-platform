"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getStaffAttempt, type AttemptStaffOut } from "@/lib/lms/staffAttempts";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { ReviewItemCard } from "./ReviewItemCard";
import { GradeForm } from "./GradeForm";
import { ResultSummary } from "./ResultSummary";

export function StaffAttemptDetail({ courseId, assessmentId, attemptId }: { courseId: string; assessmentId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const canGrade = true; // StaffGate already limits the page to teachers/assistants; the server enforces grades.manage
  const [data, setData] = useState<AttemptStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [onlyPending, setOnlyPending] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getStaffAttempt(courseId, attemptId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId, attemptId]);
  useEffect(() => { void load(); }, [load]);

  const back = `/${lang}/courses/${courseId}/assessments/${assessmentId}/attempts`;
  const backLink = <Link href={back} className="text-sm font-medium text-brand-700 hover:underline">{t("grading.backToAttempts")}</Link>;
  if (error && !data) return <div className="space-y-3">{backLink}<ErrorMessage error={error} onRetry={() => void load()} /></div>;
  if (!data) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  const submitted = data.status !== "in_progress" && data.status !== "void";
  // essays (pending) first, keeping document order inside each group
  const numbered = data.items.map((it, i) => ({ it, n: i + 1 }));
  const sorted = [...numbered].sort((a, b) => Number(b.it.correctness === "pending") - Number(a.it.correctness === "pending") || a.n - b.n);
  const shown = onlyPending ? sorted.filter((x) => x.it.correctness === "pending") : sorted;

  return (
    <div className="space-y-5">
      {backLink}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">{data.student_name || t("grading.unnamed")}</h2>
          <p className="text-sm text-slate-600">
            {t(`results.status.${data.status}`)}
            {data.attempt_no ? ` · ${t("grading.attemptN", { n: data.attempt_no })}` : ""}
            {data.submitted_at ? ` · ${fmtDateTime(data.submitted_at)}` : ""}
            {data.submit_reason ? ` · ${t(`grading.reason.${data.submit_reason}`)}` : ""}
          </p>
        </div>
        {data.is_preview && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">{t("results.preview")}</span>}
      </div>
      <ErrorMessage error={error} onRetry={() => void load()} />
      {data.status === "needs_review" && (
        <p role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">{t("grading.needsReviewBanner", { n: data.pending_review })}</p>
      )}
      {data.result ? <ResultSummary result={data.result} /> : data.raw_score !== null && data.raw_score !== undefined ? (
        <p className="text-lg font-bold text-slate-900">{fmtPoints(data.raw_score)} / {fmtPoints(data.points_possible)}</p>
      ) : null}
      {!submitted && <p className="text-sm text-slate-600">{t("grading.notSubmitted")}</p>}
      {data.pending_review > 0 && (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
          {t("grading.onlyPending")}
        </label>
      )}
      <div className="space-y-4">
        {shown.map(({ it, n }) => {
          const max = it.points ?? it.question.points ?? null;
          const maxNum = max === null || max === undefined ? null : Number(max);
          return (
            <ReviewItemCard key={it.position} item={it} number={n} maxPoints={max}>
              {canGrade && submitted && (
                <GradeForm courseId={courseId} attemptId={attemptId} item={it}
                  max={maxNum !== null && Number.isFinite(maxNum) ? maxNum : null} onSaved={setData} />
              )}
            </ReviewItemCard>
          );
        })}
      </div>
    </div>
  );
}
