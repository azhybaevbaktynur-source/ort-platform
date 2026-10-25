import React from "react";
import { cn } from "./utils";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "system";

// Text/background pairs all reach at least 4.5:1 contrast.
const TONES: Record<BadgeTone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  info: "border-brand-200 bg-brand-50 text-brand-800",
  success: "border-success-200 bg-success-50 text-success-800",
  warning: "border-warning-200 bg-warning-50 text-warning-900",
  danger: "border-danger-200 bg-danger-50 text-danger-800",
  system: "border-slate-700 bg-slate-700 text-white",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** Optional icon before the text (color is never the only signal). */
  icon?: React.ReactNode;
}

/** Short status label, kept on one line (Phase 7a UX: no wrapped badges in tables); keep the labels short. */
export function Badge({ tone = "neutral", icon, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold leading-5 [&>svg]:h-3.5 [&>svg]:w-3.5 [&>svg]:shrink-0",
        TONES[tone],
        className,
      )}
      {...rest}
    >
      {icon}
      <span className="min-w-0 break-words">{children}</span>
    </span>
  );
}
