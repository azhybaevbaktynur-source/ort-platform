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
  /** `md` (default) or `sm`: a compact metrics row (`p-3`, `text-xl` value, smaller icon chip). */
  size?: "md" | "sm";
  className?: string;
}

export type StatIconTone = "brand";
/** The student frame's one icon chip tone (STUDENT_UI_FIX_PLAN 4.1): brand-50 / brand-700. */
export const STAT_ICON_TONE: Record<StatIconTone, string> = {
  brand: "bg-brand-50 text-brand-700",
};

/**
 * A number with its label; optionally a link to the list behind it. Use for headline counts (dashboards, overview
 * pages); staff metrics rows pass `size="sm"`.
 */
export function StatTile({ label, value, hint, icon, href, tone = "default", iconTone = "brand", size = "md", className }: StatTileProps) {
  const sm = size === "sm";
  const box = cn(
    "flex items-start rounded-2xl border shadow-sm",
    sm ? "gap-2.5 p-3" : "min-h-[5.5rem] gap-3 p-4",
    tone === "gold" ? "border-gold-300 bg-gold-50" : "border-slate-200 bg-white",
    href && cn("transition-colors hover:border-brand-300 hover:bg-brand-50/40", focusRing),
    className,
  );
  const content = (
    <>
      {icon && (
        <span aria-hidden="true" className={cn("inline-flex shrink-0 items-center justify-center",
          sm ? "h-8 w-8 rounded-lg [&>svg]:h-4 [&>svg]:w-4" : "h-10 w-10 rounded-xl [&>svg]:h-5 [&>svg]:w-5",
          tone === "gold" ? "bg-gold-100 text-gold-800" : STAT_ICON_TONE[iconTone])}>
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium leading-5 text-slate-600">{label}</span>
        <span className={cn("block font-bold text-slate-900", sm ? "mt-0.5 text-xl leading-7" : "mt-1 text-2xl leading-8")}>{value}</span>
        {hint && <span className="mt-0.5 block text-sm leading-5 text-slate-600">{hint}</span>}
      </span>
      {href && <ChevronRight aria-hidden="true" className={cn("shrink-0 text-slate-500", sm ? "mt-0.5 h-4 w-4" : "mt-1 h-5 w-5")} />}
    </>
  );
  return href ? <Link href={href} className={box}>{content}</Link> : <div className={box}>{content}</div>;
}
