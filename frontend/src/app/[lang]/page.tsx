"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { GraduationCap, BookOpen, Clock, BarChart3, Languages, LogIn, UserPlus } from "lucide-react";

export default function HomePage() {
  const { lang, setLang, t } = useTranslation();
  const { user, userProfile, signOut } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 text-slate-800">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex min-w-0 items-center space-x-3">
            <div className="w-10 h-10 shrink-0 rounded-xl bg-brand-600 flex items-center justify-center text-white font-bold text-lg shadow-sm shadow-brand-500/30" aria-hidden="true">
              {t("common.appName").charAt(0)}
            </div>
            <div className="min-w-0">
              <span className="font-bold text-lg tracking-tight text-slate-900 block truncate leading-tight">
                {t("common.appName")}
              </span>
              <span className="hidden text-xs text-slate-500 sm:block">
                {t("landing.badge")}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center space-x-2 sm:space-x-3">
            {/* Language Switcher */}
            <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
              {(["en", "ky", "ru"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  aria-pressed={lang === l}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    lang === l
                      ? "bg-white text-brand-600 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {l.toUpperCase()}
                </button>
              ))}
            </div>

            {/* Auth Actions in Header */}
            {user ? (
              <div className="flex items-center space-x-2">
                <Link
                  href={`/${lang}/courses`}
                  className="max-w-[7rem] truncate px-3 py-1.5 rounded-lg bg-brand-50 border border-brand-200 text-brand-700 text-xs font-bold hover:bg-brand-100 transition-colors sm:max-w-[14rem]"
                >
                  {userProfile?.displayName || user.email}
                </Link>
                <button
                  onClick={() => signOut()}
                  className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 text-xs font-semibold hover:bg-slate-50 transition-colors"
                >
                  {t("common.logout")}
                </button>
              </div>
            ) : (
              // phones: the hero below has the same two buttons, so the header keeps brand + language only
              <div className="hidden items-center space-x-2 sm:flex">
                <Link
                  href={`/${lang}/login`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-xs font-semibold hover:bg-slate-50 transition-colors"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  <span>{t("common.login")}</span>
                </Link>
                <Link
                  href={`/${lang}/register`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600 text-white text-xs font-bold hover:bg-brand-700 transition-colors shadow-2xs"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>{t("common.register")}</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="text-center max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            {t("landing.badge")}
          </div>

          <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight">
            {t("landing.title")}
          </h1>

          <p className="text-lg text-slate-600 leading-relaxed">
            {t("landing.subtitle")}
          </p>

          {/* Universal Single Door CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-6">
            {user ? (
              <Link
                href={`/${lang}/courses`}
                className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-md shadow-brand-500/25 transition-all"
              >
                <GraduationCap className="w-5 h-5" />
                <span>{t("landing.toCourses")}</span>
              </Link>
            ) : (
              <>
                <Link
                  href={`/${lang}/register`}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-md shadow-brand-500/25 transition-all"
                >
                  <UserPlus className="w-4 h-4" />
                  <span>{t("landing.start")}</span>
                </Link>
                <Link
                  href={`/${lang}/login`}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-white text-slate-800 font-bold text-sm border-2 border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-all"
                >
                  <LogIn className="w-4 h-4" />
                  <span>{t("landing.signIn")}</span>
                </Link>
              </>
            )}
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-16 pt-12 border-t border-slate-200">
          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <BookOpen className="w-8 h-8 text-brand-600 mb-3" aria-hidden="true" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">{t("landing.f1Title")}</h3>
            <p className="text-xs text-slate-500">{t("landing.f1Text")}</p>
          </div>
          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <Clock className="w-8 h-8 text-emerald-600 mb-3" aria-hidden="true" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">{t("landing.f2Title")}</h3>
            <p className="text-xs text-slate-500">{t("landing.f2Text")}</p>
          </div>
          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <BarChart3 className="w-8 h-8 text-amber-600 mb-3" aria-hidden="true" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">{t("landing.f3Title")}</h3>
            <p className="text-xs text-slate-500">{t("landing.f3Text")}</p>
          </div>
          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <Languages className="w-8 h-8 text-indigo-600 mb-3" aria-hidden="true" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">{t("landing.f4Title")}</h3>
            <p className="text-xs text-slate-500">{t("landing.f4Text")}</p>
          </div>
        </div>
      </main>
    </div>
  );
}

