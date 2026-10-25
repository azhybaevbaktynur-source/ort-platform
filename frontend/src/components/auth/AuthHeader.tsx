"use client";

import React from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { Brand } from "@/components/ui/AppHeader";
import { cn, focusRing } from "@/components/ui";

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
          className={cn("min-h-11 min-w-11 rounded-md px-2.5 text-sm font-semibold transition-all", focusRing, "focus-visible:ring-offset-0",
            lang === l ? "bg-white text-brand-800 shadow-sm" : "text-slate-700 hover:text-slate-900")}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

/** Brand (`AppHeader`'s mark: common.appName + landing.badge) and the language switcher above the auth card. */
export function AuthHeader() {
  const { lang } = useTranslation();
  return (
    <div className="mb-8 flex items-center justify-between gap-3 px-4 sm:mx-auto sm:w-full sm:max-w-md">
      <Brand href={`/${lang}`} tagline />
      <UiLanguageSwitcher />
    </div>
  );
}
