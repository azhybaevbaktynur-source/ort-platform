"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §3.1): the exam countdown as three tiles (days, hours, minutes); "Сегодня" on the
 * exam day. Updates every 30 seconds; nothing is announced while it ticks (the group's name carries the full value).
 */

/** Start of an exam day (`YYYY-MM-DD`) in Bishkek time (UTC+6, no daylight saving). */
export function examDayStart(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00+06:00`);
}

export interface CountdownProps {
  /** The moment counted down to (see `examDayStart`). */
  target: Date;
  /** What it counts down to, read with the value ("до экзамена"). */
  label: string;
  /** Tiles on a dark background (navy cards). */
  tone?: "light" | "dark";
  className?: string;
}

const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;

export function Countdown({ target, label, tone = "light", className }: CountdownProps) {
  const { t } = useTranslation();
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  const tile = cn("flex min-w-[4.5rem] flex-1 flex-col items-center justify-center rounded-control border px-3 py-2",
    tone === "dark" ? "border-white/15 bg-white/10 text-white" : "border-slate-200 bg-white text-slate-900");
  const unit = cn("text-xs font-medium leading-4", tone === "dark" ? "text-white/75" : "text-slate-600");
  if (now === null) {
    return <div aria-hidden="true" className={cn("flex gap-2", className)}><span className={cn(tile, "h-[4.25rem]")} /><span className={cn(tile, "h-[4.25rem]")} /><span className={cn(tile, "h-[4.25rem]")} /></div>;
  }
  const left = target.getTime() - now;
  if (left <= 0) {
    if (left <= -DAY) return null; // the day is over
    return (
      <div role="group" aria-label={`${label}: ${t("ui.countdown.today")}`} className={cn("flex", className)}>
        <span className={cn(tile, "py-3 text-lg font-bold leading-7")}>{t("ui.countdown.today")}</span>
      </div>
    );
  }
  const days = Math.floor(left / DAY);
  const hours = Math.floor((left % DAY) / (60 * MINUTE));
  const minutes = Math.floor((left % (60 * MINUTE)) / MINUTE);
  const parts: [number, string][] = [[days, t("ui.countdown.days")], [hours, t("ui.countdown.hours")], [minutes, t("ui.countdown.minutes")]];
  return (
    <div role="group" aria-label={`${label}: ${parts.map(([n, u]) => `${n} ${u}`).join(" ")}`} className={cn("flex gap-2", className)}>
      {parts.map(([n, u], i) => (
        <span key={i} aria-hidden="true" className={tile}>
          <span className="text-2xl font-bold leading-8 tabular-nums">{i === 0 ? n : String(n).padStart(2, "0")}</span>
          <span className={unit}>{u}</span>
        </span>
      ))}
    </div>
  );
}
