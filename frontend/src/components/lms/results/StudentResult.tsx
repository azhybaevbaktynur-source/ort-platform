"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getAttempt, getAttemptResult, getAttemptReview } from "@/lib/lms/attempts";
import type { AttemptResultOut, AttemptState, ReviewOut } from "@/lib/lms/attemptTypes";
import { LmsApiError } from "@/lib/lms/client";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { ResultSummary } from "./ResultSummary";
import { ReviewItemCard } from "./ReviewItemCard";

export function StudentResult({ courseId, attemptId }: { courseId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const [state, setState] = useState<AttemptState | null>(null);
  const [result, setResult] = useState<AttemptResultOut | null>(null);
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [reviewError, setReviewError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const st = await getAttempt(attemptId);
      setState(st);
      setError(null);
      if (st.status === "in_progress" || !st.results_available) {
        setResult(null);
        setReview(null);
        return;
      }
      try {
        setResult(await getAttemptResult(attemptId));
      } catch (e) {
        // policy flipped between the two calls: show the "not available" state
        if (e instanceof LmsApiError && e.code === "results_not_available") {
          setState({ ...st, results_available: false });
          return;
        }
        throw e;
      }
      try {
        setReview(await getAttemptReview(attemptId));
        setReviewError(null);
      } catch (e) {
        setReview(null);
        if (!(e instanceof LmsApiError && e.code === "results_not_available")) setReviewError(e);
      }
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [attemptId]);
  useEffect(() => { void load(); }, [load]);

  const back = `/${lang}/courses/${courseId}/assessments${state ? `/${state.assessment_id}` : ""}`;
  const backLink = <Link href={back} className="text-sm font-medium text-brand-700 hover:underline">{t("results.back")}</Link>;

  if (loading && !state) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (error && !state) return <div className="space-y-3">{backLink}<ErrorMessage error={error} onRetry={() => void load()} /></div>;
  if (!state) return null;

  if (state.status === "in_progress") {
    return (
      <div className="space-y-3">
        {backLink}
        <div role="status" className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <p className="mb-3 font-semibold">{t("results.inProgress")}</p>
          <Link href={`/${lang}/courses/${courseId}/attempts/${attemptId}`} className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">{t("results.resume")}</Link>
        </div>
      </div>
    );
  }

  if (state.status === "void") {
    return (
      <div className="space-y-3">
        {backLink}
        <div role="status" className="rounded-2xl border border-red-200 bg-red-50 p-5">
          <h2 className="mb-1 text-lg font-bold text-red-900">{t("results.grade.voidedTitle")}</h2>
          <p className="text-sm text-red-800">{t("results.grade.voided")}</p>
        </div>
      </div>
    );
  }

  if (!state.results_available) {
    return (
      <div className="space-y-3">
        {backLink}
        <div role="status" className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="mb-1 text-lg font-bold text-slate-900">{t("results.submittedTitle")}</h2>
          <p className="text-sm text-slate-600">{t("results.notAvailable")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {backLink}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t("results.title")}</h2>
        {state.is_preview && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">{t("results.preview")}</span>}
      </div>
      <ErrorMessage error={error} onRetry={() => void load()} />
      {result && <ResultSummary result={result} />}
      {reviewError ? <ErrorMessage error={reviewError} onRetry={() => void load()} /> : null}
      {review && review.items.length > 0 && (
        <section className="space-y-4" aria-label={t("results.reviewTitle")}>
          <h3 className="text-base font-semibold text-slate-900">{t("results.reviewTitle")}</h3>
          {review.items.map((it, i) => <ReviewItemCard key={it.position} item={it} number={i + 1} />)}
        </section>
      )}
      {review && review.items.length === 0 && <p className="text-sm text-slate-500">{t("results.noReview")}</p>}
    </div>
  );
}
