"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "@/components/ui";
import { PublicPageHeading, PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER } from "@/components/landing/roles";

/** A few real answers; every name in them is the label the app shows. */
export default function HelpPage() {
  const { lang, t } = useTranslation();
  const entries: { key: string; text: string; link?: { href: string; label: string } }[] = [
    // step 3a S7 (V5): «Войти по коду» is a button in the catalog's header
    { key: "joinCode", text: t("landing.help.joinCode.a", { catalog: t("student.nav.catalog"), join: t("home.primary.join") }) },
    { key: "catalog", text: t("landing.help.catalog.a", { catalog: t("catalog.title") }) },
    { key: "forgot", text: t("landing.help.forgot.a", { link: t("auth.forgotPassword") }),
      link: { href: `/${lang}/forgot-password`, label: t("landing.help.forgot.link") } },
    { key: "language", text: t("landing.help.language.a") },
    { key: "becomeTeacher", text: t("landing.help.becomeTeacher.a"),
      link: { href: `/${lang}/for-teachers/apply`, label: t("landing.help.becomeTeacher.link") } },
  ];
  return (
    <PublicShell>
      <PublicPageHeading title={t("landing.help.title")} intro={t("landing.help.intro")} pose="thinking" />
      <div className={cn(LANDING_INNER, "py-10 sm:py-14")}>
        <div className="max-w-3xl divide-y divide-slate-200">
          {entries.map(({ key, text, link }) => (
            <section key={key} aria-labelledby={`help-${key}`} className="py-6 first:pt-0 last:pb-0">
              <h2 id={`help-${key}`} className="text-lg font-bold leading-7 text-slate-900 sm:text-xl">{t(`landing.help.${key}.q`)}</h2>
              <p className="mt-2 text-base leading-7 text-slate-600">{text}</p>
              {link && (
                <Link href={link.href} className={cn("mt-1 inline-flex min-h-11 items-center rounded-md text-base font-semibold text-brand-700 underline-offset-4 hover:underline", focusRing)}>
                  {link.label}
                </Link>
              )}
            </section>
          ))}
        </div>
      </div>
    </PublicShell>
  );
}
