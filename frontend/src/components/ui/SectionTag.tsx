"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1): a tinted pill per ORT section ("Математика I", "Чтение", ...). The colour is
 * decoration only: the label always says which section it is. Unknown keys get a neutral slate pill.
 */

const TONES: Record<string, string> = {
  math_1: "bg-tag-math1 text-tag-math1-fg",
  math_2: "bg-tag-math2 text-tag-math2-fg",
  analogies: "bg-tag-analogies text-tag-analogies-fg",
  reading: "bg-tag-reading text-tag-reading-fg",
  grammar: "bg-tag-grammar text-tag-grammar-fg",
};

export interface SectionTagProps {
  /** Section key (`math_1`, `math_2`, `analogies`, `reading`, `grammar`; anything else is neutral). */
  section: string;
  /** Text of the pill; default `sections.<key>`. */
  label?: React.ReactNode;
  size?: "sm" | "md";
  className?: string;
}

export function SectionTag({ section, label, size = "sm", className }: SectionTagProps) {
  const { t } = useTranslation();
  return (
    <span className={cn(
      "inline-flex max-w-full items-center rounded-full font-semibold",
      size === "sm" ? "px-2.5 py-0.5 text-xs leading-5" : "px-3 py-1 text-sm leading-5",
      TONES[section] ?? "bg-slate-100 text-slate-700",
      className,
    )}>
      <span className="min-w-0 break-words">{label ?? t(`sections.${section}`)}</span>
    </span>
  );
}
