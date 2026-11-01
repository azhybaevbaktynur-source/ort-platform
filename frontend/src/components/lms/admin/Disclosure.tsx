import React from "react";
import { ChevronRight } from "lucide-react";
import { cn, focusRing } from "@/components/ui";

/** UX rework E (UR-4): a rarely used section, folded under its title. A native `<details>`: keyboard and screen readers work. */
export function Disclosure({ title, children, className }: { title: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <details className={cn("group rounded-2xl border border-slate-200 bg-white shadow-sm", className)}>
      <summary className={cn("flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-2xl px-4 py-2 text-base font-semibold leading-6 text-slate-900 hover:bg-slate-50 sm:px-6 [&::-webkit-details-marker]:hidden", focusRing)}>
        <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-600 transition-transform group-open:rotate-90" />
        <span className="min-w-0 break-words">{title}</span>
      </summary>
      <div className="border-t border-slate-100 px-4 py-4 sm:px-6">{children}</div>
    </details>
  );
}
