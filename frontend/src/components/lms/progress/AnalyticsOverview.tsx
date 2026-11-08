"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Bookmark, Flame, ListChecks, Target } from "lucide-react";
import { ErrorState, LinkButton, Mascot, Skeleton, StatTile, cn } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { useCourse } from "@/components/lms/CourseContext";
import { useTranslation } from "@/lib/i18n/context";
import { listSaved, type ActivityDays, type ActivityOut, type ProgressOut } from "@/lib/lms/progress";
import { loadAnalytics } from "@/lib/lms/pageData"; // PERFORMANCE_AUDIT S3
import { ActiveHours, ActivityBars, AllTimeHeatmap, Sessions, StudyTime } from "./ActivityCards";
import { AnalyticsCard } from "./AnalyticsCard";
import { GoalInput } from "./GoalInput";
import { TopicAccuracy, WeakTopics } from "./TopicCards";
import { HEATMAP_MIN_DAYS, PERIODS, namedTopics, toPercent } from "./analyticsData";

/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): the analytics page body. Three requests in parallel (progress and activity of
 * the period, the first page of saved questions for the count); the period reloads progress and activity together, so
 * every number on the page has one definition and one period (STUDENT_UI_FIX_PLAN 4.2).
 * Free for everyone (D8): `LOCK_ANALYTICS` moves the weak-topic and by-topic cards behind the pass when the owner says so.
 */
const LOCK_ANALYTICS = false;
/** Active days in the period before the history cards (answers, study time, active hours, sessions) appear (U8, U9, §5.1 c). */
const HISTORY_DAYS = 3;

/** The period buttons ("7 дней", "30 дней", "90 дней", "Год"); a toggle group, one pressed. */
export function PeriodPicker({ value, onChange }: { value: ActivityDays; onChange: (d: ActivityDays) => void }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("progress.analytics.period.label")} className="inline-flex rounded-control border border-slate-200 bg-white p-1">
      {PERIODS.map((d) => (
        <button key={d} type="button" aria-pressed={value === d} onClick={() => onChange(d)}
          className={cn("min-h-10 rounded-lg px-3 text-sm font-semibold leading-5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1",
            value === d ? "bg-navy-800 text-white" : "text-slate-700 hover:bg-slate-100")}>
          {t(`progress.analytics.period.d${d}`)}
        </button>
      ))}
    </div>
  );
}

/** A number's place while it loads (inline: it sits inside the tile's text). */
const NumberSkeleton = () => (
  <span aria-hidden="true" className="inline-block h-6 w-14 animate-pulse rounded-lg bg-slate-200 align-middle motion-reduce:animate-none" />
);

/** PERFORMANCE_AUDIT S3: the tiles' frames (icons and labels) at once, skeletons only for the numbers and the charts. */
function Loading({ period, saved }: { period: ActivityDays; saved: string | null }) {
  const { t } = useTranslation();
  const inPeriod = t(`progress.analytics.period.in.d${period}`);
  return (
    <div className="space-y-4 sm:space-y-6" aria-busy="true">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={<ListChecks />} label={t("progress.analytics.tiles.answered")} value={<NumberSkeleton />} hint={inPeriod} />
        <StatTile icon={<Target />} label={t("progress.analytics.tiles.accuracy")} value={<NumberSkeleton />} hint={inPeriod} />
        <StatTile icon={<Bookmark />} label={t("progress.analytics.tiles.saved")}
          value={saved === null ? <NumberSkeleton /> : <span className="tabular-nums">{saved}</span>} hint={t("progress.analytics.tiles.savedHint")} />
        <StatTile icon={<Flame />} label={t("progress.analytics.tiles.streak")} value={<NumberSkeleton />} />
      </div>
      <Skeleton className="h-56 w-full rounded-card" />
      <Skeleton className="h-56 w-full rounded-card" />
    </div>
  );
}

