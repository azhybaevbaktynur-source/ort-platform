import React from "react";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1): a three-band accuracy bar. Below 60 % rose, 60-84 % amber, from 85 % green,
 * always with the number next to it (colour is never the only signal).
 */

export type AccuracyBand = "low" | "mid" | "high";

/** The band of a percentage (0-100). */
export function accuracyBand(percent: number): AccuracyBand {
  if (percent >= 85) return "high";
  if (percent >= 60) return "mid";
  return "low";
}

const FILL: Record<AccuracyBand, string> = { low: "bg-acc-low", mid: "bg-acc-mid", high: "bg-acc-high" };
const TEXT: Record<AccuracyBand, string> = { low: "text-acc-low-text", mid: "text-acc-mid-text", high: "text-acc-high-text" };

export interface MeterProps {
  /** 0-100; clamped. */
  value: number;
  /** Accessible name ("Уравнения: точность"). */
  label: string;
  /** Show "64 %" after the bar (default true). */
  showValue?: boolean;
  className?: string;
}

export function Meter({ value, label, showValue = true, className }: MeterProps) {
  const v = Math.max(0, Math.min(100, Math.round(Number.isFinite(value) ? value : 0)));
  const band = accuracyBand(v);
  return (
    <div className={cn("flex min-w-0 items-center gap-3", className)}>
      <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={v} aria-valuetext={`${v} %`}
        className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={cn("h-full rounded-full", FILL[band])} style={{ width: `${v}%` }} />
      </div>
      {showValue && <span aria-hidden="true" className={cn("w-11 shrink-0 text-right text-sm font-semibold tabular-nums", TEXT[band])}>{v} %</span>}
    </div>
  );
}
