"use client";

import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { cn, heatLevel } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";

/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): the all-time activity calendar as one small grid per month (Monday on top,
 * a column per week), months in a row. It shows at least the months with answers and as many earlier months as fill
 * the card (at most 13); the newest month is on the right and visible first: on a phone the row scrolls sideways
 * inside the card, starting at the end. Levels as the Heatmap primitive (0, 1-4, 5-14, 15-29, 30+ answers a day).
 * U9 (STUDENT_UI_REVIEW 11): where fewer than three full-size months fit (phones), exactly the last three months with
 * smaller cells, so nothing scrolls.
 */

const LEVEL_BG = ["bg-heat-0", "bg-heat-1", "bg-heat-2", "bg-heat-3", "bg-heat-4"] as const;
const CELL = 15; // px, gap 3 px
const MONTH_W = 6 * (CELL + 3) + 16; // widest month plus the gap between months
const PHONE_MONTHS = 3;
const PHONE_GAP = 12;

type Day = { date: string; n: number; future: boolean } | null;
interface Month { key: string; label: string; weeks: Day[][] }

const pad = (n: number) => String(n).padStart(2, "0");

function buildMonth(y: number, m: number, counts: Map<string, number>, last: string, lang: string, withYear: boolean): Month {
  const first = new Date(Date.UTC(y, m, 1));
  const offset = (first.getUTCDay() + 6) % 7; // Monday 0
  const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cols = Math.ceil((offset + days) / 7);
  const weeks: Day[][] = Array.from({ length: cols }, () => Array<Day>(7).fill(null));
  for (let d = 1; d <= days; d++) {
    const i = offset + d - 1;
    const date = `${y}-${pad(m + 1)}-${pad(d)}`;
    weeks[Math.floor(i / 7)][i % 7] = { date, n: counts.get(date) ?? 0, future: date > last };
  }
  let label = `${pad(m + 1)}.${y}`;
  try {
    label = first.toLocaleDateString(lang === "en" ? "en-GB" : lang, withYear ? { month: "short", year: "numeric", timeZone: "UTC" } : { month: "short", timeZone: "UTC" });
  } catch { /* keep the numeric label */ }
  return { key: `${y}-${m}`, label, weeks };
}

export function MonthHeatmap({ days, last, label, summary }: {
  days: { date: string; answered: number }[];
  /** Today, `YYYY-MM-DD` (the student's calendar day). */
  last: string;
  /** Accessible name of the calendar. */
  label: string;
  summary: React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  const scroller = useRef<HTMLDivElement | null>(null);
  const [fit, setFit] = useState(6);
  const [cell, setCell] = useState(CELL); // smaller on phones: three months fit
  const phone = fit < PHONE_MONTHS;
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      const full = Math.floor(w / MONTH_W);
      setFit(full);
      setCell(full < PHONE_MONTHS ? Math.max(8, Math.min(CELL, Math.floor(((w - (PHONE_MONTHS - 1) * PHONE_GAP) / PHONE_MONTHS + 3) / 6) - 3)) : CELL);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const months = useMemo(() => {
    const counts = new Map(days.map((d) => [d.date, d.answered]));
    const [ly, lm] = last.split("-").map(Number);
    const firstData = days.length ? days[0].date : last;
    const [fy, fm] = firstData.split("-").map(Number);
    const withData = (ly - fy) * 12 + (lm - fm) + 1;
    const n = phone ? PHONE_MONTHS : Math.min(13, Math.max(withData, fit));
    const out: Month[] = [];
    for (let k = n - 1; k >= 0; k--) {
      const idx = ly * 12 + (lm - 1) - k;
      // the year on the first month shown and on every January
      out.push(buildMonth(Math.floor(idx / 12), idx % 12, counts, last, lang, k === n - 1 || idx % 12 === 0));
    }
    return out;
  }, [days, last, fit, phone, lang]);

  // the newest month first: start scrolled to the end
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [months]);

  const fmt = (iso: string) => {
    try {
      const [y, m, d] = iso.split("-").map(Number);
      return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(lang === "en" ? "en-GB" : lang, { day: "numeric", month: "short", timeZone: "UTC" });
    } catch {
      return iso;
    }
  };

  return (
    <figure className="min-w-0">
      <div ref={scroller} className="overflow-x-auto pb-1">
        <div role="img" aria-label={label} className={cn("flex w-max min-w-full", phone ? "gap-3" : "gap-4", months.length <= Math.max(fit, PHONE_MONTHS) ? "justify-between" : "justify-end")}>
          {months.map((mo) => (
            <div key={mo.key} className="shrink-0">
              <p aria-hidden="true" className="mb-1.5 text-xs font-medium leading-4 text-slate-600">{mo.label}</p>
              <div className="flex gap-[3px]">
                {mo.weeks.map((w, i) => (
                  <div key={i} className="flex flex-col gap-[3px]">
                    {w.map((d, j) => (
                      <span key={j} title={d && !d.future ? t("ui.heatmap.cell", { date: fmt(d.date), n: d.n }) : undefined}
                        style={{ width: cell, height: cell }}
                        className={cn("rounded-[3px]", !d || d.future ? "bg-transparent" : LEVEL_BG[heatLevel(d.n)])} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <figcaption className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs leading-4 text-slate-600">
        <span className="min-w-0">{summary}</span>
        <span aria-hidden="true" className="inline-flex items-center gap-1">
          {t("ui.heatmap.less")}
          {LEVEL_BG.map((bg) => <span key={bg} className={cn("h-3 w-3 rounded-[3px]", bg)} />)}
          {t("ui.heatmap.more")}
        </span>
      </figcaption>
    </figure>
  );
}
