"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "@/components/ui";
import { PublicPageHeading, PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER } from "@/components/landing/roles";

const PARAGRAPHS = ["p1", "p2", "p3"] as const;

export default function AboutPage() {
  const { t } = useTranslation();
  return (
    <PublicShell>
      <PublicPageHeading title={t("landing.about.title")} intro={t("landing.about.intro")} pose="reading" />
      <div className={cn(LANDING_INNER, "py-10 sm:py-14")}>
        <div className="max-w-3xl space-y-5 text-base leading-7 text-slate-700 sm:text-lg sm:leading-8">
          {PARAGRAPHS.map((p) => <p key={p}>{t(`landing.about.${p}`)}</p>)}
        </div>
      </div>
    </PublicShell>
  );
}
