"use client";

import React, { useMemo, useState } from "react";
import { Button, accuracyBand, cn } from "@/components/ui";
import { fmtDuration } from "@/components/lms/home/format";
import { parseApiDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n/context";
import type { ActivityDays, ActivityOut } from "@/lib/lms/progress";
import { AnalyticsCard, CardEmpty, ChartScroll, Legend, type LegendItem } from "./AnalyticsCard";
import { MonthHeatmap } from "./MonthHeatmap";
import {
  CORRECT_FILL, OTHER_FILL, SECTION_FILL, SECTION_ORDER, WRONG_STYLE,
  bucketize, dayMs, niceCount, niceMax, type Bucket,
} from "./analyticsData";

/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): activity charts as plain CSS bars (no chart library). Each chart is one image
 * for screen readers (a summary sentence); each bar has a tooltip with its numbers; the legend says in words what each
 * colour is, and wrong answers are also hatched. On a phone a wide chart scrolls inside its card only.
 */

const PLOT_H = "h-40";
const locale = (lang: string) => (lang === "en" ? "en-GB" : lang);

function fmtDay(iso: string, lang: string): string {
  try {
    return new Date(dayMs(iso)).toLocaleDateString(locale(lang), { day: "numeric", month: "short", timeZone: "UTC" });
  } catch {
    return iso;
  }
}
function fmtRange(b: Bucket, lang: string): string {
  return b.start === b.end ? fmtDay(b.start, lang) : `${fmtDay(b.start, lang)} – ${fmtDay(b.end, lang)}`;
}
function fmtTime(iso: string, lang: string): string {
  const d = parseApiDate(iso);
  return d ? d.toLocaleTimeString(locale(lang), { hour: "2-digit", minute: "2-digit" }) : "";
}

/** Indexes that get an x label: every bar up to 7, else about five spread evenly. */
function tickIndexes(n: number): number[] {
  if (n <= 7) return Array.from({ length: n }, (_, i) => i);
  const k = 3;
  return Array.from(new Set(Array.from({ length: k + 1 }, (_, i) => Math.round((i * (n - 1)) / k))));
}

/** Y labels on the left, recessive grid lines, bars in a horizontally scrolling plot, x labels under it. */
function BarFrame({ n, minStep, yTop, yMid, label, xLabel, ticks: fixedTicks, overlay, children }: {
  n: number;
  /** Bars that get an x label (default: about five spread evenly). */
  ticks?: number[];
  /** Narrowest bar step in px; below it the plot scrolls inside the card. */
  minStep: number;
  yTop: string;
  yMid: string;
  label: string;
  xLabel: (i: number) => string;
  overlay?: React.ReactNode;
  children: React.ReactNode;
}) {
  const ticks = fixedTicks ?? tickIndexes(n);
  return (
    <div className="flex min-w-0 gap-2">
      <div aria-hidden="true" className={cn("relative shrink-0 text-right text-xs leading-4 text-slate-500", PLOT_H)} style={{ width: "3.25rem" }}>
        <span className="absolute right-0 top-0 -translate-y-1/2 whitespace-nowrap">{yTop}</span>
        <span className="absolute right-0 top-1/2 -translate-y-1/2 whitespace-nowrap">{yMid}</span>
        <span className="absolute bottom-0 right-0 translate-y-1/2">0</span>
      </div>
      <div className="min-w-0 flex-1">
        <ChartScroll minWidth={n * minStep}>
          <div role="img" aria-label={label} className={cn("relative", PLOT_H)}>
            <span aria-hidden="true" className="absolute inset-x-0 top-0 border-t border-slate-100" />
            <span aria-hidden="true" className="absolute inset-x-0 top-1/2 border-t border-slate-100" />
            <span aria-hidden="true" className="absolute inset-x-0 bottom-0 border-t border-slate-300" />
            <div aria-hidden="true" className="absolute inset-0 flex items-end gap-[2px]">{children}</div>
            {overlay}
          </div>
          <div aria-hidden="true" className="relative mt-1.5 h-4 text-xs leading-4 text-slate-600">
            {ticks.map((i) => {
              const edge = i === 0 ? "translate-x-0" : i === n - 1 ? "-translate-x-full" : "-translate-x-1/2";
              const left = i === 0 ? 0 : i === n - 1 ? 100 : ((i + 0.5) / n) * 100;
              return <span key={i} className={cn("absolute top-0 whitespace-nowrap", edge)} style={{ left: `${left}%` }}>{xLabel(i)}</span>;
            })}
          </div>
        </ChartScroll>
      </div>
    </div>
  );
}

