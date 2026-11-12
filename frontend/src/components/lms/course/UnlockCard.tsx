"use client";

// Student UI §5.1 b, U9 (review 9): one short gold card while some content needs a Pro pass; the details stay on /pro.
// Step 3a S2: shared by the hub's exam home (until S5) and the course Обзор (exam courses: `needs_pass`; other courses:
// a locked Pro module). Never for staff or test students: the server sends no lock for them.
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { GoldPill, cn } from "@/components/ui";

export function UnlockCard({ className }: { className?: string }) {
  const { lang, t } = useTranslation();
  return (
    <section aria-labelledby="home-unlock"
      className={cn("flex flex-col gap-3 rounded-card border border-gold-300 bg-gradient-to-br from-gold-50 to-gold-100 p-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5", className)}>
      <div className="min-w-0 flex-1">
        <h2 id="home-unlock" className="text-base font-semibold leading-6 text-gold-900">{t("home.prep.unlock.title")}</h2>
        <p className="text-base leading-6 text-slate-800 sm:text-sm sm:leading-5">{t("home.prep.unlock.body")}</p>
      </div>
      <GoldPill href={`/${lang}/pro`} className="justify-center sm:shrink-0">{t("access.needsPassLink")}</GoldPill>
    </section>
  );
}
