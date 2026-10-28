"use client";

// Phase 8a UX (minor 1): one chip style for the language versions of a page, in the viewer and the editor. The
// current version is the same chip with a selected style (and `aria-current`), the others are links.
import React from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import { cn, focusRing } from "@/components/ui";

const chip = "inline-flex min-h-11 items-center gap-1 rounded-full border px-3 text-sm font-medium";

export function LangChip({ label, href, selected = false }: { label: string; href?: string; selected?: boolean }) {
  if (selected || !href) {
    return (
      <span aria-current={selected ? "page" : undefined}
        className={cn(chip, selected ? "border-brand-600 bg-brand-50 text-brand-800" : "border-slate-300 bg-white text-slate-800")}>
        {selected && <Check aria-hidden="true" className="h-4 w-4" />}{label}
      </span>
    );
  }
  return (
    <Link href={href} className={cn(chip, "border-slate-300 bg-white text-slate-800 hover:bg-slate-50", focusRing)}>
      {label}
    </Link>
  );
}
