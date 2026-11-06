"use client";

import React, { useMemo } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1, §3.3): a calendar heatmap of answers per day, one column per week (Monday on
 * top). Levels: 0, 1-4, 5-14, 15-29, 30+ answers. The grid is one image for screen readers (`label`, plus the total
 * in `summary`); each cell has a tooltip with its date and count. On a phone it scrolls sideways inside its own box.
 */

export interface HeatmapDay {
  /** `YYYY-MM-DD` (the student's calendar day). */
  date: string;
  answered: number;
}

export interface HeatmapProps {
  days: HeatmapDay[];
  /** Accessible name of the grid ("Моя активность"). */
  label: string;
  /** Short line under the grid, also read with it ("240 ответов за 3 месяца"). */
  summary?: React.ReactNode;
  /** Last day shown, `YYYY-MM-DD` (default: today on this device). */
  end?: string;
  /** Number of week columns (default 13, about three months). */
  weeks?: number;
  className?: string;
}

/** Level 0-4 of a day's answer count. */
export function heatLevel(answered: number): 0 | 1 | 2 | 3 | 4 {
  if (answered >= 30) return 4;
  if (answered >= 15) return 3;
  if (answered >= 5) return 2;
  if (answered >= 1) return 1;
  return 0;
}

const LEVEL_BG = ["bg-heat-0", "bg-heat-1", "bg-heat-2", "bg-heat-3", "bg-heat-4"] as const;
const DAY_MS = 86_400_000;

function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Midnight UTC of a `YYYY-MM-DD` day (day arithmetic only, never shown as a time). */
function dayMs(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, (m || 1) - 1, d || 1);
}

const isoOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function Heatmap({ days, label, summary, end, weeks = 13, className }: HeatmapProps) {
  const { lang, t } = useTranslation();
  const last = end ?? localToday();
  const cells = useMemo(() => {
    const counts = new Map(days.map((d) => [d.date, d.answered]));
    const lastMs = dayMs(last);
    const weekday = (new Date(lastMs).getUTCDay() + 6) % 7; // Monday 0
    const start = lastMs - (weekday + (weeks - 1) * 7) * DAY_MS;
    const out: { date: string; n: number; future: boolean }[] = [];
    for (let i = 0; i < weeks * 7; i++) {
      const ms = start + i * DAY_MS;
      const date = isoOf(ms);
      out.push({ date, n: counts.get(date) ?? 0, future: ms > lastMs });
    }
    return out;
  }, [days, last, weeks]);
  const fmt = (iso: string) => {
    try {
      return new Date(dayMs(iso)).toLocaleDateString(lang === "en" ? "en-GB" : lang, { day: "numeric", month: "short", timeZone: "UTC" });
    } catch {
      return iso;
    }
  };
  return (
    <figure className={cn("min-w-0", className)}>
      <div className="overflow-x-auto pb-1">
        <div role="img" aria-label={label} className="grid w-max grid-flow-col grid-rows-7 gap-[3px]">
          {cells.map((c) => (
            <span key={c.date} title={c.future ? undefined : t("ui.heatmap.cell", { date: fmt(c.date), n: c.n })}
              className={cn("h-3 w-3 rounded-[3px]", c.future ? "bg-transparent" : LEVEL_BG[heatLevel(c.n)])} />
          ))}
        </div>
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs leading-4 text-slate-600">
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
