import React from "react";
import Link from "next/link";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §2.3): the phone bottom tab bar. Fixed slots, each an icon over an 11 px label,
 * at least 44 px tall; 64 px plus the safe-area inset. Links get `aria-current="page"`; a button slot (the "More"
 * sheet) reports `aria-expanded`. Hidden from 1024 px (the sidebar takes over). The page's <main> needs bottom
 * padding (`TAB_BAR_SPACE`) so the bar never covers content.
 */

export interface TabBarItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  href?: string;
  onClick?: () => void;
  active?: boolean;
  /** Button slots: the sheet it opens is open. */
  expanded?: boolean;
  /** Button slots: id of the sheet it opens. */
  controls?: string;
}

export interface TabBarProps {
  label: string;
  items: TabBarItem[];
  className?: string;
}

/** Bottom padding for <main> below 1024 px: the bar plus 16 px and the safe area. */
export const TAB_BAR_SPACE = "pb-[calc(80px+env(safe-area-inset-bottom))] lg:pb-8";

const SLOT = "flex min-h-11 w-full flex-col items-center justify-center gap-0.5 rounded-control px-1 pt-1 text-[11px] font-semibold leading-[14px] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600";

export function TabBar({ label, items, className }: TabBarProps) {
  return (
    <nav aria-label={label}
      className={cn("fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] lg:hidden", className)}>
      <ul className="mx-auto flex h-16 max-w-xl items-stretch gap-1 px-2 py-1.5">
        {items.map((it) => {
          const on = !!it.active || !!it.expanded;
          const body = (
            <>
              <span aria-hidden="true" className={cn("inline-flex h-7 w-12 items-center justify-center rounded-full [&>svg]:h-5 [&>svg]:w-5",
                on ? "bg-brand-50 text-brand-700" : "text-slate-500")}>
                {it.icon}
              </span>
              <span className={cn("max-w-full break-words text-center", on ? "text-brand-800" : "text-slate-600")}>{it.label}</span>
            </>
          );
          return (
            <li key={it.key} className="min-w-0 flex-1">
              {it.href ? (
                <Link href={it.href} aria-current={it.active ? "page" : undefined} onClick={it.onClick} className={SLOT}>{body}</Link>
              ) : (
                <button type="button" onClick={it.onClick} aria-expanded={it.expanded ?? false} aria-controls={it.controls}
                  aria-haspopup="dialog" className={SLOT}>{body}</button>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
