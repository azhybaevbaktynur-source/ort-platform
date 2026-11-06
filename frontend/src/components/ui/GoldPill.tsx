import React from "react";
import Link from "next/link";
import { Star } from "lucide-react";
import { cn, focusRing } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1, §6): the gold "Открыть все экзамены" pill (paid access) and, with a pass, its
 * quiet `secondary` form ("Доступ до 31 мая"). Gold stays for access and achievements only.
 */

export interface GoldPillProps {
  children: React.ReactNode;
  /** A link when set, else a button. */
  href?: string;
  onClick?: () => void;
  /** Leading icon (default a star; `null` for none). */
  icon?: React.ReactNode | null;
  /** `secondary`: the student already has access. */
  variant?: "gold" | "secondary";
  /** Fill the width of its container (the sidebar). */
  block?: boolean;
  className?: string;
}

export function GoldPill({ children, href, onClick, icon, variant = "gold", block = false, className }: GoldPillProps) {
  const cls = cn(
    "inline-flex min-h-11 items-center gap-2 rounded-full border px-4 text-sm font-semibold leading-5 transition-colors",
    variant === "gold"
      ? "border-gold-300 bg-gradient-to-r from-gold-100 to-gold-200 text-gold-900 hover:from-gold-200 hover:to-gold-200"
      : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50",
    block && "w-full",
    focusRing,
    className,
  );
  const ico = icon === null ? null : (
    <span aria-hidden="true" className={cn("inline-flex shrink-0 [&>svg]:h-4 [&>svg]:w-4", variant === "gold" ? "text-gold-700" : "text-slate-500")}>
      {icon ?? <Star className="fill-current" />}
    </span>
  );
  const body = <>{ico}<span className="min-w-0 break-words text-left">{children}</span></>;
  if (href) return <Link href={href} className={cls} onClick={onClick}>{body}</Link>;
  return <button type="button" className={cls} onClick={onClick}>{body}</button>;
}
