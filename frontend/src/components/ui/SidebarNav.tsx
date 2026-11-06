import React from "react";
import Link from "next/link";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §2.2): the student sidebar's link list. Groups with small-caps labels; the active
 * item is a white pill (`aria-current="page"`). `tone="navy"` is the dark sidebar, `tone="light"` the same list on a
 * white sheet (phone "More"). Items may carry sub-links (one level).
 */

export interface SidebarNavItem {
  key: string;
  label: string;
  /** A link when set, else a button (`onClick`). */
  href?: string;
  onClick?: () => void;
  icon?: React.ReactNode;
  active?: boolean;
  /** Small trailing text (a count, "2/4"). */
  badge?: React.ReactNode;
  children?: SidebarNavItem[];
}

export interface SidebarNavGroup {
  key: string;
  /** Small-caps group label ("УРОКИ"); none for the first group. */
  label?: string;
  items: SidebarNavItem[];
}

export interface SidebarNavProps {
  /** Accessible name of the navigation landmark. */
  label: string;
  groups: SidebarNavGroup[];
  tone?: "navy" | "light";
  /** Called after any item is chosen (closes a sheet). */
  onNavigate?: () => void;
  className?: string;
}

const RING_NAVY = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-navy-800";
const RING_LIGHT = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-0";

function itemClass(tone: "navy" | "light", active: boolean, sub: boolean): string {
  return cn(
    "flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left text-sm leading-5 transition-colors",
    sub ? "pl-10 font-medium" : "font-semibold",
    tone === "navy"
      ? cn(RING_NAVY, active ? "bg-white text-navy-800" : "text-white/90 hover:bg-white/[0.08] hover:text-white")
      : cn(RING_LIGHT, active ? "bg-brand-50 text-brand-800" : "text-slate-800 hover:bg-slate-100"),
  );
}

function Item({ item, tone, sub, onNavigate }: { item: SidebarNavItem; tone: "navy" | "light"; sub: boolean; onNavigate?: () => void }) {
  const active = !!item.active;
  const body = (
    <>
      {item.icon && (
        <span aria-hidden="true" className={cn("inline-flex shrink-0 [&>svg]:h-5 [&>svg]:w-5",
          tone === "navy" ? (active ? "text-navy-800" : "text-white/[0.72]") : (active ? "text-brand-700" : "text-slate-500"))}>
          {item.icon}
        </span>
      )}
      <span className="min-w-0 flex-1 break-words">{item.label}</span>
      {item.badge != null && (
        <span className={cn("shrink-0 text-xs font-semibold tabular-nums", tone === "navy" ? (active ? "text-navy-800" : "text-white/[0.72]") : "text-slate-600")}>
          {item.badge}
        </span>
      )}
    </>
  );
  const onClick = () => { item.onClick?.(); onNavigate?.(); };
  return (
    <li>
      {item.href ? (
        <Link href={item.href} aria-current={active ? "page" : undefined} onClick={onClick} className={itemClass(tone, active, sub)}>{body}</Link>
      ) : (
        <button type="button" onClick={onClick} className={itemClass(tone, active, sub)}>{body}</button>
      )}
      {item.children && item.children.length > 0 && (
        <ul className="mt-0.5 space-y-0.5">
          {item.children.map((c) => <Item key={c.key} item={c} tone={tone} sub onNavigate={onNavigate} />)}
        </ul>
      )}
    </li>
  );
}

export function SidebarNav({ label, groups, tone = "navy", onNavigate, className }: SidebarNavProps) {
  return (
    <nav aria-label={label} className={cn("space-y-4", className)}>
      {groups.filter((g) => g.items.length > 0).map((g) => (
        <div key={g.key}>
          {g.label && (
            <p className={cn("mb-1 px-3 text-[11px] font-semibold uppercase leading-4 tracking-[0.08em]",
              tone === "navy" ? "text-white/[0.62]" : "text-slate-500")}>
              {g.label}
            </p>
          )}
          <ul className="space-y-0.5">
            {g.items.map((i) => <Item key={i.key} item={i} tone={tone} sub={false} onNavigate={onNavigate} />)}
          </ul>
        </div>
      ))}
    </nav>
  );
}