/** `examPrep`: the percent goal card is hidden (those courses set a scaled target on Главная). */
export function AnalyticsOverview({ courseId, period, examPrep = false }: { courseId: string; period: ActivityDays; examPrep?: boolean }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const [progress, setProgress] = useState<ProgressOut | null>(null);
  const [activity, setActivity] = useState<ActivityOut | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const loadBase = useCallback((signal?: AbortSignal) => {
    // the count is a convenience: a failure leaves the tile at "-"
    listSaved(courseId, null, signal, 50)
      .then((p) => { if (!signal?.aborted) setSaved(`${p.items.length}${p.next_cursor ? "+" : ""}`); })
      .catch(() => undefined);
  }, [courseId]);

  const loadActivity = useCallback(async (signal?: AbortSignal) => {
    setBusy(true);
    try {
      // PERFORMANCE_AUDIT S3: an answer the shell link's hover/focus asked moments ago is used (or its request shared); otherwise asked again
      const [p, a] = await loadAnalytics(courseId, period);
      if (!signal?.aborted) { setProgress(p); setActivity(a); }
    } catch (e) {
      if (!signal?.aborted) setError(e);
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }, [courseId, period]);

  useEffect(() => {
    const c = new AbortController();
    loadBase(c.signal);
    return () => c.abort();
  }, [loadBase]);
  useEffect(() => {
    const c = new AbortController();
    void loadActivity(c.signal);
    return () => c.abort();
  }, [loadActivity]);

  const retry = () => { setError(null); loadBase(); void loadActivity(); };

  if (error) return <ErrorState message={errorText(error)} onRetry={retry} />;
  if (!progress || !activity) return <Loading period={period} saved={saved} />;

  const answered = activity.totals.answered;
  const graded = activity.totals.graded;
  const topics = namedTopics(progress.by_topic);
  // correct counts a partial answer as half: one decimal at most
  const correctText = Number.isInteger(activity.totals.correct) ? String(activity.totals.correct) : activity.totals.correct.toFixed(1);
  // zero answers ever (the heatmap is all time): only the hero below
  const nothingYet = answered === 0 && activity.heatmap.length === 0;
  const history = activity.days.filter((d) => d.answered > 0).length >= HISTORY_DAYS;
  // U9 (review 11): the calendar only after a week of active days
  const calendar = activity.heatmap.filter((d) => d.answered > 0).length >= HEATMAP_MIN_DAYS;
  const practiceHref = course.features?.practice ? `/${lang}/courses/${courseId}/practice` : null;
  const split = !!course.template?.section_keys?.length;
  const pct = (v: number | null) => (v === null ? "-" : `${Math.round(v)} %`);

  return (
    <div className={cn("space-y-4 transition-opacity sm:space-y-6", busy && "opacity-60")} aria-busy={busy}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={<ListChecks />} label={t("progress.analytics.tiles.answered")} value={<span className="tabular-nums">{answered}</span>}
          hint={t(`progress.analytics.period.in.d${period}`)} />
        <StatTile icon={<Target />} label={t("progress.analytics.tiles.accuracy")}
          value={<span className="tabular-nums">{graded > 0 ? `${toPercent(activity.totals.accuracy)} %` : "-"}</span>}
          hint={graded > 0 ? t("progress.analytics.tiles.accuracyHint", { correct: correctText, total: graded }) : t(`progress.analytics.period.in.d${period}`)} />
        <StatTile icon={<Bookmark />} label={t("progress.analytics.tiles.saved")} value={<span className="tabular-nums">{saved ?? "-"}</span>}
          hint={t("progress.analytics.tiles.savedHint")} />
        <StatTile icon={<Flame />} label={t("progress.analytics.tiles.streak")}
          value={<span className="whitespace-nowrap">{t("progress.analytics.tiles.streakValue", { count: activity.streak_current })}</span>}
          hint={t("progress.analytics.tiles.streakBest", { count: activity.streak_longest })} />
      </div>

      {nothingYet && (
        <section className="flex flex-col items-center gap-4 rounded-card border border-brand-100 bg-brand-50 p-5 text-center sm:flex-row sm:text-left">
          <Mascot pose="hello" size={88} />
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold leading-7 text-slate-900">{t("progress.analytics.empty.pageTitle")}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-700">{t("progress.analytics.empty.pageBody")}</p>
          </div>
          <LinkButton href={`/${lang}/courses/${courseId}`} className="shrink-0">{t("progress.analytics.empty.pageAction")}</LinkButton>
        </section>
      )}

      {/* zero answers: the hero above is the whole story; "Пока мало данных" only once there is some data (one mascot, one action) */}
      {!nothingYet && <WeakTopics topics={topics} ready={progress.weak_topics_ready} practiceHref={practiceHref} testsHref={`/${lang}/courses/${courseId}`} locked={LOCK_ANALYTICS} />}
      {/* U9 (review 11): the answers chart too needs history (a chart of one bar says nothing) */}
      {history && <ActivityBars data={activity} period={period} />}
      {!nothingYet && <TopicAccuracy topics={topics} split={split} locked={LOCK_ANALYTICS} />}
      {/* U8 (§5.1 c): study time, active hours and sessions need history; before that they are not drawn at all */}
      {history && <StudyTime data={activity} period={period} />}
      {history && (
        <div className="grid min-w-0 gap-4 sm:gap-6 lg:grid-cols-2">
          <ActiveHours data={activity} />
          <Sessions data={activity} />
        </div>
      )}
      {calendar && <AllTimeHeatmap data={activity} />}

      {!examPrep && <AnalyticsCard title={t("progress.analytics.goal.title")}
        subtitle={progress.current_percent === null && progress.goal_percent === null
          ? t("progress.analytics.goal.hint")
          : t("progress.analytics.goal.subtitle", { current: pct(progress.current_percent), goal: pct(progress.goal_percent) })}>
        <GoalInput courseId={courseId} value={progress.goal_percent} onChange={(v) => setProgress({ ...progress, goal_percent: v })} />
      </AnalyticsCard>}
    </div>
  );
}
