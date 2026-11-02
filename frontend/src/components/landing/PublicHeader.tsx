"use client";

import React from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { Brand } from "@/components/ui/AppHeader";
import { buttonClasses, cn, focusRing } from "@/components/ui";
import { LANDING_INNER } from "./roles";
import { LANDING_LANGS, useSwitchLang } from "./useSwitchLang";

/** A native select stays compact next to the two account links and is the easiest control on a phone. */
function LanguageSelect() {
  const { lang, t } = useTranslation();
  const switchLang = useSwitchLang();
  return (
    <label className="relative block shrink-0">
      <span className="sr-only">{t("common.language")}</span>
      <select value={lang} onChange={(e) => switchLang(e.target.value as Language)}
        className={cn("min-h-11 cursor-pointer appearance-none rounded-xl border border-slate-200 bg-white pl-2.5 pr-7 text-sm font-semibold text-slate-700 hover:border-slate-300", focusRing)}>
        {LANDING_LANGS.map((l) => <option key={l} value={l}>{l.toUpperCase()}</option>)}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
    </label>
  );
}

/** The only login and the only top sign-up of the public pages. Signed in: "My courses" and the name instead. */
export function PublicHeader() {
  const { lang, t } = useTranslation();
  const { user, userProfile } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className={cn(LANDING_INNER, "flex h-16 items-center justify-between gap-2")}>
        <Brand href={`/${lang}`} hideNameOnPhone />
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
          <LanguageSelect />
          {user ? (
            <>
              <Link href={`/${lang}/courses`} className={buttonClasses({ className: "shrink-0 px-3 text-sm sm:px-4" })}>
                {t("landing.myCourses")}
              </Link>
              <span className="min-w-0 truncate text-sm font-medium text-slate-700 sm:max-w-[14rem]">
                {userProfile?.displayName || user.email}
              </span>
            </>
          ) : (
            <>
              <Link href={`/${lang}/login`}
                className={cn("inline-flex min-h-11 shrink-0 items-center rounded-xl px-2 text-sm font-semibold text-slate-700 transition-colors hover:text-brand-700 sm:px-3", focusRing)}>
                {t("common.login")}
              </Link>
              <Link href={`/${lang}/register`} className={buttonClasses({ className: "shrink-0 px-3 text-sm sm:px-4" })}>
                {t("common.register")}
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
