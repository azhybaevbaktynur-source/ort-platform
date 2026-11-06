"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ListChecks } from "lucide-react";
import { BackLink } from "@/components/lms/BackLink";
import { useTranslation } from "@/lib/i18n/context";
import { getAttempt, getAttemptResult, getAttemptReview } from "@/lib/lms/attempts";
import type { AttemptResultOut, AttemptState, Correctness, ReviewItemOut, ReviewOut } from "@/lib/lms/attemptTypes";
import { getAssessment } from "@/lib/lms/assessments";
import { getExamPrep, type ExamNextOut } from "@/lib/lms/examPrep";
import { LmsApiError } from "@/lib/lms/client";
import { pickLocalized } from "@/lib/lms/localized";
import { isExamPrepStudent, useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, LinkButton, LoadingState, cn, focusRing } from "@/components/ui";
import { isScaledResult, useResultSectionName } from "./ResultSummary";
import { ReviewItemCard } from "./ReviewItemCard";
import { ExamResultHero } from "./ExamResultHero";
import { SectionBreakdown } from "./SectionBreakdown";
import { useReturnPath, withReturn } from "@/components/lms/player/returnPath";
import type { PassageDisplay } from "@/lib/lms/blocks";

const REVIEW_ID = "review";
const ITEM_HASH = /^#item-(\d+)$/;

/**
 * The student's result page (SF-1, STUDENT_UI_FIX_PLAN §2.2): back link, title, one result card (hero with the score,
 * section breakdown), the actions ("Review mistakes" primary, "Next test" for exam-prep students) and the answer
 * review. Every number comes from the server; the not-available, in-progress and void states keep their logic.
 */
