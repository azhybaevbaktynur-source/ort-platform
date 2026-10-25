"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/** One grey placeholder block (decorative). Size it with `className`. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("h-4 animate-pulse rounded-lg bg-slate-200 motion-reduce:animate-none", className)} />;
}

/** Placeholder lines of text; the last one is shorter. */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={cn("space-y-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={i === lines - 1 && lines > 1 ? "w-2/3" : "w-full"} />
      ))}
    </div>
  );
}

/**
 * Loading region: announces "Loading" to screen readers and shows the given skeletons
 * (or a default card list) in the page's layout, never a blank page.
 */
export function LoadingState({ label, rows = 3, children, className }: { label?: string; rows?: number; children?: React.ReactNode; className?: string }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className={className}>
      <span className="sr-only">{label ?? t("ui.loading")}</span>
      {children ?? (
        <div className="space-y-3">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} aria-hidden="true" className="rounded-2xl border border-slate-200 bg-white p-4">
              <Skeleton className="mb-3 h-5 w-1/2" />
              <SkeletonText lines={2} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
