"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { GraduationCap } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";

const LANGS: Language[] = ["en", "ky", "ru"];

/**
 * Interface language switcher (EN / KY / RU), shared by the auth and invitation pages (audit P2).
 * Switches the dictionary and the `/{lang}` prefix of the current URL (query string kept).
 */
export function UiLanguageSwitcher() {
  const { lang, setLang, t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const switchTo = (l: Language) => {
    setLang(l);
    const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "");
    const qs = typeof window !== "undefined" ? window.location.search : "";
    router.replace(`/${l}${rest}${qs}`);
  };
  return (
    <div role="group" aria-label={t("common.language")} className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1">
      {LANGS.map((l) => (
        <button key={l} type="button" aria-pressed={lang === l} onClick={() => switchTo(l)}
          className={`min-h-[36px] min-w-[44px] rounded-md px-2.5 text-xs font-semibold transition-all ${lang === l ? "bg-white text-brand-600 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

/** Brand (common.appName + landing.badge) and the language switcher above the auth card. */
export function AuthHeader() {
  const { lang, t } = useTranslation();
  return (
    <div className="mb-8 flex items-center justify-between gap-3 px-4 sm:mx-auto sm:w-full sm:max-w-md">
      <Link href={`/${lang}`} className="flex min-w-0 items-center gap-3">
        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm shadow-brand-500/30">
          <GraduationCap className="h-6 w-6" aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block font-bold leading-tight tracking-tight text-slate-900">{t("common.appName")}</span>
          <span className="block text-xs text-slate-500">{t("landing.badge")}</span>
        </span>
      </Link>
      <UiLanguageSwitcher />
    </div>
  );
}
