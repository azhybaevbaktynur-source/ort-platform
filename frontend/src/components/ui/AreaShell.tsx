"use client";

import React, { useEffect, useId, useState } from "react";
import Link from "next/link";
import { ChevronDown, Menu } from "lucide-react";
import { TabsNav } from "./Tabs";
import { Dialog } from "./Dialog";
import { cn, focusRing } from "./utils";

/*
 * Area frame (Phase 6b S5b, PHASE_6_DESIGN.md §3 and §8.3): the sections of one area (Platform admin,
 * Organization) as a side nav from `md`, and as one horizontally scrollable tab row on phones
 * (edge fade, the active section scrolled into view) so the content starts right under the header.
 *
 * Phase 8c S1 (PHASE_8C_DESIGN §2.1): `phone="drawer"` (the course sidebar) replaces the phone tab row with one
 * full-width "Menu · Active link" button that opens a left sheet with the links (Dialog: focus trap, Esc,
 * backdrop); choosing a link closes it. The default stays `tabs`, so the admin and org areas do not change.
 */

export interface AreaNavItem {
  href: string;
  label: string;
  active: boolean;
  /** Small count after the label (for example waiting requests). */
  count?: number | null;
  icon?: React.ReactNode;
  /** Phase 8c S1: a small trailing mark with its own accessible name (for example "hidden from students"). */
  marker?: { icon: React.ReactNode; label: string } | null;
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
  /** Phase 8c S1: phone navigation, `tabs` (default) or `drawer` (one menu button + left sheet). */
  phone?: "tabs" | "drawer";
  /** Phase 8c S1, drawer mode: the menu button's text before the active link ("Course menu"). */
  menuLabel?: string;
  /** Phase 8c S1: a short line under the side nav (and at the end of the sheet). */
  navFooter?: React.ReactNode;
}

function NavList({ items, onChoose }: { items: AreaNavItem[]; onChoose?: () => void }) {
  return (
    <ul className="space-y-0.5">
      {items.map((i) => (
        <li key={i.href}>
          <Link href={i.href} aria-current={i.active ? "page" : undefined} onClick={onChoose}
            className={cn(
              "relative flex min-h-11 items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium leading-5 transition-colors",
              focusRing,
              i.active ? "bg-brand-50 font-semibold text-brand-800" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
            )}>
            {i.active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-1 rounded-full bg-brand-600" />}
            {i.icon && <span aria-hidden="true" className={cn("inline-flex shrink-0 [&>svg]:h-4 [&>svg]:w-4", i.active ? "text-brand-700" : "text-slate-500")}>{i.icon}</span>}
            <span className="min-w-0 flex-1 break-words">{i.label}</span>
            {i.marker && (
              <span role="img" aria-label={i.marker.label} title={i.marker.label}
                className="inline-flex shrink-0 text-slate-500 [&>svg]:h-4 [&>svg]:w-4">{i.marker.icon}</span>
            )}
            {i.count ? (
              <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", i.active ? "bg-brand-100 text-brand-800" : "bg-slate-100 text-slate-700")}>{i.count}</span>
            ) : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function PhoneDrawer({ label, menuLabel, items, heading, navFooter }: {
  label: string; menuLabel: string; items: AreaNavItem[]; heading?: React.ReactNode; navFooter?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const sheetId = useId();
  const active = items.find((i) => i.active);
  const activeHref = active?.href;
  // a navigation (link chosen, back button) closes the sheet
  useEffect(() => { setOpen(false); }, [activeHref]);
  return (
    <div className="mb-5 md:hidden">
      <button type="button" aria-expanded={open} aria-controls={open ? sheetId : undefined} onClick={() => setOpen(true)}
        className={cn("flex min-h-11 w-full items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-50", focusRing)}>
        <Menu aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="min-w-0 flex-1 break-words">
          {menuLabel}{active ? <> · <span className="font-semibold text-slate-900">{active.label}</span></> : null}
        </span>
        <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title={heading ?? menuLabel}
        className="m-0 mr-auto h-[100dvh] max-h-[100dvh] w-[85vw] max-w-xs rounded-none rounded-r-2xl sm:max-w-xs">
        <nav id={sheetId} aria-label={label} className="-mx-2">
          <NavList items={items} onChoose={() => setOpen(false)} />
          {navFooter && <div className="mt-4 px-3 text-xs leading-5 text-slate-600">{navFooter}</div>}
        </nav>
      </Dialog>
    </div>
  );
}

export function AreaShell({ label, items, heading, banner, children, className, phone = "tabs", menuLabel, navFooter }: AreaShellProps) {
  return (
    <div className={className}>
      {banner}
      {phone === "drawer" ? (
        <PhoneDrawer label={label} menuLabel={menuLabel ?? label} items={items} heading={heading} navFooter={navFooter} />
      ) : (
        <TabsNav
          label={label}
          className="-mx-4 mb-5 bg-white px-1 md:hidden"
          items={items.map((i) => ({ href: i.href, label: i.label, active: i.active, count: i.count ? i.count : undefined }))}
        />
      )}
      <div className="md:flex md:items-start md:gap-8">
        <nav aria-label={label} className="hidden md:block md:w-56 md:shrink-0">
          {heading && <div className="mb-3 px-3">{heading}</div>}
          <NavList items={items} />
          {navFooter && <p className="mt-4 px-3 text-xs leading-5 text-slate-600">{navFooter}</p>}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
