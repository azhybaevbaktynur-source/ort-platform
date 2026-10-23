"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { GraduationCap, KeyRound, LayoutDashboard, Plus, Scale, ShieldCheck, UserPlus } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { LmsMeProvider, useLmsMeLoader } from "@/lib/lms/useLmsMe";
import { ErrorMessage } from "./ErrorMessage";

const LANGS: Language[] = ["en", "ru", "ky"];

/**
 * Top-level frame for every LMS page (courses/*, admin/*). Redirects signed-out users to login,
 * loads MeOut once and provides it through `useLmsMe()`.
 */
export function LmsShell({ children }: { children: React.ReactNode }) {
  const { lang, setLang, t } = useTranslation();
  const { user, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const signedIn = !authLoading && !!user;
  const meState = useLmsMeLoader(signedIn);
  const { me } = meState;

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace(`/${lang}/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [authLoading, user, lang, pathname, router]);

  const switchLang = (l: Language) => {
    setLang(l);
    const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "");
    router.push(`/${l}${rest}`);
  };

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500" role="status">
        {t("lms.common.loading")}
      </div>
    );
  }

  const linkCls = "inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100";
  return (
    <LmsMeProvider value={meState}>
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
            <Link href={`/${lang}/courses`} className="mr-2 inline-flex items-center gap-2 text-base font-bold text-slate-900">
              <GraduationCap className="h-5 w-5 text-brand-600" aria-hidden="true" />
              {t("lms.nav.myCourses")}
            </Link>
            <nav aria-label={t("lms.nav.label")} className="flex flex-1 flex-wrap items-center gap-1">
              <Link href={`/${lang}/courses/join`} className={linkCls}><KeyRound className="h-4 w-4" aria-hidden="true" />{t("lms.nav.join")}</Link>
              {me?.can_create_courses && (
                <Link href={`/${lang}/courses/new`} className={linkCls}><Plus className="h-4 w-4" aria-hidden="true" />{t("lms.nav.create")}</Link>
              )}
              {me && !me.can_create_courses && (me.teacher_status === "none" || me.teacher_status === "revoked") && (
                <Link href={`/${lang}/courses/become-teacher`} className={linkCls}><UserPlus className="h-4 w-4" aria-hidden="true" />{t("lms.nav.becomeTeacher")}</Link>
              )}
              {(me?.can_create_courses || me?.is_platform_admin) && (
                <Link href={`/${lang}/grading-schemes`} className={linkCls}><Scale className="h-4 w-4" aria-hidden="true" />{t("lms.nav.gradingSchemes")}</Link>
              )}
              {me?.is_platform_admin && (
                <Link href={`/${lang}/admin`} className={linkCls}><ShieldCheck className="h-4 w-4" aria-hidden="true" />{t("lms.nav.platformAdmin")}</Link>
              )}
              <Link href={`/${lang}/courses#catalog`} className={linkCls}><LayoutDashboard className="h-4 w-4" aria-hidden="true" />{t("lms.nav.catalog")}</Link>
            </nav>
            <div role="group" aria-label={t("common.language")} className="flex gap-1">
              {LANGS.map((l) => (
                <button key={l} type="button" aria-pressed={l === lang} onClick={() => switchLang(l)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-bold ${l === lang ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">
          {meState.error && !me ? <ErrorMessage error={meState.error} onRetry={meState.reload} /> : children}
        </main>
      </div>
    </LmsMeProvider>
  );
}
