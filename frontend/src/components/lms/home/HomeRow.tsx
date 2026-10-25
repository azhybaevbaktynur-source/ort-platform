"use client";

import React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn, focusRing } from "@/components/ui";

/**
 * Phase 6b S6b: one tappable row of a home list (at least 44 px high). The visible `actionLabel` says what the
 * tap does ("Continue", "Open"), so the action is never hidden behind the row alone. On phones the `aside`
 * (a value or badge) and the label move under the text.
 */
export function HomeRow({ href, title, meta, aside, actionLabel, className }: {
  href: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  aside?: React.ReactNode;
  actionLabel?: React.ReactNode;
  className?: string;
}) {
  return (
    <li>
      <Link href={href}
        className={cn("flex min-h-11 items-center gap-3 rounded-xl px-3 py-3 hover:bg-slate-50 sm:px-4", focusRing, className)}>
        <span className="min-w-0 flex-1">
          <span className="block break-words text-base font-semibold leading-6 text-slate-900">{title}</span>
          {meta && <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm leading-6 text-slate-600">{meta}</span>}
          {/* phone: value and action under the text, so long ky/ru titles keep the full width */}
          {(aside || actionLabel) && (
            <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 sm:hidden">
              {aside}
              {actionLabel && <span className="text-sm font-semibold leading-6 text-brand-700">{actionLabel}</span>}
            </span>
          )}
        </span>
        {aside && <span className="hidden shrink-0 flex-col items-end gap-1 text-right sm:flex">{aside}</span>}
        {actionLabel && <span className="hidden shrink-0 text-right text-sm font-semibold leading-5 text-brand-700 sm:inline">{actionLabel}</span>}
        <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400" />
      </Link>
    </li>
  );
}

/** A titled home section: heading + rows in one card. */
export function HomeSection({ id, title, children, footer }: { id: string; title: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="mb-2 text-lg font-semibold leading-7 text-slate-900">{title}</h2>
      <div className="rounded-2xl border border-slate-200 bg-white p-1 shadow-sm sm:p-2">{children}</div>
      {footer && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">{footer}</div>}
    </section>
  );
}
