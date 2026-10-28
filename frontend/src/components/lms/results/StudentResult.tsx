"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getAttempt, getAttemptResult, getAttemptReview } from "@/lib/lms/attempts";
import type { AttemptResultOut, AttemptState, Correctness, ReviewItemOut, ReviewOut } from "@/lib/lms/attemptTypes";
import { LmsApiError } from "@/lib/lms/client";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { ChevronDown } from "lucide-react";
import { LinkButton, LoadingState, cn, focusRing } from "@/components/ui";
import { ResultSummary } from "./ResultSummary";
import { ReviewItemCard } from "./ReviewItemCard";
import { useReturnPath, withReturn } from "@/components/lms/player/returnPath";
import type { PassageDisplay } from "@/lib/lms/blocks";

export function StudentResult({ courseId, attemptId }: { courseId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const returnPath = useReturnPath(lang); // Phase 8b S3
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
  // Phase 8b S3 (PHASE_8B_DESIGN 7.2): a validated `?return=` (template preview) replaces the back link; absent = today's.
  const backLink = returnPath
    ? <Link href={returnPath} className="text-sm font-medium text-brand-700 hover:underline">{t("player.scrolling.back")}</Link>
    : <Link href={back} className="text-sm font-medium text-brand-700 hover:underline">{t("results.back")}</Link>;

  if (loading && !state) return <LoadingState label={t("lms.common.loading")} rows={2} />;
  if (error && !state) return <div className="space-y-3">{backLink}<ErrorMessage error={error} onRetry={() => void load()} /></div>;
  if (!state) return null;

  if (state.status === "in_progress") {
    return (
      <div className="space-y-3">
        {backLink}
        <div role="status" className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <p className="mb-3 font-semibold">{t("results.inProgress")}</p>
          <LinkButton href={withReturn(`/${lang}/courses/${courseId}/attempts/${attemptId}`, returnPath)}>{t("results.resume")}</LinkButton>
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
        <ReviewList items={review.items} sections={result?.sections ?? []} passageDisplay={review.passage_display ?? result?.passage_display ?? null} />
      )}
      {review && review.items.length === 0 && <p className="text-sm text-slate-500">{t("results.noReview")}</p>}
    </div>
  );
}

const MISTAKES = new Set<Correctness>(["incorrect", "partial", "unanswered"]);

/**
 * The answer review (S7b, R4): grouped by section (folding groups, all open), with an optional "only mistakes"
 * filter that is off by default. Every card and its content are unchanged; numbering stays global.
 */
function ReviewList({ items, sections, passageDisplay }: {
  items: ReviewItemOut[];
  sections: AttemptResultOut["sections"];
  /** Phase 8b S3: renderer from the review payload (null: course template). */
  passageDisplay: PassageDisplay | null;
}) {
  const { t } = useTranslation();
  const [onlyMistakes, setOnlyMistakes] = useState(false);
  const groups = useMemo(() => {
    const out: { pos: number; entries: { item: ReviewItemOut; number: number }[] }[] = [];
    items.forEach((item, i) => {
      let g = out.find((x) => x.pos === item.section_pos);
      if (!g) {
        g = { pos: item.section_pos, entries: [] };
        out.push(g);
      }
      g.entries.push({ item, number: i + 1 });
    });
    return out;
  }, [items]);
  const sectionName = (pos: number) => {
    const idx = sections.findIndex((s) => s.pos === pos);
    const key = idx >= 0 ? sections[idx].key : null;
    if (key && t(`sections.${key}`) !== `sections.${key}`) return t(`sections.${key}`);
    return t("results.sectionN", { n: idx >= 0 ? idx + 1 : pos });
  };
  const show = (it: ReviewItemOut) => !onlyMistakes || (it.correctness !== null && MISTAKES.has(it.correctness));
  const anyShown = items.some(show);
  const grouped = groups.length > 1;

  return (
    <section className="space-y-4" aria-label={t("results.reviewTitle")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-900">{t("results.reviewTitle")}</h3>
        <button
          type="button"
          aria-pressed={onlyMistakes}
          onClick={() => setOnlyMistakes((v) => !v)}
          className={cn(
            "inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-semibold transition-colors sm:min-h-9",
            focusRing,
            onlyMistakes ? "border-brand-600 bg-brand-600 text-white hover:bg-brand-700" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
          )}
        >
          {t("results.review.onlyMistakes")}
        </button>
      </div>
      {!anyShown && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{t("results.review.noMistakes")}</p>}
      {grouped
        ? groups.map((g) => {
          const shown = g.entries.filter((e) => show(e.item));
          if (shown.length === 0) return null;
          const correct = g.entries.filter((e) => e.item.correctness === "correct").length;
          return (
            <details key={g.pos} open className="group space-y-4">
              <summary className={cn("flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 [&::-webkit-details-marker]:hidden", focusRing)}>
                <span className="font-semibold text-slate-900">{sectionName(g.pos)}</span>
                <span className="flex shrink-0 items-center gap-2 text-sm text-slate-700">
                  {t("results.review.sectionSummary", { correct, total: g.entries.length })}
                  <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
                </span>
              </summary>
              <div className="space-y-4">
                {shown.map((e) => <ReviewItemCard key={e.item.position} item={e.item} number={e.number} passageDisplay={passageDisplay} />)}
              </div>
            </details>
          );
        })
        : groups.flatMap((g) => g.entries).filter((e) => show(e.item)).map((e) => <ReviewItemCard key={e.item.position} item={e.item} number={e.number} passageDisplay={passageDisplay} />)}
    </section>
  );
}
