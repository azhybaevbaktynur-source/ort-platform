"use client";

import React, { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, Skeleton, StatTile, Table, type TableColumn } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getProgress, type ProgressOut, type TopicStat } from "@/lib/lms/progress";
import { GoalInput } from "./GoalInput";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "-" : `${Math.round(v)}%`);

/** Trend as small CSS bars, oldest first; a thin line marks the goal. */
function Trend({ data }: { data: ProgressOut }) {
  const { lang, t } = useTranslation();
  const goal = data.goal_percent;
  return (
    <section aria-label={t("progress.trend")} className="rounded-2xl border border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-base font-semibold text-slate-900">{t("progress.trend")}</h2>
      <div className="relative flex h-32 items-end gap-1" role="list">
        {goal !== null && <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 border-t border-dashed border-gold-500" style={{ bottom: `${goal}%` }} />}
        {data.trend.map((p) => {
          const title = `${pickLocalized(p.title, lang) || t("assessments.untitled")}, ${pct(p.percent)}${p.at ? `, ${fmtShortDateTime(p.at, lang)}` : ""}`;
          return (
            <div key={p.attempt_id} role="listitem" title={title} aria-label={title} className="flex h-full min-w-0 flex-1 items-end">
              <span className={`block w-full rounded-t ${p.practice ? "bg-brand-300" : "bg-brand-600"}`} style={{ height: `${Math.max(2, Math.min(100, p.percent))}%` }} />
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function ProgressOverview({ courseId, onOpenMistakes }: { courseId: string; onOpenMistakes: () => void }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const [data, setData] = useState<ProgressOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    try {
      setData(await getProgress(courseId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <ErrorState message={errorText(error)} onRetry={() => void load()} />;
  if (!data) return <div className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-40 w-full" /></div>;

  const columns: TableColumn<TopicStat>[] = [
    { key: "topic", header: t("progress.topics.topic"), primary: true, cell: (r) => r.topic },
    { key: "section", header: t("progress.topics.section"), cell: (r) => r.section ?? "-", hideOnMobile: true },
    { key: "accuracy", header: t("progress.topics.accuracy"), align: "right", nowrap: true, cell: (r) => pct(r.accuracy * 100) },
    { key: "total", header: t("progress.topics.questions"), align: "right", nowrap: true, cell: (r) => r.total },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label={t("progress.tiles.current")} value={pct(data.current_percent)} />
        <StatTile label={t("progress.tiles.goal")} value={pct(data.goal_percent)} />
        <StatTile label={t("progress.tiles.attempts")} value={data.attempts_total} />
        <StatTile label={t("progress.tiles.mistakes")} value={data.open_mistakes}
          hint={data.open_mistakes > 0 ? <button type="button" onClick={onOpenMistakes} className="font-medium text-brand-700 hover:underline">{t("progress.tiles.openNotebook")}</button> : undefined} />
      </div>
      <GoalInput courseId={courseId} value={data.goal_percent} onChange={(v) => setData({ ...data, goal_percent: v })} />
      {data.attempts_total === 0 ? (
        <EmptyState mascot="reading" title={t("progress.empty")} />
      ) : (
        <>
          <Trend data={data} />
          {data.by_section.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-base font-semibold text-slate-900">{t("progress.sections")}</h2>
              <ul className="space-y-2">
                {data.by_section.map((s) => (
                  <li key={s.section} className="flex items-center gap-3 text-sm">
                    <span className="w-28 shrink-0 truncate text-slate-700">{s.section}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
                      <span className="block h-full rounded-full bg-brand-600" style={{ width: `${Math.round(s.accuracy * 100)}%` }} />
                    </span>
                    <span className="w-12 shrink-0 text-right font-medium text-slate-900">{pct(s.accuracy * 100)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.by_topic.length > 0 && (
            <Table caption={t("progress.topics.title")} showCaption columns={columns} rows={data.by_topic} rowKey={(r) => `${r.section}:${r.topic}`} />
          )}
        </>
      )}
    </div>
  );
}
