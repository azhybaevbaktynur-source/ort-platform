"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { cn, focusRing } from "./utils";

/**
 * Horizontal scroller with fade indicators on the side(s) that have more content.
 * Used by Tabs and TabsNav so long tab rows (ky/ru) scroll instead of wrapping or clipping.
 */
function ScrollFade({ children, className }: { children: (ref: React.RefObject<HTMLDivElement | null>) => React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const left = el.scrollLeft > 1;
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setEdges((prev) => (prev.left === left && prev.right === right ? prev : { left, right }));
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    ro?.observe(el);
    if (el.firstElementChild) ro?.observe(el.firstElementChild);
    return () => { el.removeEventListener("scroll", update); ro?.disconnect(); };
  }, [update]);

  return (
    <div className={cn("relative border-b border-slate-200", className)}>
      {children(ref)}
      <span aria-hidden="true" className={cn("pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-white to-transparent transition-opacity", edges.left ? "opacity-100" : "opacity-0")} />
      <span aria-hidden="true" className={cn("pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-white to-transparent transition-opacity", edges.right ? "opacity-100" : "opacity-0")} />
    </div>
  );
}

/** Scroll the tab row (only sideways, never the page) so `el` is visible. */
function revealInRow(row: HTMLElement | null, selector: string) {
  const el = row?.querySelector<HTMLElement>(selector);
  if (!row || !el) return;
  const c = row.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  if (r.left < c.left) row.scrollLeft += r.left - c.left - 32;
  else if (r.right > c.right) row.scrollLeft += r.right - c.right + 32;
}

const TAB_BASE =
  "relative -mb-px inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-4 text-sm font-semibold leading-5 transition-colors";
const TAB_ON = "border-brand-600 text-brand-700";
const TAB_OFF = "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900";

function TabCount({ value, active }: { value: React.ReactNode; active: boolean }) {
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", active ? "bg-brand-100 text-brand-800" : "bg-slate-100 text-slate-700")}>{value}</span>
  );
}

export interface TabItem {
  id: string;
  label: React.ReactNode;
  /** Small count after the label ("12"). */
  count?: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  /** Base id; panels use `<TabPanel tabsId={id} value=...>`. */
  id: string;
  /** Accessible name of the tab list. */
  label: string;
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}

export const tabId = (tabsId: string, value: string) => `${tabsId}-tab-${value}`;
export const panelId = (tabsId: string, value: string) => `${tabsId}-panel-${value}`;

/**
 * In-page tabs (`role="tablist"`): arrow keys / Home / End move and select, only the
 * selected tab is in the Tab order. The row scrolls sideways with a fade when it overflows.
 * For tabs that are links to other pages use `TabsNav`.
 */
export function Tabs({ id, label, items, value, onChange, className }: TabsProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    revealInRow(listRef.current, '[aria-selected="true"]');
  }, [value]);

  const enabled = items.filter((i) => !i.disabled);
  const onKeyDown = (e: React.KeyboardEvent) => {
    const idx = enabled.findIndex((i) => i.id === value);
    let next: TabItem | undefined;
    if (e.key === "ArrowRight") next = enabled[(idx + 1) % enabled.length];
    else if (e.key === "ArrowLeft") next = enabled[(idx - 1 + enabled.length) % enabled.length];
    else if (e.key === "Home") next = enabled[0];
    else if (e.key === "End") next = enabled[enabled.length - 1];
    if (!next) return;
    e.preventDefault();
    onChange(next.id);
    document.getElementById(tabId(id, next.id))?.focus();
  };

  return (
    <ScrollFade className={className}>
      {(ref) => (
        <div
          ref={(node) => { listRef.current = node; (ref as React.MutableRefObject<HTMLDivElement | null>).current = node; }}
          role="tablist"
          aria-label={label}
          onKeyDown={onKeyDown}
          className="flex overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {items.map((item) => {
            const active = item.id === value;
            return (
              <button
                key={item.id}
                id={tabId(id, item.id)}
                type="button"
                role="tab"
                aria-selected={active}
                aria-controls={panelId(id, item.id)}
                tabIndex={active ? 0 : -1}
                disabled={item.disabled}
                onClick={() => onChange(item.id)}
                className={cn(TAB_BASE, active ? TAB_ON : TAB_OFF, "disabled:cursor-not-allowed disabled:opacity-50", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}
              >
                {item.label}
                {item.count !== undefined && <TabCount value={item.count} active={active} />}
              </button>
            );
          })}
        </div>
      )}
    </ScrollFade>
  );
}

/** Panel of one tab; render it only for the selected value (or keep all and pass `hidden`). */
export function TabPanel({ tabsId, value, children, className, hidden }: { tabsId: string; value: string; children: React.ReactNode; className?: string; hidden?: boolean }) {
  return (
    <div id={panelId(tabsId, value)} role="tabpanel" aria-labelledby={tabId(tabsId, value)} tabIndex={0} hidden={hidden}
      className={cn("pt-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600", className)}>
      {children}
    </div>
  );
}

export interface TabsNavItem {
  href: string;
  label: React.ReactNode;
  active: boolean;
  count?: React.ReactNode;
}

/** Tab-looking navigation between pages (links with `aria-current="page"`), same scroll and fade as Tabs. */
export function TabsNav({ label, items, className }: { label: string; items: TabsNavItem[]; className?: string }) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const activeHref = items.find((i) => i.active)?.href;
  useEffect(() => {
    revealInRow(listRef.current, '[aria-current="page"]');
  }, [activeHref]);
  return (
    <nav aria-label={label} className={className}>
      <ScrollFade>
        {(ref) => (
          <div ref={(node) => { listRef.current = node; (ref as React.MutableRefObject<HTMLDivElement | null>).current = node; }}
            className="flex overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {items.map((item) => (
              <Link key={item.href} href={item.href} aria-current={item.active ? "page" : undefined}
                className={cn(TAB_BASE, item.active ? TAB_ON : TAB_OFF, focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}>
                {item.label}
                {item.count !== undefined && <TabCount value={item.count} active={item.active} />}
              </Link>
            ))}
          </div>
        )}
      </ScrollFade>
    </nav>
  );
}
