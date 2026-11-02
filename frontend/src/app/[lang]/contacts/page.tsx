"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "@/components/ui";
import { PublicPageHeading, PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER } from "@/components/landing/roles";

/** No public contact address exists yet: the owner fills `landing.contacts.body` before launch. */
export default function ContactsPage() {
  const { t } = useTranslation();
  return (
    <PublicShell>
      <PublicPageHeading title={t("landing.contacts.title")} pose="hello" />
      <div className={cn(LANDING_INNER, "py-10 sm:py-14")}>
        <p className="max-w-3xl text-base leading-7 text-slate-700 sm:text-lg sm:leading-8">{t("landing.contacts.body")}</p>
      </div>
    </PublicShell>
  );
}
