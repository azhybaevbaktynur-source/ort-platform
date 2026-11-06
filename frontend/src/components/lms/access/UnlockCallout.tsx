"use client";

// S3 access: the lobby of a paid exam the student has no pass for says so and offers the unlock page.
import React from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LinkButton, cn } from "@/components/ui";

export function UnlockCallout({ className }: { className?: string }) {
  const { lang, t } = useTranslation();
  return (
    <section aria-labelledby="unlock-callout"
      className={cn("flex flex-col gap-3 rounded-2xl border border-gold-300 bg-gold-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5", className)}>
      <div className="flex min-w-0 items-start gap-3">
        <Lock aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-gold-800" />
        <div className="min-w-0">
          <h2 id="unlock-callout" className="text-base font-semibold leading-6 text-slate-900">{t("access.lobby.title")}</h2>
          <p className="mt-1 text-sm leading-5 text-slate-700">{t("access.lobby.body")}</p>
        </div>
      </div>
      <LinkButton href={`/${lang}/unlock`} className="w-full shrink-0 sm:w-auto">{t("access.lobby.action")}</LinkButton>
    </section>
  );
}
