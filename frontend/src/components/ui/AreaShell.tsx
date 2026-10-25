"use client";

import React from "react";
import Link from "next/link";
import { TabsNav } from "./Tabs";
import { cn, focusRing } from "./utils";

/*
 * Area frame (Phase 6b S5b, PHASE_6_DESIGN.md §3 and §8.3): the sections of one area (Platform admin,
 * Organization) as a side nav from `md`, and as one horizontally scrollable tab row on phones
 * (edge fade, the active section scrolled into view) so the content starts right under the header.
 */

export interface AreaNavItem {
  href: string;
  label: string;
  active: boolean;
  /** Small count after the label (for example waiting requests). */
  count?: number | null;
  icon?: React.ReactNode;
}

export interface AreaShellProps {
  /** Accessible name of the section navigation. */
  label: string;
  items: AreaNavItem[];
  /** Small heading above the side nav on desktop (area name, organization name). Phones show it in the breadcrumbs. */
  heading?: React.ReactNode;
  /** Content above both nav and page, full width (for example a suspended-organization banner). */
  banner?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function AreaShell({ label, items, heading, banner, children, className }: AreaShellProps) {
  return (
    <div className={className}>
      {banner}
      <TabsNav
        label={label}
        className="-mx-4 mb-5 bg-white px-1 md:hidden"
        items={items.map((i) => ({ href: i.href, label: i.label, active: i.active, count: i.count ? i.count : undefined }))}
      />
      <div className="md:flex md:items-start md:gap-8">
        <nav aria-label={label} className="hidden md:block md:w-56 md:shrink-0">
          {heading && <div className="mb-3 px-3">{heading}</div>}
          <ul className="space-y-0.5">
            {items.map((i) => (
              <li key={i.href}>
                <Link href={i.href} aria-current={i.active ? "page" : undefined}
                  className={cn(
                    "relative flex min-h-11 items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium leading-5 transition-colors",
                    focusRing,
                    i.active ? "bg-brand-50 font-semibold text-brand-800" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
                  )}>
                  {i.active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-1 rounded-full bg-brand-600" />}
                  {i.icon && <span aria-hidden="true" className={cn("inline-flex shrink-0 [&>svg]:h-4 [&>svg]:w-4", i.active ? "text-brand-700" : "text-slate-500")}>{i.icon}</span>}
                  <span className="min-w-0 flex-1 break-words">{i.label}</span>
                  {i.count ? (
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", i.active ? "bg-brand-100 text-brand-800" : "bg-slate-100 text-slate-700")}>{i.count}</span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