export function StudentResult({ courseId, attemptId }: { courseId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const ui = useTemplateUi();
  const examPrep = isExamPrepStudent(course);
  const returnPath = useReturnPath(lang); // Phase 8b S3
  const [state, setState] = useState<AttemptState | null>(null);
  const [result, setResult] = useState<AttemptResultOut | null>(null);
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [reviewError, setReviewError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [next, setNext] = useState<ExamNextOut | null | undefined>(undefined);
  const [onlyMistakes, setOnlyMistakes] = useState(false);

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

  // The test's title for the header (best effort: the page works without it)
  const assessmentId = state?.assessment_id ?? null;
  useEffect(() => {
    if (!assessmentId) return;
    let live = true;
    getAssessment(courseId, assessmentId)
      .then((a) => { if (live) setTitle(pickLocalized(a.title, lang, course.default_language)); })
      .catch(() => { /* no title */ });
    return () => { live = false; };
  }, [courseId, assessmentId, lang, course.default_language]);

  // "Next test" (exam-prep students, graded attempts): the exam-prep page's own suggestion
  const wantsNext = examPrep && !!state && !state.is_preview && !state.is_practice && state.status !== "in_progress";
  useEffect(() => {
    if (!wantsNext) return;
    let live = true;
    getExamPrep(courseId).then((p) => { if (live) setNext(p.next); }).catch(() => { if (live) setNext(null); });
    return () => { live = false; };
  }, [courseId, wantsNext]);

  // Problem 3: a link to `#item-n` (Сохранённые, Ошибки) lands on that card once it is rendered. Runs after the
  // render that has the review (and again after the filter changes), so the card exists when it scrolls; a card the
  // "only mistakes" filter hides turns the filter off first. Once per hash.
  const scrolledHash = useRef<string | null>(null);
  useEffect(() => {
    if (!review || typeof window === "undefined") return;
    const hash = window.location.hash;
    const m = ITEM_HASH.exec(hash);
    if (!m || scrolledHash.current === hash) return;
    const target = review.items.find((it) => it.position === Number(m[1]));
    if (!target) return;
    const el = document.getElementById(`item-${target.position}`);
    if (!el) {
      if (onlyMistakes) setOnlyMistakes(false); // hidden by the filter: show it, this effect runs again
      return;
    }
    scrolledHash.current = hash;
    el.scrollIntoView({ block: "start" });
  }, [review, onlyMistakes]);

  const lobby = `/${lang}/courses/${courseId}/assessments${state ? `/${state.assessment_id}` : ""}`;
  // Phase 8b S3 (PHASE_8B_DESIGN 7.2): a validated `?return=` (template preview) replaces the back link. SF-1: an
  // exam-prep student goes back to Тесты; other students to the test's lobby.
  const backLink = returnPath
    ? <BackLink href={returnPath}>{t(state?.is_preview ? "examTemplates.preview.backToTemplate" : "player.scrolling.back")}</BackLink>
    : examPrep
      ? <BackLink href={`/${lang}/courses/${courseId}/tests`}>{t("results.backToTests")}</BackLink>
      : <BackLink href={lobby}>{t("results.back")}</BackLink>;

  if (loading && !state) return <LoadingState label={t("lms.common.loading")} rows={2} />;
  if (error && !state) return <div className="space-y-3">{backLink}<ErrorMessage error={error} onRetry={() => void load()} /></div>;
  if (!state) return null;

  if (state.status === "in_progress") {
    return (
      <div className="space-y-3">
        {backLink}
        <div role="status" className="rounded-card border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
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
        <div role="status" className="rounded-card border border-red-200 bg-red-50 p-5">
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
        <div role="status" className="rounded-card border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-1 text-lg font-bold text-slate-900">{t("results.submittedTitle")}</h2>
          <p className="text-sm text-slate-600">{t("results.notAvailable")}</p>
        </div>
      </div>
    );
  }

  const grade = result?.grade ?? null;
  const scaled = !!result && isScaledResult(result, grade, ui.resultView);
  const hasReview = !!review && review.items.length > 0;
  const nextHref = next && next.assessment_id ? `/${lang}/courses/${courseId}/assessments/${next.assessment_id}` : `/${lang}/courses/${courseId}/tests`;
  const reviewMistakes = () => {
    setOnlyMistakes(true);
    window.requestAnimationFrame(() => document.getElementById(REVIEW_ID)?.scrollIntoView({ block: "start" }));
  };

  return (
    <div className="space-y-5">
      {backLink}
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold leading-8 text-slate-900">{t("results.title")}</h1>
          {state.is_preview && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">{t("results.preview")}</span>}
        </div>
        {title && <p className="break-words text-base text-slate-600">{title}</p>}
      </header>
      <ErrorMessage error={error} onRetry={() => void load()} />
      {result && (
        <section aria-label={t("results.title")} className="space-y-6 rounded-card border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <ExamResultHero result={result} grade={grade} scaled={scaled} showPass={!examPrep}
            showMascot={!state.is_preview && !state.is_practice} />
          {result.pending_review > 0 && (
            <p role="status" className="rounded-control border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
              {t("results.pendingReview", { n: result.pending_review })}
            </p>
          )}
          <SectionBreakdown result={result} grade={scaled ? grade : null} />
        </section>
      )}
      {(hasReview || wantsNext) && (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          {hasReview && <Button leftIcon={<ListChecks aria-hidden="true" />} onClick={reviewMistakes}>{t("results.actions.reviewMistakes")}</Button>}
          {wantsNext && <LinkButton variant="secondary" href={nextHref}>{t("results.actions.nextTest")}</LinkButton>}
        </div>
      )}
      {reviewError ? <ErrorMessage error={reviewError} onRetry={() => void load()} /> : null}
      {review && review.items.length > 0 && (
        <ReviewList items={review.items} sections={result?.sections ?? []} onlyMistakes={onlyMistakes} onOnlyMistakes={setOnlyMistakes}
          passageDisplay={review.passage_display ?? result?.passage_display ?? null} />
      )}
      {review && review.items.length === 0 && <p className="text-sm text-slate-600">{t("results.noReview")}</p>}
    </div>
  );
}

const MISTAKES = new Set<Correctness>(["incorrect", "partial", "unanswered"]);

/**
 * The answer review (S7b, R4): grouped by section (folding groups, all open), with an "only mistakes" filter that is
 * off by default ("Review mistakes" turns it on). Every card and its content are unchanged; numbering stays global;
 * each card carries `id="item-{position}"` (SF-1, problem 3).
 */
function ReviewList({ items, sections, passageDisplay, onlyMistakes, onOnlyMistakes }: {
  items: ReviewItemOut[];
  sections: AttemptResultOut["sections"];
  /** Phase 8b S3: renderer from the review payload (null: course template). */
  passageDisplay: PassageDisplay | null;
  onlyMistakes: boolean;
  onOnlyMistakes: (v: boolean) => void;
}) {
  const { t } = useTranslation();
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
  const sectionName = useResultSectionName(sections); // the same names as the section breakdown above
  const show = (it: ReviewItemOut) => !onlyMistakes || (it.correctness !== null && MISTAKES.has(it.correctness));
  const anyShown = items.some(show);
  const grouped = groups.length > 1;
  const card = (e: { item: ReviewItemOut; number: number }) => (
    <ReviewItemCard key={e.item.position} anchorId={`item-${e.item.position}`} item={e.item} number={e.number} passageDisplay={passageDisplay} />
  );

  return (
    <section id={REVIEW_ID} className="scroll-mt-20 space-y-4" aria-label={t("results.reviewTitle")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* stays h3: the ORT DOM check counts one level-3 heading per card plus this title */}
        <h3 className="text-lg font-semibold text-slate-900">{t("results.reviewTitle")}</h3>
        <button
          type="button"
          aria-pressed={onlyMistakes}
          onClick={() => onOnlyMistakes(!onlyMistakes)}
          className={cn(
            "inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-semibold transition-colors sm:min-h-9",
            focusRing,
            onlyMistakes ? "border-brand-200 bg-brand-50 text-brand-800 hover:bg-brand-100" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
          )}
        >
          {t("results.review.onlyMistakes")}
        </button>
      </div>
      {!anyShown && <p role="status" className="rounded-control border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{t("results.review.noMistakes")}</p>}
      {grouped
        ? groups.map((g) => {
          const shown = g.entries.filter((e) => show(e.item));
          if (shown.length === 0) return null;
          const correct = g.entries.filter((e) => e.item.correctness === "correct").length;
          return (
            <details key={g.pos} open className="group space-y-4">
              <summary className={cn("flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-control border border-slate-200 bg-white px-4 py-2 shadow-sm [&::-webkit-details-marker]:hidden", focusRing)}>
                <span className="font-semibold text-slate-900">{sectionName(g.pos)}</span>
                <span className="flex shrink-0 items-center gap-2 text-sm text-slate-700">
                  {t("results.review.sectionSummary", { correct, total: g.entries.length })}
                  <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
                </span>
              </summary>
              <div className="space-y-4">{shown.map(card)}</div>
            </details>
          );
        })
        : groups.flatMap((g) => g.entries).filter((e) => show(e.item)).map(card)}
    </section>
  );
}
