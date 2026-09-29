"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { GraduationCap, ShieldCheck, BookOpen, Clock, BarChart3, TrendingUp, Target, LogIn, UserPlus } from "lucide-react";

export default function HomePage() {
  const { lang, setLang, t } = useTranslation();
  const { user, userProfile, signOut } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 text-slate-800">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center text-white font-bold text-lg shadow-sm shadow-brand-500/30">
              ОРТ
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight text-slate-900 block leading-tight">
                {t("common.appName")}
              </span>
              <span className="text-xs text-slate-500 block">
                ЖРТ / ОРТ Кыргызстан 2026
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Language Switcher */}
            <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
              <button
                onClick={() => setLang("ky")}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                  lang === "ky"
                    ? "bg-white text-brand-600 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Кыргызча
              </button>
              <button
                onClick={() => setLang("ru")}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                  lang === "ru"
                    ? "bg-white text-brand-600 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Русский
              </button>
            </div>

            {/* Auth Actions in Header */}
            {user ? (
              <div className="flex items-center space-x-2">
                <Link
                  href={userProfile?.role === "admin" ? `/${lang}/exams` : `/${lang}/dashboard`}
                  className="px-3 py-1.5 rounded-lg bg-brand-50 border border-brand-200 text-brand-700 text-xs font-bold hover:bg-brand-100 transition-colors"
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
              <div className="flex items-center space-x-2">
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
            12,000+ ОРТ суроолору жана жаңы формат
          </div>

          <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight">
            {lang === "ky"
              ? "Жалпы республикалык тестирлөөгө жогорку деңгээлде даярданыңыз"
              : "Готовьтесь к Общереспубликанскому тестированию на максимум"}
          </h1>

          <p className="text-lg text-slate-600 leading-relaxed">
            {lang === "ky"
              ? "Алтын сертификат максаты (219+ балл), күндүк окуу планы, терең талдоо жана бирдиктүү билим берүү экосистемасы."
              : "Цель — Золотой сертификат (219+ баллов), ежедневный умный план, детальный анализ и единая образовательная экосистема."}
          </p>

          {/* Universal Single Door CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-6">
            {user ? (
              <Link
                href={userProfile?.role === "admin" ? `/${lang}/exams` : `/${lang}/dashboard`}
                className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-md shadow-brand-500/25 transition-all"
              >
                <GraduationCap className="w-5 h-5" />
                <span>
                  {userProfile?.role === "admin"
                    ? (lang === "ky" ? "Башкаруу панелине өтүү" : "Перейти к управлению")
                    : (lang === "ky" ? "Окуучу дашбордуна өтүү" : "Перейти в кабинет ученика")}
                </span>
              </Link>
            ) : (
              <>
                <Link
                  href={`/${lang}/register`}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-md shadow-brand-500/25 transition-all"
                >
                  <UserPlus className="w-4 h-4" />
                  <span>{lang === "ky" ? "Даярданууну баштоо" : "Начать подготовку"}</span>
                </Link>
                <Link
                  href={`/${lang}/login`}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-white text-slate-800 font-bold text-sm border-2 border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-all"
                >
                  <LogIn className="w-4 h-4" />
                  <span>{lang === "ky" ? "Кирүү" : "Войти в систему"}</span>
                </Link>
              </>
            )}
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-16 pt-12 border-t border-slate-200">
          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <BookOpen className="w-8 h-8 text-brand-600 mb-3" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">
              {lang === "ky" ? "5 Негизги Бөлүм" : "5 Основных Разделов"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "Математика I & II, Окуу, Грамматика, Аналогиялар."
                : "Математика I & II, Чтение, Грамматика, Аналогии."}
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <Clock className="w-8 h-8 text-emerald-600 mb-3" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">
              {lang === "ky" ? "Ыкчам баалоо" : "Мгновенный подсчет"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "ЖРТнын 60-245 шкаласы боюнча реалдуу балл жана перцентиль."
                : "Точный пересчет в шкалу ОРТ (60-245) и перцентиль."}
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <Target className="w-8 h-8 text-indigo-600 mb-3" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">
              {lang === "ky" ? "Максаттуу балл" : "Целевой балл"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "Алтын сертификатка (219+ балл) карай күндүк дельта трекери."
                : "Индивидуальный трекер достижения Золотого сертификата (219+)."}
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white border border-slate-200">
            <BarChart3 className="w-8 h-8 text-amber-600 mb-3" />
            <h3 className="font-bold text-slate-900 text-sm mb-1">
              {lang === "ky" ? "Каталар менен иштөө" : "Работа над ошибками"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "Туура эмес жоопторду өзүнчө топтомго сактап кайталоо."
                : "Автоматический сбор ошибочных ответов с пояснениями."}
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

