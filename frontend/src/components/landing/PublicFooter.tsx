"use client";

import React from "react";
import Link from "next/link";
import { GraduationCap } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "@/components/ui";
import { LANDING_INNER } from "./roles";
import { LANDING_LANGS, useSwitchLang } from "./useSwitchLang";

const FOCUS_DARK = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900";
const HEADING = "text-sm font-semibold text-white";

function FooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <li>
      <Link href={href} className={cn("inline-flex min-h-11 items-center rounded-md text-sm text-slate-300 transition-colors hover:text-white", FOCUS_DARK)}>
        {children}
      </Link>
    </li>
  );
}

export function PublicFooter() {
  const { lang, t } = useTranslation();
  const switchLang = useSwitchLang();
  return (
    <footer className="bg-slate-900 text-slate-300">
      <div className={cn(LANDING_INNER, "grid gap-8 py-10 sm:grid-cols-2 sm:py-14 lg:grid-cols-[2fr_1fr_1fr_1.4fr]")}>
        <div className="max-w-xs">
          <div className="flex items-center gap-2.5">
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white">
              <GraduationCap className="h-5 w-5" />
            </span>
            <span className="text-base font-bold text-white">{t("common.appName")}</span>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-400">{t("landing.badge")}</p>
        </div>
        <nav aria-label={t("landing.footer.platform")}>
          <h2 className={HEADING}>{t("landing.footer.platform")}</h2>
          <ul className="mt-2">
            <FooterLink href={`/${lang}/about`}>{t("landing.footer.about")}</FooterLink>
            <FooterLink href={`/${lang}/for-teachers`}>{t("landing.footer.forTeachers")}</FooterLink>
          </ul>
        </nav>
        <nav aria-label={t("landing.footer.support")}>
          <h2 className={HEADING}>{t("landing.footer.support")}</h2>
          <ul className="mt-2">
            <FooterLink href={`/${lang}/help`}>{t("landing.footer.help")}</FooterLink>
            <FooterLink href={`/${lang}/contacts`}>{t("landing.footer.contacts")}</FooterLink>
            <FooterLink href={`/${lang}/policies/privacy`}>{t("landing.footer.privacy")}</FooterLink>
          </ul>
        </nav>
        <div>
          <h2 className={HEADING}>{t("common.language")}</h2>
          <div role="group" aria-label={t("common.language")} className="mt-2 flex flex-wrap gap-x-4">
            {LANDING_LANGS.map((l) => (
              <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => switchLang(l)}
                className={cn("min-h-11 rounded-md text-sm transition-colors hover:text-white", FOCUS_DARK,
                  lang === l ? "font-semibold text-white underline underline-offset-4" : "text-slate-300")}>
                {t(`landing.footer.languages.${l}`)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
