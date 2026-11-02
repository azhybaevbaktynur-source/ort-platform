"use client";

import React from "react";
import { Button, LinkButton, Mascot } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";

/** Render failures anywhere under `[lang]` except the exam player (it has its own `attempts/[attemptId]/error.tsx`). */
export default function LangError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { lang, t } = useTranslation();
  return (
    <main role="alert" className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4 py-10 text-center">
      <Mascot pose="encouraging" size={96} className="mb-3" />
      <h1 className="text-xl font-bold text-slate-900">{t("mascot.error.title")}</h1>
      <p className="mt-1 text-sm leading-6 text-slate-600">{t("mascot.error.body")}</p>
      <div className="mt-5 flex flex-col items-stretch gap-2 sm:flex-row">
        <Button onClick={() => reset()}>{t("mascot.error.retry")}</Button>
        <LinkButton href={`/${lang}`} variant="secondary">{t("mascot.error.home")}</LinkButton>
      </div>
    </main>
  );
}