/** A bar column: the whole height is the hover target, the segments sit at the bottom. */
function Column({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div title={title} className="flex h-full min-w-0 flex-1 flex-col justify-end gap-[2px] rounded-t-[4px] hover:bg-slate-50">
      {children}
    </div>
  );
}

export function ActivityBars({ data, period }: { data: ActivityOut; period: ActivityDays }) {
  const { lang, t } = useTranslation();
  const { unit, buckets } = useMemo(() => bucketize(data.days, period), [data.days, period]);
  const top = niceCount(Math.max(0, ...buckets.map((b) => b.correct + b.wrong)));
  const legend: LegendItem[] = [
    { key: "correct", color: CORRECT_FILL, label: t("progress.analytics.activity.correct") },
    { key: "wrong", style: WRONG_STYLE, label: t("progress.analytics.activity.wrong") },
  ];
  return (
    <AnalyticsCard title={t("progress.analytics.activity.title")}
      subtitle={t(unit === "week" ? "progress.analytics.activity.byWeek" : "progress.analytics.activity.byDay")}
      aside={data.totals.answered > 0 ? <Legend items={legend} label={t("progress.analytics.legend.label")} /> : undefined}>
      {data.totals.answered === 0 ? (
        <CardEmpty pose="working" hint={t("progress.analytics.activity.empty")} />
      ) : (
        <BarFrame n={buckets.length} minStep={unit === "week" ? 10 : 7} yTop={String(top)} yMid={String(top / 2)}
          label={t("progress.analytics.activity.summary", { answered: data.totals.answered, correct: data.totals.correct, wrong: data.days.reduce((s, d) => s + d.wrong, 0) })}
          xLabel={(i) => fmtDay(buckets[i].start, lang)}>
          {buckets.map((b) => (
            <Column key={b.start} title={t("progress.analytics.activity.bar", { date: fmtRange(b, lang), correct: b.correct, wrong: b.wrong })}>
              {b.wrong > 0 && <span className="block w-full rounded-t-[3px]" style={{ height: `${(b.wrong / top) * 100}%`, ...WRONG_STYLE }} />}
              {b.correct > 0 && <span className={cn("block w-full", b.wrong === 0 && "rounded-t-[3px]")} style={{ height: `${(b.correct / top) * 100}%`, background: CORRECT_FILL }} />}
            </Column>
          ))}
        </BarFrame>
      )}
    </AnalyticsCard>
  );
}

