"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1): a pill per ORT section ("Математика I", "Чтение", ...). One neutral tone for all
 * sections (STUDENT_UI_FIX_PLAN 4.1): the label text says which section it is, colour never does.
 */

export interface SectionTagProps {
  /** Section key (only picks the default label). */
  section: string;
  /** Text of the pill; default `sections.<key>`. */
  label?: React.ReactNode;
  size?: "sm" | "md";
  /** The section the page is about: the one subtle brand tint (STUDENT_UI_FIX_PLAN 4.1); every other tag is neutral. */
  current?: boolean;
  className?: string;
}

export function SectionTag({ section, label, size = "sm", current = false, className }: SectionTagProps) {
  const { t } = useTranslation();
  return (
    <span className={cn(
      "inline-flex max-w-full items-center rounded-full font-semibold",
      size === "sm" ? "px-2.5 py-0.5 text-xs leading-5" : "px-3 py-1 text-sm leading-5",
      current ? "bg-brand-50 text-brand-800" : "bg-[#eef2f7] text-[#334155]",
      className,
    )}>
      <span className="min-w-0 break-words">{label ?? t(`sections.${section}`)}</span>
    </span>
  );
}
