"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlarmClock, Clock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatClock } from "./playerUtils";

/**
 * Countdown to an absolute deadline. The remaining time is recomputed from the (server-corrected) clock on
 * every tick, never decremented, so background-tab throttling and sleeping laptops cannot drift it.
 */
export function DeadlineTimer({
  deadlineMs,
  getNowMs,
  onExpire,
  onTick,
  label,
}: {
  deadlineMs: number | null;
  getNowMs: () => number;
  onExpire: () => void;
  onTick?: (remainingMs: number) => void;
  label?: string;
}) {
  const { t } = useTranslation();
  const [left, setLeft] = useState<number | null>(null);
  const expiredFor = useRef<number | null>(null);
  const cb = useRef({ onExpire, onTick, getNowMs });
  useEffect(() => {
    cb.current = { onExpire, onTick, getNowMs };
  });

  useEffect(() => {
    if (deadlineMs === null) {
      setLeft(null);
      return;
    }
    const tick = () => {
      const rem = deadlineMs - cb.current.getNowMs();
      setLeft(rem);
      cb.current.onTick?.(rem);
      if (rem <= 0 && expiredFor.current !== deadlineMs) {
        expiredFor.current = deadlineMs;
        cb.current.onExpire();
      }
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [deadlineMs]);

  if (deadlineMs === null || left === null) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-sm text-slate-500">
        <Clock className="h-4 w-4" aria-hidden="true" />
        {t("player.timer.unlimited")}
      </span>
    );
  }
  const secs = Math.max(0, Math.ceil(left / 1000));
  const urgent = secs <= 60;
  const warn = secs <= 300;
  const tone = urgent ? "bg-red-50 text-red-700 border-red-300" : warn ? "bg-amber-50 text-amber-900 border-amber-300" : "bg-slate-50 text-slate-800 border-slate-200";
  // Under five minutes the icon changes too and the digits turn bold: colour is never the only signal (S7b, P4).
  const Icon = warn ? AlarmClock : Clock;
  return (
    <div className="flex items-center gap-2">
      {label ? <span className="hidden text-xs text-slate-600 sm:inline">{label}</span> : null}
      <span
        role="timer"
        aria-label={t("player.timer.label")}
        className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 font-mono text-sm tabular-nums ${warn ? "font-extrabold" : "font-semibold"} ${tone}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
        {formatClock(secs)}
      </span>
      {/* Announce only at the two thresholds, not every second. */}
      <span className="sr-only" role="status" aria-live="polite">
        {secs <= 60 && secs > 55 ? t("player.timer.oneMinute") : secs <= 300 && secs > 295 ? t("player.timer.fiveMinutes") : ""}
      </span>
    </div>
  );
}
