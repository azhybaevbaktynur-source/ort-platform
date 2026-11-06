import React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn, focusRing } from "./utils";

export interface StatTileProps {
  label: React.ReactNode;
  value: React.ReactNode;
  /** Small line under the value ("3 waiting for review"). */
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  /** Makes the whole tile a link (for example to the list it counts). */
  href?: string;
  /** `gold` only for achievements. */
  tone?: "default" | "gold";
  /** Student UI colour (STUDENT_UI_DESIGN §1.1): the icon chip on a pastel; default `brand`. */
  iconTone?: StatIconTone;
  className?: string;
}

export type StatIconTone = "brand";
/** The student frame's one icon chip tone (STUDENT_UI_FIX_PLAN 4.1): brand-50 / brand-700. */
export const STAT_ICON_TONE: Record<StatIconTone, string> = {
  brand: "bg-brand-50 text-brand-700",
};

/** A number with its label; optionally a link to the list behind it. */
export function StatTile({ label, value, hint, icon, href, tone = "default", iconTone = "brand", className }: StatTileProps) {
  const box = cn(
    "flex min-h-[5.5rem] items-start gap-3 rounded-2xl border p-4 shadow-sm",
    tone === "gold" ? "border-gold-300 bg-gold-50" : "border-slate-200 bg-white",
    href && cn("transition-colors hover:border-brand-300 hover:bg-brand-50/40", focusRing),
    className,
  );
  const content = (
    <>
      {icon && (
        <span aria-hidden="true" className={cn("inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl [&>svg]:h-5 [&>svg]:w-5",
          tone === "gold" ? "bg-gold-100 text-gold-800" : STAT_ICON_TONE[iconTone])}>
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium leading-5 text-slate-600">{label}</span>
        <span className="mt-1 block text-2xl font-bold leading-8 text-slate-900">{value}</span>
        {hint && <span className="mt-0.5 block text-sm leading-5 text-slate-600">{hint}</span>}
      </span>
      {href && <ChevronRight aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-slate-500" />}
    </>
  );
  return href ? <Link href={href} className={box}>{content}</Link> : <div className={box}>{content}</div>;
}
