"use client";

// Phase 10 S6: shared pieces of the course and organization analytics pages (tiles + histogram, percent format).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { StatTile } from "@/components/ui";
import { LoadError } from "@/components/lms/org/OrgUi";
import { LoadingState } from "@/components/ui";
import type { ScoreOut, SubmissionCountsOut } from "@/lib/lms/analytics";
import { Histogram } from "./Histogram";

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${v}%`);

/** Loads one object once; shows a skeleton, an error with retry, or the render prop. */
export function useLoaded<T>(load: () => Promise<T>, deps: React.DependencyList) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [loading, setLoading] = React.useState(true);
  const run = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setData(await load()); } catch (e) { setError(e); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  React.useEffect(() => { void run(); }, [run]);
  return { data, error, loading, reload: run };
}

export function Loaded({ loading, error, data, reload, children }: {
  loading: boolean; error: unknown; data: unknown; reload: () => void; children: React.ReactNode;
}) {
  if (error && !data) return <LoadError error={error} onRetry={reload} />;
  if (loading && !data) return <LoadingState rows={3} />;
  return <>{children}</>;
}

export function ScoreAndSubmissions({ score, submissions, extra }: {
  score: ScoreOut; submissions: SubmissionCountsOut; extra: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {extra}
        <StatTile label={t("analytics.meanScore")} value={pct(score.mean_percent)} hint={t("analytics.scoredStudents", { n: score.count })} />
        <StatTile label={t("analytics.graded")} value={submissions.graded} />
        <StatTile label={t("analytics.pendingReview")} value={submissions.pending_review} />
        <StatTile label={t("analytics.missing")} value={submissions.missing} />
      </div>
      <section className="mt-6" aria-labelledby="an-dist">
        <h2 id="an-dist" className="text-base font-semibold text-slate-900">{t("analytics.distribution")}</h2>
        {score.count > 0
          ? <div className="mt-2"><Histogram distribution={score.distribution} label={t("analytics.distribution")} /></div>
          : <p className="mt-2 text-sm text-slate-600">{t("analytics.noScores")}</p>}
      </section>
    </>
  );
}
