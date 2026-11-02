"use client";

import React from "react";
import { Check } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "@/components/ui";

export type ApplyStepKey = "account" | "email" | "application";
const STEPS: ApplyStepKey[] = ["account", "email", "application"];

/** Three equal columns on a phone, a list beside the form from `lg`. */
export function ApplySteps({ current, className }: { current: ApplyStepKey; className?: string }) {
  const { t } = useTranslation();
  const at = STEPS.indexOf(current);
  return (
    <ol aria-label={t("teacherApply.steps.label")} className={cn("grid grid-cols-3 gap-2 lg:grid-cols-1 lg:gap-3", className)}>
      {STEPS.map((key, i) => (
        <li key={key} aria-current={i === at ? "step" : undefined}
          className={cn("flex min-w-0 flex-col items-center gap-1 text-center text-xs leading-4 lg:flex-row lg:gap-3 lg:text-left lg:text-base lg:leading-6",
            i === at ? "font-semibold text-slate-900" : i < at ? "text-slate-700" : "text-slate-600")}>
          <span aria-hidden="true" className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold lg:h-8 lg:w-8 lg:text-sm",
            i === at ? "bg-brand-600 text-white" : i < at ? "bg-brand-100 text-brand-800" : "bg-slate-100 text-slate-600")}>
            {i < at ? <Check className="h-4 w-4" /> : i + 1}
          </span>
          <span className="min-w-0 break-words">{t(`teacherApply.steps.${key}`)}</span>
        </li>
      ))}
    </ol>
  );
}
