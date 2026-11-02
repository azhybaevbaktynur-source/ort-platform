"use client";

// Phase 10 S5: quiz statistics page body (PHASE_10_DESIGN 5). Tiles, histogram, version selector, item table.
// While the server computes (`state: computing`) the summary is refetched after 5 s, at most 3 times.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getQuizStats, type QuizStats } from "@/lib/lms/statistics";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Histogram } from "@/components/lms/analytics/Histogram";
import { ItemStatsTable } from "@/components/lms/analytics/ItemStatsTable";
import { EmptyState, LoadingState, PageHeader, Select } from "@/components/ui";

const REFETCH_MS = 5000;
const REFETCH_MAX = 3;

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <dt className="text-xs font-medium text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

export function QuizStatsView({ assessmentId }: { assessmentId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const [versionId, setVersionId] = useState<string | null>(null);
  const [stats, setStats] = useState<QuizStats | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const retries = useRef(0);

  const load = useCallback(async () => {
    setError(null);
    try { setStats(await getQuizStats(course.id, assessmentId, versionId)); }
    catch (e) { setError(e); } finally { setLoading(false); }
  }, [course.id, assessmentId, versionId]);

  useEffect(() => { retries.current = 0; setLoading(true); void load(); }, [load]);

  useEffect(() => {
    if (stats?.state !== "computing" || retries.current >= REFETCH_MAX) return;
    const id = setTimeout(() => { retries.current += 1; void load(); }, REFETCH_MS);
    return () => clearTimeout(id);
  }, [stats, load]);

  const pct = (v: number | null) => (v === null ? "-" : `${v.toFixed(1)}%`);
  const hasData = stats !== null && stats.attempts_counted > 0 && stats.mean_percent !== null;

  return (
    <div>
      <PageHeader
        title={t("quizStats.title")}
        breadcrumbs={[
          { label: t("quizStats.analytics"), href: `/${lang}/courses/${course.id}/analytics` },
          { label: t("quizStats.title") },
        ]}
      />
      <ErrorMessage error={error} onRetry={() => void load()} />
      {loading && !stats ? <LoadingState rows={4} /> : stats && (
        <>
          {stats.versions.length > 1 && (
            <Select
              label={t("quizStats.versionLabel")}
              value={stats.version_id ?? ""}
              onChange={(ev) => setVersionId(ev.target.value || null)}
              options={stats.versions.map((v) => ({
                value: v.version_id, label: t("quizStats.versionOption", { no: v.version_no ?? 0, n: v.attempts }),
              }))}
              containerClassName="mb-4 w-full sm:w-72"
            />
          )}
          {stats.state === "empty" || !hasData ? (
            stats.state === "computing" ? <LoadingState label={t("quizStats.computing")} rows={3} /> : <EmptyState mascot="working" title={t("quizStats.empty")} />
          ) : (
            <>
              {stats.state === "stale" && stats.computed_at && (
                <p role="status" className="mb-3 text-sm text-slate-700">{t("quizStats.stale", { date: fmtShortDateTime(stats.computed_at, lang) })}</p>
              )}
              {stats.state === "computing" && <p role="status" className="mb-3 text-sm text-slate-700">{t("quizStats.refreshing")}</p>}
              <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Tile label={t("quizStats.tileAttempts")} value={String(stats.attempts_counted)} />
                <Tile label={t("quizStats.tileMean")} value={pct(stats.mean_percent)} />
                <Tile label={t("quizStats.tileMedian")} value={pct(stats.median_percent)} />
                <Tile label={t("quizStats.tileSpread")} value={pct(stats.stddev_percent)} />
              </dl>
              <section aria-labelledby="qs-dist" className="mt-6 rounded-xl border border-slate-200 bg-white p-4">
                <h2 id="qs-dist" className="mb-3 text-lg font-semibold text-slate-900">{t("quizStats.distribution")}</h2>
                <Histogram buckets={stats.distribution} />
              </section>
              <ItemStatsTable
                courseId={course.id} assessmentId={assessmentId} versionId={stats.version_id}
                reloadKey={`${stats.version_id}:${stats.computed_at}`}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