export function StudyTime({ data, period }: { data: ActivityOut; period: ActivityDays }) {
  const { lang, t } = useTranslation();
  const { unit, buckets } = useMemo(() => bucketize(data.days, period), [data.days, period]);
  const total = buckets.reduce((s, b) => s + b.seconds, 0);
  const active = buckets.filter((b) => b.seconds > 0);
  const avg = active.length ? total / active.length : 0;
  const topMin = niceMax(Math.max(0, ...buckets.map((b) => b.seconds)) / 60, 10);
  const top = topMin * 60;
  const keys = useMemo(() => {
    const seen = new Set<string>();
    for (const b of buckets) for (const [k, v] of Object.entries(b.sections)) if (v > 0) seen.add(k);
    const known = SECTION_ORDER.filter((k) => seen.has(k));
    const other = [...seen].filter((k) => !SECTION_FILL[k]);
    return { known: known as string[], other: other.length > 0 };
  }, [buckets]);
  const sectionName = (k: string) => (k && SECTION_FILL[k] ? t(`sections.${k}`) : t("progress.analytics.time.other"));
  const legend: LegendItem[] = [
    ...keys.known.map((k) => ({ key: k, color: SECTION_FILL[k], label: sectionName(k) })),
    ...(keys.other ? [{ key: "other", color: OTHER_FILL, label: t("progress.analytics.time.other") }] : []),
    { key: "avg", line: true, label: t("progress.analytics.time.avg", { value: fmtDuration(avg, t) }) },
  ];
  const segs = (b: Bucket) => {
    const out: { key: string; s: number; color: string }[] = [];
    for (const k of keys.known) if (b.sections[k]) out.push({ key: k, s: b.sections[k], color: SECTION_FILL[k] });
    const rest = Object.entries(b.sections).filter(([k]) => !SECTION_FILL[k]).reduce((s, [, v]) => s + v, 0);
    if (rest > 0) out.push({ key: "other", s: rest, color: OTHER_FILL });
    return out.reverse(); // top first; the first section sits on the baseline
  };
  return (
    <AnalyticsCard title={t("progress.analytics.time.title")}
      subtitle={t(unit === "week" ? "progress.analytics.time.byWeek" : "progress.analytics.time.byDay")}>
      {total === 0 ? (
        <CardEmpty pose="reading" hint={t("progress.analytics.time.empty")} />
      ) : (
        <>
          <BarFrame n={buckets.length} minStep={unit === "week" ? 10 : 7} yTop={fmtDuration(top, t)} yMid={fmtDuration(top / 2, t)}
            label={t("progress.analytics.time.summary", { total: fmtDuration(total, t), avg: fmtDuration(avg, t) })}
            xLabel={(i) => fmtDay(buckets[i].start, lang)}
            overlay={avg > 0 ? <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 border-t-2 border-dashed border-slate-700" style={{ bottom: `${(avg / top) * 100}%` }} /> : undefined}>
            {buckets.map((b) => {
              const s = segs(b);
              const parts = s.slice().reverse().map((x) => `${sectionName(x.key === "other" ? "" : x.key)} ${fmtDuration(x.s, t)}`).join(", ");
              return (
                <Column key={b.start} title={`${fmtRange(b, lang)}: ${fmtDuration(b.seconds, t) || "0"}${parts ? ` (${parts})` : ""}`}>
                  {s.map((x, i) => (
                    <span key={x.key} className={cn("block w-full", i === 0 && "rounded-t-[3px]")}
                      style={{ height: `${(x.s / top) * 100}%`, background: x.color }} />
                  ))}
                </Column>
              );
            })}
          </BarFrame>
          <Legend className="mt-3" items={legend} label={t("progress.analytics.legend.label")} />
        </>
      )}
    </AnalyticsCard>
  );
}

export function ActiveHours({ data }: { data: ActivityOut }) {
  const { t } = useTranslation();
  const hours = data.by_hour.length === 24 ? data.by_hour : Array.from({ length: 24 }, (_, i) => data.by_hour[i] ?? 0);
  const total = hours.reduce((s, n) => s + n, 0);
  const peak = hours.reduce((best, n, i) => (n > hours[best] ? i : best), 0);
  const top = niceCount(Math.max(0, ...hours));
  const hh = (h: number) => `${String(h % 24).padStart(2, "0")}:00`;
  return (
    <AnalyticsCard title={t("progress.analytics.hours.title")}
      subtitle={total > 0 ? t("progress.analytics.hours.peak", { from: hh(peak), to: hh(peak + 1) }) : undefined}>
      {total === 0 ? (
        <CardEmpty compact pose="thinking" hint={t("progress.analytics.hours.empty")} />
      ) : (
        <BarFrame n={24} minStep={10} yTop={String(top)} yMid={String(top / 2)}
          label={t("progress.analytics.hours.summary", { from: hh(peak), to: hh(peak + 1), n: hours[peak] })}
          xLabel={(i) => hh(i)} ticks={[0, 6, 12, 18, 23]}>
          {hours.map((n, h) => (
            <Column key={h} title={t("progress.analytics.hours.bar", { from: hh(h), to: hh(h + 1), n })}>
              {n > 0 && <span className={cn("block w-full rounded-t-[3px]", h === peak ? "bg-brand-700" : "bg-brand-300")} style={{ height: `${(n / top) * 100}%` }} />}
            </Column>
          ))}
        </BarFrame>
      )}
    </AnalyticsCard>
  );
}

const BAND_TEXT = { low: "text-acc-low-text", mid: "text-acc-mid-text", high: "text-acc-high-text" } as const;

export function Sessions({ data }: { data: ActivityOut }) {
  const { lang, t } = useTranslation();
  const [all, setAll] = useState(false);
  const rows = all ? data.sessions : data.sessions.slice(0, 6);
  return (
    <AnalyticsCard title={t("progress.analytics.sessions.title")} subtitle={t("progress.analytics.sessions.subtitle")}>
      {data.sessions.length === 0 ? (
        <CardEmpty compact pose="encouraging" hint={t("progress.analytics.sessions.empty")} />
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {rows.map((s) => {
              const a = parseApiDate(s.started_at);
              const b = parseApiDate(s.ended_at);
              const secs = a && b ? Math.max(60, (b.getTime() - a.getTime()) / 1000) : 60;
              const p = s.answered ? Math.round((s.correct / s.answered) * 100) : 0;
              const day = a ? a.toLocaleDateString(locale(lang), { weekday: "short", day: "numeric", month: "short" }) : "";
              return (
                <li key={s.started_at} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 first:pt-0 last:pb-0">
                  <span className="min-w-0 text-sm leading-5">
                    <span className="font-medium text-slate-900">{day}</span>
                    <span className="text-slate-600"> · {fmtTime(s.started_at, lang)}–{fmtTime(s.ended_at, lang)}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-3 text-sm leading-5 text-slate-700">
                    <span>{fmtDuration(secs, t)}</span>
                    <span>{t("progress.analytics.answers", { count: s.answered })}</span>
                    <span className={cn("font-semibold tabular-nums", BAND_TEXT[accuracyBand(p)])}>{t("progress.analytics.sessions.correct", { percent: p })}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          {data.sessions.length > 6 && (
            <Button variant="link" size="sm" className="mt-2" onClick={() => setAll((v) => !v)} aria-expanded={all}>
              {all ? t("progress.analytics.sessions.less") : t("progress.analytics.sessions.more", { count: data.sessions.length })}
            </Button>
          )}
        </>
      )}
    </AnalyticsCard>
  );
}

export function AllTimeHeatmap({ data }: { data: ActivityOut }) {
  const { t } = useTranslation();
  const total = data.heatmap.reduce((s, d) => s + d.answered, 0);
  const today = data.days.length ? data.days[data.days.length - 1].date : new Date().toISOString().slice(0, 10);
  return (
    <AnalyticsCard title={t("progress.analytics.heat.title")}
      subtitle={total > 0 ? t("progress.analytics.heat.streaks", { current: data.streak_current, longest: data.streak_longest }) : undefined}>
      {total === 0 ? (
        <CardEmpty compact pose="hello" hint={t("progress.analytics.heat.empty")} />
      ) : (
        <MonthHeatmap days={data.heatmap} last={today} label={t("progress.analytics.heat.label", { count: total })}
          summary={<span className="text-sm font-medium text-slate-700">{t("progress.analytics.heat.summary", { count: total })}</span>} />
      )}
    </AnalyticsCard>
  );
}
