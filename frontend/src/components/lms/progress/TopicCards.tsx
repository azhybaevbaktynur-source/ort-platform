"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Meter, SectionTag, accuracyBand, cn, focusRing, type AccuracyBand } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { AnalyticsCard, BandLegend, CardEmpty, NotEnoughData } from "./AnalyticsCard";
import { TOPIC_MIN_GRADED, isGraded, toPercent, topicGroup, twoDigits, weakestTopics, type NamedTopic, type TopicGroup } from "./analyticsData";

/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): "5 слабых тем" and accuracy by topic (math vs language). Both take `locked`
 * so the owner can move them behind the pass later without a layout change (D8: free today).
 * U9 (STUDENT_UI_REVIEW 11): a topic shows a percent and a band only from 5 answers (else "Мало данных", grey); the
 * weak-topic card only once 3 topics are graded; the band legend once, under the last topic card.
 */

const RING: Record<AccuracyBand, string> = { low: "#f43f5e", mid: "#f59e0b", high: "#10b981" };
const BAND_TEXT: Record<AccuracyBand, string> = { low: "text-acc-low-text", mid: "text-acc-mid-text", high: "text-acc-high-text" };

/** A small progress ring; decoration next to the written percent. */
function Ring({ percent }: { percent: number }) {
  const r = 15;
  const c = 2 * Math.PI * r;
  const band = accuracyBand(percent);
  return (
    <svg aria-hidden="true" width="40" height="40" viewBox="0 0 40 40" className="shrink-0 -rotate-90">
      <circle cx="20" cy="20" r={r} fill="none" stroke="#f1f5f9" strokeWidth="5" />
      <circle cx="20" cy="20" r={r} fill="none" stroke={RING[band]} strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${(Math.max(percent, 2) / 100) * c} ${c}`} />
    </svg>
  );
}

export function WeakTopics({ topics, ready, practiceHref, testsHref, locked = false }: { topics: NamedTopic[]; ready: boolean; practiceHref: string | null; testsHref: string; locked?: boolean }) {
  const { t } = useTranslation();
  const weak = weakestTopics(topics, ready);
  if (weak === null) {
    return (
      <AnalyticsCard locked={locked} title={t("progress.analytics.weak.titleEmpty")}>
        <NotEnoughData body={t("progress.analytics.notEnough.weakBody")} href={testsHref} />
      </AnalyticsCard>
    );
  }
  return (
    <AnalyticsCard locked={locked}
      title={weak.length ? t("progress.analytics.weak.title", { count: weak.length }) : t("progress.analytics.weak.titleEmpty")}
      subtitle={weak.length ? t("progress.analytics.weak.subtitle") : undefined}>
      {weak.length === 0 ? (
        <CardEmpty pose="thinking" hint={t("progress.analytics.weak.empty")} />
      ) : (
        <ol className="divide-y divide-slate-100">
          {weak.map((tp, i) => {
            const p = toPercent(tp.accuracy);
            const band = accuracyBand(p);
            return (
              <li key={`${tp.section}:${tp.topic}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 first:pt-0 last:pb-0 sm:flex-nowrap">
                <span aria-hidden="true" className="w-6 shrink-0 text-sm font-semibold tabular-nums text-slate-500 sm:w-7">{twoDigits(i + 1)}</span>
                <div className="min-w-0 flex-1">
                  <p className="break-words text-base font-semibold leading-6 text-slate-900">{tp.topic}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm leading-5 text-slate-600">
                    {tp.section && <SectionTag section={tp.section} />}
                    <span>{t("progress.analytics.answers", { count: tp.total })}</span>
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Ring percent={p} />
                  <span className="flex flex-col leading-tight">
                    <span className={cn("text-base font-bold tabular-nums", BAND_TEXT[band])}>{p} %</span>
                    <span className="text-xs text-slate-600">{t(`progress.analytics.band.${band}`)}</span>
                  </span>
                </div>
                {practiceHref && (
                  <Link href={practiceHref}
                    className={cn("ml-auto inline-flex min-h-11 shrink-0 basis-full items-center justify-end gap-1 rounded-control px-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 sm:ml-2 sm:basis-auto", focusRing)}>
                    {t("progress.analytics.weak.practice")}
                    <span className="sr-only">: {tp.topic}</span>
                    <ArrowRight aria-hidden="true" className="h-4 w-4" />
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </AnalyticsCard>
  );
}

function TopicRows({ topics }: { topics: NamedTopic[] }) {
  const { t } = useTranslation();
  // graded topics first (weakest first), then the ones with too few answers (most answers first)
  const rows = topics.filter((x) => x.total > 0).slice().sort((a, b) =>
    Number(isGraded(b)) - Number(isGraded(a)) || (isGraded(a) ? a.accuracy - b.accuracy : 0) || b.total - a.total);
  return (
    <ul className="space-y-3">
      {rows.map((tp) => (
        <li key={`${tp.section}:${tp.topic}`} className="min-w-0">
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3">
            <span className="min-w-0 break-words text-sm font-medium leading-5 text-slate-900">{tp.topic}</span>
            <span className="shrink-0 text-xs leading-4 text-slate-600">{t("progress.analytics.answers", { count: tp.total })}</span>
          </div>
          {isGraded(tp) ? (
            <div className="flex items-center gap-3">
              <Meter className="flex-1" value={toPercent(tp.accuracy)} showValue={false} label={t("progress.analytics.topics.meter", { topic: tp.topic })} />
              <span aria-hidden="true" className={cn("shrink-0 whitespace-nowrap text-right text-sm font-semibold tabular-nums", BAND_TEXT[accuracyBand(toPercent(tp.accuracy))])} style={{ minWidth: "3.25rem" }}>
                {toPercent(tp.accuracy)} %
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="h-2 flex-1 rounded-full bg-slate-100" />
              <span className="shrink-0 whitespace-nowrap text-right text-xs font-medium leading-4 text-slate-500">{t("progress.analytics.lowDataCount", { graded: tp.graded, min: TOPIC_MIN_GRADED })}</span>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Accuracy by topic: a math card and a language card on ORT-like courses, one card on general courses. */
export function TopicAccuracy({ topics, split, locked = false }: { topics: NamedTopic[]; split: boolean; locked?: boolean }) {
  const { t } = useTranslation();
  const by: Record<TopicGroup, NamedTopic[]> = { math: [], language: [], other: [] };
  for (const tp of topics) by[topicGroup(tp.section)].push(tp);
  const useSplit = split || by.math.length > 0 || by.language.length > 0;
  const groups: TopicGroup[] = useSplit ? ["math", "language", ...(by.other.length ? ["other" as const] : [])] : ["other"];
  // the band legend once: under the last card that shows a graded topic
  const legendIn = [...groups].reverse().find((g) => by[g].some(isGraded)) ?? null;
  return (
    <div className={cn("grid min-w-0 gap-4", groups.length > 1 && "lg:grid-cols-2")}>
      {groups.map((g) => (
        <AnalyticsCard key={g} locked={locked} className={g === "other" && groups.length === 3 ? "lg:col-span-2" : undefined}
          title={t(useSplit ? `progress.analytics.topics.${g}` : "progress.analytics.topics.all")}
          subtitle={t("progress.analytics.topics.subtitle")}>
          {/* no answers in this group: one quiet line (the mascot and the action live in the weak-topics card) */}
          {by[g].every((x) => x.total === 0) ? (
            <p className="text-sm leading-5 text-slate-600">{t("progress.analytics.notEnough.topicsBody")}</p>
          ) : (
            <>
              <TopicRows topics={by[g]} />
              {g === legendIn && <BandLegend className="mt-4 border-t border-slate-100 pt-3" />}
            </>
          )}
        </AnalyticsCard>
      ))}
    </div>
  );
}
