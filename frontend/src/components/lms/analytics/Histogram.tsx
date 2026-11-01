"use client";

// Phase 10 S5: score distribution as CSS bars (no chart library). The same numbers are in a table for screen readers.
// `buckets` are ten counts of 10 percentage points each; 100 % is in the last bucket. Reused by course analytics (S6).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";

export function Histogram({ buckets, className = "" }: { buckets: number[]; className?: string }) {
  const { t } = useTranslation();
  const max = Math.max(1, ...buckets);
  const range = (i: number) => t("quizStats.bucketRange", { from: i * 10, to: i === buckets.length - 1 ? 100 : i * 10 + 10 });
  return (
    <figure className={className}>
      <div className="flex h-40 items-end gap-1 sm:gap-2" aria-hidden="true">
        {buckets.map((n, i) => (
          <div key={i} className="flex h-full min-w-0 flex-1 flex-col justify-end text-center">
            <span className="mb-0.5 text-xs tabular-nums text-slate-600">{n > 0 ? n : ""}</span>
            <div className="w-full rounded-t bg-brand-600" style={{ height: `${(n / max) * 100}%`, minHeight: n > 0 ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1 sm:gap-2" aria-hidden="true">
        {buckets.map((_, i) => (
          <span key={i} className="min-w-0 flex-1 truncate text-center text-[10px] text-slate-600 sm:text-xs">{i * 10}</span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{t("quizStats.histogramCaption")}</caption>
        <thead>
          <tr><th scope="col">{t("quizStats.colRange")}</th><th scope="col">{t("quizStats.colStudents")}</th></tr>
        </thead>
        <tbody>
          {buckets.map((n, i) => (
            <tr key={i}><th scope="row">{range(i)}</th><td>{n}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
