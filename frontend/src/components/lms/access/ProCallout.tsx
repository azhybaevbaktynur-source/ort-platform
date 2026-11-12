"use client";

// F6b Pro (docs/phases/SUBSCRIPTION_DESIGN.md 6): the lobby of a paid exam the student has no Pro for says so and
// offers the Pro page (was UnlockCallout; same slot).
import React from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { GoldPill, LinkButton, cn } from "@/components/ui";

/** `tests` (step 3a S2): the Pro bar under the course tabs on Тесты while some tests need a pass; its action is the gold
 * pill, so the tab keeps one primary button (on its next test). */
export function ProCallout({ className, variant = "lobby" }: { className?: string; variant?: "lobby" | "course" | "tests" }) {
  const { lang, t } = useTranslation();
  const k = variant === "course" ? "access.courseBar" : variant === "tests" ? "access.testsBar" : "access.lobby";
  return (
    <section aria-labelledby={`pro-callout-${variant}`}
      className={cn("flex flex-col gap-3 rounded-2xl border border-gold-300 bg-gold-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5", className)}>
      <div className="flex min-w-0 items-start gap-3">
        <Lock aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-gold-800" />
        <div className="min-w-0">
          <h2 id={`pro-callout-${variant}`} className="text-base font-semibold leading-6 text-slate-900">{t(`${k}.title`)}</h2>
          <p className="mt-1 text-sm leading-5 text-slate-700">{t(`${k}.body`)}</p>
        </div>
      </div>
      {variant === "tests"
        ? <GoldPill href={`/${lang}/pro`} className="w-full justify-center sm:w-auto sm:shrink-0">{t(`${k}.action`)}</GoldPill>
        : <LinkButton href={`/${lang}/pro`} className="w-full shrink-0 sm:w-auto">{t(`${k}.action`)}</LinkButton>}
    </section>
  );
}
