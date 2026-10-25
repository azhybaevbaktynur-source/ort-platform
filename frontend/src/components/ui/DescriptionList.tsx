import React from "react";
import { cn } from "./utils";

export interface DescriptionItem {
  term: React.ReactNode;
  description: React.ReactNode;
  /** Stable key (defaults to the index). */
  key?: string;
}

export interface DescriptionListProps {
  items: DescriptionItem[];
  /** `stacked`: term above value (default, best for long ky/ru terms); `columns`: term left, value right from `sm`. */
  layout?: "stacked" | "columns";
  /** Two items per row from `sm` (stacked layout only). */
  twoColumns?: boolean;
  className?: string;
}

/** Label/value pairs (`<dl>`) for detail pages. */
export function DescriptionList({ items, layout = "stacked", twoColumns = false, className }: DescriptionListProps) {
  if (layout === "columns") {
    return (
      <dl className={cn("divide-y divide-slate-100", className)}>
        {items.map((it, i) => (
          <div key={it.key ?? i} className="py-3 first:pt-0 last:pb-0 sm:grid sm:grid-cols-3 sm:gap-4">
            <dt className="text-sm font-medium leading-6 text-slate-600">{it.term}</dt>
            <dd className="mt-0.5 break-words text-base leading-6 text-slate-900 sm:col-span-2 sm:mt-0 sm:text-sm sm:leading-6">{it.description}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <dl className={cn("grid gap-x-6 gap-y-4", twoColumns && "sm:grid-cols-2", className)}>
      {items.map((it, i) => (
        <div key={it.key ?? i} className="min-w-0">
          <dt className="text-sm font-medium leading-6 text-slate-600">{it.term}</dt>
          <dd className="break-words text-base leading-6 text-slate-900 sm:text-sm sm:leading-6">{it.description}</dd>
        </div>
      ))}
    </dl>
  );
}
